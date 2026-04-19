# 認証 PoC 統合構築手順書（個人環境版）

## Entra ID + Identity Platform + IAP + HTTPS on Cloud Run

## 変更履歴

| バージョン | 変更内容 |
|---|---|
| v1 | 初版（個人環境向け統合版） |

---

## 構成図

```
ユーザー
  ↓ HTTPS(443)
Cloud Load Balancing (External Application LB) + IAP
  │
  ├─ クッキーなし（未認証）
  │     ↓ IAPが自動リダイレクト
  │   Identity Platform（認証ページ: IAP自動生成）
  │     ↓ OIDCフロー
  │   Microsoft Entra ID（ログイン画面）
  │     ↓ 認証完了
  │   ブラウザにクッキー保存 → 再アクセス
  │
  └─ クッキーあり（認証済み）
        ↓ パスベースルーティング
        ├── /*       → Cloud Run: poc-frontend (Next.js)
        └── /api/*   → Cloud Run: poc-backend  (FastAPI)
                          ↓
                     Google Cloud Storage
```

---

## 前提条件

| 項目 | 値 |
|---|---|
| GCPプロジェクト | 個人環境（変数 `PROJECT_ID` で管理） |
| ドメイン | `poc.tetutetu214.com`（Cloudflare Registrar管理） |
| リージョン | `asia-northeast1` |
| VPC Service Controls | なし |
| SSL証明書 | Google マネージド証明書（DNS認証） |
| フロントエンド | Next.js 14（App Router） |
| バックエンド | FastAPI + Python 3.12 |
| max-instances | 3（PoC用） |

---

## Step1. 事前準備

### 1-1. プロジェクト設定

```bash
# プロジェクトをセット
gcloud config set project YOUR_PROJECT_ID

# 確認
PROJECT_ID=$(gcloud config get-value project)
echo "PROJECT_ID=${PROJECT_ID}"
```

### 1-2. API 有効化

```bash
gcloud services enable \
  run.googleapis.com \
  storage.googleapis.com \
  compute.googleapis.com \
  artifactregistry.googleapis.com \
  iap.googleapis.com \
  identitytoolkit.googleapis.com \
  certificatemanager.googleapis.com
```

### 1-3. Private Google Access 有効化

```bash
# Cloud Run 間の内部通信に必要（Direct VPC egress 経由で Google サービスにアクセスするため）
gcloud compute networks subnets update default \
  --region=asia-northeast1 \
  --enable-private-ip-google-access
```

---

## Step2. GCS バケット作成

```bash
PROJECT_ID=$(gcloud config get-value project)
BUCKET_NAME="poc-upload-${PROJECT_ID}"

gcloud storage buckets create gs://${BUCKET_NAME} \
  --location=asia-northeast1 \
  --uniform-bucket-level-access

echo "BUCKET_NAME=${BUCKET_NAME}"
```

---

## Step3. サービスアカウント作成・権限付与

### 3-1. バックエンド用 SA

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud iam service-accounts create poc-backend-sa \
  --display-name="POC Backend Service Account"

# GCS への読み書き権限
gcloud storage buckets add-iam-policy-binding gs://${BUCKET_NAME} \
  --member="serviceAccount:poc-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectUser"
```

### 3-2. フロントエンド用 SA

```bash
gcloud iam service-accounts create poc-frontend-sa \
  --display-name="POC Frontend Service Account"
```

> フロントエンド SA は GCS 等へのアクセス権限不要。
> Cloud Run のデフォルト SA（Compute Engine SA）を使わず、
> 最小権限の専用 SA を割り当てる目的。

---

## Step4. バックエンド (FastAPI) 構築

### 4-1. ディレクトリ作成

```bash
mkdir -p ~/poc/backend && cd ~/poc/backend
```

### 4-2. ファイル作成

**main.py**

```bash
cat > main.py << 'EOF'
from fastapi import FastAPI, UploadFile, File, HTTPException
from google.cloud import storage
import os

app = FastAPI()

BUCKET_NAME = os.environ["BUCKET_NAME"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="PDFファイルのみ受け付けます"
        )

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"uploads/{file.filename}")

    contents = await file.read()
    blob.upload_from_string(
        contents, content_type="application/pdf"
    )

    return {
        "message": "アップロード成功",
        "filename": file.filename,
    }
EOF
```

**requirements.txt**

```bash
cat > requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn==0.30.6
google-cloud-storage==2.18.0
python-multipart==0.0.9
EOF
```

**Dockerfile**

```bash
cat > Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
EOF
```

### 4-3. Artifact Registry リポジトリ作成

```bash
gcloud artifacts repositories create poc-repo \
  --repository-format=docker \
  --location=asia-northeast1
```

### 4-4. ビルド・デプロイ

```bash
PROJECT_ID=$(gcloud config get-value project)

# ビルド・プッシュ
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/backend:latest .

# Cloud Run デプロイ
gcloud run deploy poc-backend \
  --image=asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/backend:latest \
  --region=asia-northeast1 \
  --service-account=poc-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars=BUCKET_NAME=${BUCKET_NAME} \
  --ingress=internal \
  --max-instances=3 \
  --allow-unauthenticated \
  --port=8080

# ※ --allow-unauthenticated だが、--ingress=internal により
#    外部からのアクセスは完全ブロックされる。
#    フロントエンド(Next.js)からの内部通信のみ受け付ける（3層構成）。

# バックエンドの URL を変数に保存
BACKEND_URL=$(gcloud run services describe poc-backend \
  --region=asia-northeast1 \
  --format='value(status.url)')
echo "BACKEND_URL=${BACKEND_URL}"
```

---

## Step5. フロントエンド (Next.js) 構築

### 5-1. ディレクトリ作成

```bash
mkdir -p ~/poc/frontend/app/api/upload && cd ~/poc/frontend
```

### 5-2. ファイル作成

**package.json**

```bash
cat > package.json << 'EOF'
{
  "name": "poc-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start -p 8080"
  },
  "dependencies": {
    "next": "14.2.5",
    "react": "18.3.1",
    "react-dom": "18.3.1"
  }
}
EOF
```

**next.config.js**

```bash
cat > next.config.js << 'EOF'
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
};

module.exports = nextConfig;
EOF
```

**tsconfig.json**

```bash
cat > tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{"name": "next"}],
    "paths": {"@/*": ["./*"]}
  },
  "include": [
    "next-env.d.ts", "**/*.ts", "**/*.tsx",
    ".next/types/**/*.ts"
  ],
  "exclude": ["node_modules"]
}
EOF
```

**app/layout.tsx**

```bash
cat > app/layout.tsx << 'EOF'
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
EOF
```

**app/page.tsx**

```bash
cat > app/page.tsx << 'EOF'
"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const handleUpload = async () => {
    if (!file) {
      setMessage("ファイルを選択してください");
      return;
    }
    setLoading(true);
    setMessage("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setMessage(data.message ?? JSON.stringify(data));
    } catch (e) {
      setMessage("エラーが発生しました");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ padding: "2rem" }}>
      <h1>PDF アップロード PoC</h1>
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) =>
          setFile(e.target.files?.[0] ?? null)
        }
      />
      <br /><br />
      <button onClick={handleUpload} disabled={loading}>
        {loading ? "アップロード中..." : "アップロード"}
      </button>
      {message && <p>{message}</p>}
    </main>
  );
}
EOF
```

**app/api/upload/route.ts**

```bash
cat > app/api/upload/route.ts << 'EOF'
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL;

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const res = await fetch(`${BACKEND_URL}/api/upload`, {
    method: "POST",
    body: formData,
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
EOF
```

**Dockerfile**

```bash
cat > Dockerfile << 'EOF'
FROM node:20-slim AS builder

WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM node:20-slim AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

CMD ["node", "server.js"]
EOF
```

### 5-3. ファイル構成確認

```bash
find ~/poc/frontend -type f | sort

# 期待される出力:
# .../frontend/Dockerfile
# .../frontend/app/api/upload/route.ts
# .../frontend/app/layout.tsx
# .../frontend/app/page.tsx
# .../frontend/next.config.js
# .../frontend/package.json
# .../frontend/tsconfig.json
```

### 5-4. ビルド・デプロイ

```bash
PROJECT_ID=$(gcloud config get-value project)
BACKEND_URL=$(gcloud run services describe poc-backend \
  --region=asia-northeast1 \
  --format='value(status.url)')

# ビルド・プッシュ
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/frontend:latest .

# Cloud Run デプロイ
gcloud run deploy poc-frontend \
  --image=asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/frontend:latest \
  --region=asia-northeast1 \
  --service-account=poc-frontend-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars=BACKEND_URL=${BACKEND_URL} \
  --ingress=internal-and-cloud-load-balancing \
  --network=default \
  --subnet=default \
  --vpc-egress=all-traffic \
  --max-instances=3 \
  --no-allow-unauthenticated \
  --port=8080

# ※ --network/--subnet/--vpc-egress は Direct VPC egress の設定。
#    バックエンド(ingress=internal)への内部通信に必要。
#    Step1-3 で Private Google Access を有効化済みであること。
```

---

## Step6. Googleマネージド証明書（DNS認証）発行

### 6-1. DNS認証の作成

```bash
DOMAIN="poc.tetutetu214.com"

# DNS認証リソースを作成
gcloud certificate-manager dns-authorizations create poc-dns-auth \
  --domain="${DOMAIN}"

# CNAMEレコード情報を確認
gcloud certificate-manager dns-authorizations describe poc-dns-auth
```

出力例:

```
dnsResourceRecord:
  data: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.x.authorize.certificatemanager.goog.
  name: _acme-challenge.poc.tetutetu214.com.
  type: CNAME
domain: poc.tetutetu214.com
```

### 6-2. Cloudflare に CNAME レコード追加

1. Cloudflare ダッシュボード → `tetutetu214.com` → DNS
2. 「レコードを追加」をクリック
3. 以下を入力:

| 項目 | 値 |
|---|---|
| タイプ | CNAME |
| 名前 | `_acme-challenge.poc`（上記出力の `name` から `.tetutetu214.com.` を除いた部分） |
| ターゲット | 上記出力の `data` の値（末尾の `.` を除く） |
| プロキシ状態 | **DNS のみ（グレー雲）** ← 重要 |

### 6-3. 証明書の作成

```bash
gcloud certificate-manager certificates create poc-cert \
  --domains="${DOMAIN}" \
  --dns-authorizations=poc-dns-auth
```

### 6-4. 証明書マップの作成

```bash
# 証明書マップ
gcloud certificate-manager maps create poc-cert-map

# 証明書マップエントリ
gcloud certificate-manager maps entries create poc-cert-map-entry \
  --map=poc-cert-map \
  --certificates=poc-cert \
  --hostname="${DOMAIN}"
```

### 6-5. 証明書の発行状態確認

```bash
# ACTIVE になるまで待つ（通常 数分〜数十分）
gcloud certificate-manager certificates describe poc-cert
```

> `state: ACTIVE` になれば証明書の発行は完了。
> `PROVISIONING` の場合は CNAME レコードの反映待ち。

---

## Step7. Cloud Load Balancing 構築（HTTPS）

### 7-1. Serverless NEG 作成

```bash
# フロントエンド用 NEG のみ作成（3層構成）
# バックエンドはフロントエンド(Next.js)経由で内部通信するため NEG 不要
gcloud compute network-endpoint-groups create poc-frontend-neg \
  --region=asia-northeast1 \
  --network-endpoint-type=serverless \
  --cloud-run-service=poc-frontend
```

### 7-2. バックエンドサービス作成

```bash
# フロントエンド用のみ（3層構成）
# LB からはフロントエンドだけに振り分ける
gcloud compute backend-services create poc-frontend-bs \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --global

gcloud compute backend-services add-backend poc-frontend-bs \
  --network-endpoint-group=poc-frontend-neg \
  --network-endpoint-group-region=asia-northeast1 \
  --global
```

### 7-3. URL マップ作成

```bash
# 全パスをフロントエンドに振り分け（3層構成）
# /api/* へのリクエストも一度フロントエンド(Next.js)が受け取り、
# Next.js API Route がバックエンド(FastAPI)に内部通信で中継する
gcloud compute url-maps create poc-url-map \
  --default-service=poc-frontend-bs
```

> **注意:** ヒアドキュメントは `EOF`（クォートなし）で記述すること。
> `'EOF'` にすると `${PROJECT_ID}` が展開されない。

### 7-4. HTTPS プロキシ・転送ルール作成

```bash
# 外部 IP アドレス確保
gcloud compute addresses create poc-lb-ip \
  --network-tier=PREMIUM \
  --ip-version=IPV4 \
  --global

# IP アドレス確認
LB_IP=$(gcloud compute addresses describe poc-lb-ip \
  --global --format='value(address)')
echo "LB_IP=${LB_IP}"

# HTTPS ターゲットプロキシ作成（証明書マップを指定）
gcloud compute target-https-proxies create poc-https-proxy \
  --url-map=poc-url-map \
  --certificate-map=poc-cert-map

# 転送ルール作成（HTTPS: 443）
gcloud compute forwarding-rules create poc-forwarding-rule \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --network-tier=PREMIUM \
  --address=poc-lb-ip \
  --global \
  --target-https-proxy=poc-https-proxy \
  --ports=443
```

### 7-5. Cloudflare に A レコード追加

1. Cloudflare ダッシュボード → `tetutetu214.com` → DNS
2. 「レコードを追加」をクリック

| 項目 | 値 |
|---|---|
| タイプ | A |
| 名前 | `poc` |
| IPv4アドレス | 上記で確認した `LB_IP` の値 |
| プロキシ状態 | **DNS のみ（グレー雲）** ← 重要 |

> **Cloudflare プロキシ（オレンジ雲）は絶対に OFF にすること。**
> ON のままだと Google のマネージド証明書の検証・更新が失敗する。

### 7-6. IAP サービスアカウントに Cloud Run 起動権限付与

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} \
  --format='value(projectNumber)')

# IAP サービスアカウント作成
gcloud beta services identity create \
  --service=iap.googleapis.com \
  --project=${PROJECT_ID}

# フロントエンド Cloud Run への起動権限付与
gcloud run services add-iam-policy-binding poc-frontend \
  --region=asia-northeast1 \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### 7-7. LB 動作確認（認証前）

> LB のプロビジョニングに **5〜10 分** かかる。

```bash
# HTTPS でアクセスできるか確認
curl -I https://poc.tetutetu214.com
```

`200` または `302`（IAP リダイレクト）が返れば LB + HTTPS は正常。

---

## Step8. Azure: Entra ID テナント・アプリ登録

### 8-1. Azure 無料アカウント作成（未作成の場合）

1. https://azure.microsoft.com/ja-jp/pricing/purchase-options/azure-account にアクセス
2. Microsoft アカウント（`@outlook.com` 等）でサインイン
3. 無料アカウントを作成（クレジットカード登録は必要だが、Free 枠内なら課金なし）

### 8-2. Entra ID アプリ登録

1. https://entra.microsoft.com にサインイン
2. 左メニュー →「アプリケーション」→「アプリの登録」→「+ 新規登録」

| 項目 | 設定値 |
|---|---|
| 名前 | `poc-gcp-oidc` |
| サポートされているアカウントの種類 | **この組織ディレクトリのみに含まれるアカウント（シングルテナント）** |
| リダイレクト URI | **後で設定する（Step10 完了後）** |

3. 「登録」をクリック

### 8-3. クライアントID・テナントID をメモ

登録後の「概要」ページから以下をメモする:

| 項目 | メモ先の変数名 |
|---|---|
| アプリケーション（クライアント）ID | `ENTRA_CLIENT_ID` |
| ディレクトリ（テナント）ID | `ENTRA_TENANT_ID` |

### 8-4. クライアントシークレット作成

1. 左メニュー →「証明書とシークレット」
2. 「+ 新しいクライアント シークレット」をクリック

| 項目 | 設定値 |
|---|---|
| 説明 | `poc-secret` |
| 有効期限 | 推奨期間: `6 months`（PoCなので短くてよい） |

3. 「追加」をクリック
4. **「値」をメモする**（この画面を離れると二度と表示されない）

| 項目 | メモ先の変数名 |
|---|---|
| クライアントシークレットの値 | `ENTRA_CLIENT_SECRET` |

### 8-5. Web プラットフォーム追加 + ID トークン有効化

1. 左メニュー →「認証」
2. 「プラットフォームの構成」→「+ プラットフォームを追加」→「Web」を選択
3. 以下を入力:

| 項目 | 設定値 |
|---|---|
| リダイレクト URI | `https://localhost`（仮の値。Step11 で Identity Platform のコールバック URL に差し替える） |
| フロントチャンネルのログアウト URL | 空欄のまま |

4. 「暗黙的な許可およびハイブリッド フロー」セクションで **「ID トークン（暗黙的およびハイブリッド フローに使用）」** にチェック
5. 「構成」をクリック

> **注意:** Web プラットフォーム追加時はリダイレクト URI が必須入力。
> 空欄では保存できないため、仮の値として `https://localhost` を設定する。

---

## Step9. GCP: Identity Platform + OIDC プロバイダ登録

### 9-1. Identity Platform 有効化（API は Step1 で有効化済み）

1. Google Cloud コンソール → [Identity Platform](https://console.cloud.google.com/customer-identity) を開く
2. 初回の場合は「Identity Platform を有効にする」をクリック

### 9-2. OIDC プロバイダ登録

1. [Identity Platform プロバイダページ](https://console.cloud.google.com/customer-identity/providers) を開く
2. 「プロバイダを追加」→「OpenID Connect」を選択

| 項目 | 設定値 |
|---|---|
| 名前 | `microsoft-entra` |
| 付与タイプ | **コードフロー** |
| クライアント ID | Step8-3 でメモした `ENTRA_CLIENT_ID` |
| クライアントシークレット | Step8-4 でメモした `ENTRA_CLIENT_SECRET` |
| 発行者（Issuer） | `https://login.microsoftonline.com/ENTRA_TENANT_ID/v2.0`（テナントID を置換） |

3. 「保存」をクリック

### 9-3. 承認済みドメインの追加

1. [Identity Platform 設定ページ](https://console.cloud.google.com/customer-identity/settings) を開く
2. 「承認済みドメイン」タブ
3. `poc.tetutetu214.com` を追加して保存

### 9-4. コールバック URL の確認

1. プロバイダ一覧で `microsoft-entra` をクリック
2. **コールバック URL** をメモする

```
https://PROJECT_ID.firebaseapp.com/__/auth/handler
```

> この URL は Step11 で Entra ID のリダイレクト URI に設定する。

---

## Step10. GCP: IAP 設定

### 10-1. IAP で外部 ID を有効化

1. [IAP ページ](https://console.cloud.google.com/security/iap) を開く
2. 「アプリケーション」タブで `poc-frontend-bs` を見つける
3. IAP 列のトグルを **ON** にする
4. サイドパネルで「外部IDを使用して承認します」→「開始」をクリック

### 10-2. ログインページ設定

| 項目 | 設定値 |
|---|---|
| ログインページ | **IAPにログインページを作成させる** |
| リージョン | `asia-northeast1` |

### 10-3. プロバイダ選択

1. Identity Platform プロバイダ（プロジェクト名のチェックボックス）にチェック
2. 「保存」をクリック

> IAP が `gcr.io/gcip-iap/authui` イメージを Cloud Run に自動デプロイする。
> 個人環境（VPC SC なし）であれば、数分でプロビジョニングが完了する。

### 10-4. プロビジョニング完了確認

IAP ページで認証 URL が表示されれば完了。

```bash
# IAP が自動作成した Cloud Run サービスを確認
gcloud run services list --region=asia-northeast1
```

`iap-auth-xxxx` のようなサービスが表示される。

---

## Step11. Azure: リダイレクト URI 設定

### 11-1. コールバック URL を Entra ID に登録

1. https://entra.microsoft.com →「アプリの登録」→ `poc-gcp-oidc`
2. 左メニュー →「認証」
3. 「プラットフォームの構成」→「+ プラットフォームを追加」→「Web」

| 項目 | 設定値 |
|---|---|
| リダイレクト URI | Step9-4 でメモしたコールバック URL |

> 例: `https://YOUR_PROJECT_ID.firebaseapp.com/__/auth/handler`

4. 「構成」をクリック

---

## Step12. 動作確認

### 12-1. ブラウザでアクセス

```
https://poc.tetutetu214.com
```

### 12-2. 確認項目

| 確認項目 | 期待される動作 |
|---|---|
| 未認証でアクセス | Entra ID のログイン画面にリダイレクトされる |
| Entra ID でログイン | 1回だけログイン画面が表示される |
| ログイン後 | Next.js の PDF アップロード画面が表示される |
| PDF アップロード | 「アップロード成功」が表示される |
| GCS への保存確認 | 以下コマンドでファイルが確認できる |

```bash
gcloud storage ls gs://${BUCKET_NAME}/uploads/
```

---

## Step13. リソース削除手順

> **LB から順番に削除すること。**

### 13-1. IAP 無効化（LB 削除前に必ず実行）

```bash
gcloud compute backend-services update poc-frontend-bs \
  --iap=disabled \
  --global
```

### 13-2. LB 関連削除

```bash
# 転送ルール
gcloud compute forwarding-rules delete poc-forwarding-rule \
  --global -q

# HTTPS ターゲットプロキシ
gcloud compute target-https-proxies delete poc-https-proxy -q

# URL マップ
gcloud compute url-maps delete poc-url-map --global -q

# バックエンドサービス（3層構成のためフロントエンドのみ）
gcloud compute backend-services delete poc-frontend-bs --global -q

# Serverless NEG（3層構成のためフロントエンドのみ）
gcloud compute network-endpoint-groups delete poc-frontend-neg \
  --region=asia-northeast1 -q

# 外部 IP アドレス（課金対象）
gcloud compute addresses delete poc-lb-ip --global -q
```

### 13-3. 証明書関連削除

```bash
# 証明書マップエントリ
gcloud certificate-manager maps entries delete poc-cert-map-entry \
  --map=poc-cert-map -q

# 証明書マップ
gcloud certificate-manager maps delete poc-cert-map -q

# 証明書
gcloud certificate-manager certificates delete poc-cert -q

# DNS 認証
gcloud certificate-manager dns-authorizations delete poc-dns-auth -q
```

### 13-4. Cloud Run 削除

```bash
gcloud run services delete poc-frontend --region=asia-northeast1 -q
gcloud run services delete poc-backend --region=asia-northeast1 -q

# IAP が自動作成した認証ページも削除
# サービス名は gcloud run services list で確認
gcloud run services list --region=asia-northeast1
# 表示された iap-auth-xxxx を削除
# gcloud run services delete iap-auth-xxxx --region=asia-northeast1 -q
```

### 13-5. GCS・Artifact Registry 削除

```bash
# GCS バケット削除（中のファイルごと削除）
gcloud storage rm -r gs://${BUCKET_NAME}

# Artifact Registry 削除
gcloud artifacts repositories delete poc-repo \
  --location=asia-northeast1 -q
```

### 13-6. サービスアカウント削除

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud iam service-accounts delete \
  poc-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com -q
gcloud iam service-accounts delete \
  poc-frontend-sa@${PROJECT_ID}.iam.gserviceaccount.com -q
```

### 13-7. Azure: Entra ID アプリ削除

1. https://entra.microsoft.com →「アプリの登録」
2. `poc-gcp-oidc` を選択 →「削除」

### 13-8. Cloudflare: DNS レコード削除

1. Cloudflare ダッシュボード → `tetutetu214.com` → DNS
2. 以下のレコードを削除:
   - `_acme-challenge.poc` （CNAME）
   - `poc` （A レコード）

### 13-9. 削除確認

```bash
# Cloud Run 確認（何も表示されなければ OK）
gcloud run services list --region=asia-northeast1

# LB 関連確認
gcloud compute forwarding-rules list --global
gcloud compute addresses list --global

# 証明書確認
gcloud certificate-manager certificates list
```

---

## トラブルシューティング

| エラー | 対処 |
|---|---|
| 証明書が `PROVISIONING` のまま | Cloudflare の CNAME レコードが DNS Only（グレー雲）になっているか確認。プロキシ（オレンジ雲）ON だと検証失敗する |
| `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` | 証明書がまだ `ACTIVE` になっていない。`gcloud certificate-manager certificates describe poc-cert` で確認 |
| `pages or app directory not found` | `frontend/` 直下に `app/` ディレクトリが存在しない。`find` コマンドで構成確認 |
| `moduleResolution=node10 deprecated` | `tsconfig.json` が存在しないか `moduleResolution` が `node10` になっている |
| `PROJECT_ID not found` (url-maps import) | ヒアドキュメントを `'EOF'`（クォートあり）で記述している。`EOF`（クォートなし）に変更 |
| Entra ID ログイン後に 403 | Step7-6 の IAP サービスアカウント権限付与が完了しているか確認 |
| コールバック URI エラー | Step11 のリダイレクト URI が Identity Platform のコールバック URL と一致しているか確認 |
| 承認済みドメインエラー | `poc.tetutetu214.com` が Identity Platform の承認済みドメインに追加されているか確認 |
| 500 Forbidden (GCS) | `poc-backend-sa` に `roles/storage.objectUser` が付与されているか確認 |
| `poc-frontend-bs` が IAP に表示されない | `gcloud services enable iap.googleapis.com` を実行 |
| IAP 認証ページプロビジョニング失敗 | VPC SC 環境の場合は `containerregistry.googleapis.com` と `storage.googleapis.com` の Egress Rule が必要。個人環境では発生しない |

---

## 参考情報

| ドキュメント | URL |
|---|---|
| Google: マネージド証明書（DNS認証） | https://docs.cloud.google.com/certificate-manager/docs/deploy-google-managed-dns-auth |
| Google: DNS認証の管理 | https://docs.cloud.google.com/certificate-manager/docs/dns-authorizations |
| Google: IAP + 外部ID | https://docs.cloud.google.com/iap/docs/enable-external-identities |
| Google: Identity Platform プロバイダ設定 | https://cloud.google.com/identity-platform/docs/how-to |
| Microsoft: Entra ID アプリ登録 | https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app |
| Microsoft: OIDC プロトコル | https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc |