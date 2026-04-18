# 認証PoC 仕様書

## 認証仕様

### 認証フロー

ユーザーがアプリにアクセスすると、IAP が認証状態を自動チェックする。未認証の場合は Identity Platform の認証ページ（IAP が自動生成）にリダイレクトされ、そこから Entra ID のログイン画面に遷移する。ログイン完了後、ブラウザにセッションクッキーが保存され、以降のリクエストは認証済みとして通過する。

アプリケーションコード側には認証ロジックを一切実装しない。認証の強制はすべて IAP（LBレベル）で行う。

### Entra ID 設定

| 項目 | 値 |
| --- | --- |
| アプリ名 | `poc-gcp-oidc` |
| アカウントの種類 | シングルテナント（この組織ディレクトリのみ） |
| 付与タイプ | コードフロー |
| IDトークン | 暗黙的およびハイブリッドフローで有効化 |
| クライアントシークレット有効期限 | 6ヶ月（PoC用途） |

### Identity Platform 設定

| 項目 | 値 |
| --- | --- |
| プロバイダ種別 | OpenID Connect |
| プロバイダ名 | `microsoft-entra` |
| 発行者（Issuer） | `https://login.microsoftonline.com/{TENANT_ID}/v2.0` |
| 承認済みドメイン | `poc.tetutetu214.com` |

### IAP 設定

| 項目 | 値 |
| --- | --- |
| 対象バックエンドサービス | `poc-frontend-bs` |
| ログインページ | IAP に自動生成させる |
| ログインページリージョン | `asia-northeast1` |
| 外部ID | Identity Platform のプロバイダを使用 |

---

## API仕様

### バックエンド（FastAPI）

バックエンドは Cloud Run 上で動作し、LB 経由の `/api/*` パスでアクセスされる。ingress は `internal` に設定し、LB 経由以外のアクセスを遮断する。

#### GET /health

ヘルスチェック用エンドポイント。

**レスポンス:**
```json
{"status": "ok"}
```

#### POST /api/upload

PDFファイルをGCSにアップロードする。

**リクエスト:**
- Content-Type: `multipart/form-data`
- フィールド名: `file`
- 許可する Content-Type: `application/pdf` のみ

**成功レスポンス（200）:**
```json
{
    "message": "アップロード成功",
    "filename": "example.pdf"
}
```

**エラーレスポンス（400）:**
```json
{
    "detail": "PDFファイルのみ受け付けます"
}
```

**GCS保存先:** `gs://{BUCKET_NAME}/uploads/{filename}`

### フロントエンド API Route（Next.js）

#### POST /api/upload（プロキシ）

フロントエンドの Next.js API Route がバックエンドの `/api/upload` にリクエストを中継する。ユーザーのブラウザからは直接バックエンドにアクセスせず、Next.js がプロキシとして機能する。

---

## 画面仕様

### トップページ（`/`）

認証検証用のシンプルなPDFアップロード画面。

**画面要素:**
- ページタイトル: 「PDF アップロード PoC」
- ファイル選択ボタン: PDFファイルのみ選択可能（`accept="application/pdf"`）
- アップロードボタン: クリックで `/api/upload` に POST
- 状態表示: アップロード中は「アップロード中...」、完了後は結果メッセージを表示

**UIライブラリ:** 使用しない（素のHTML + インラインスタイル。PoCのため最小構成）

---

## インフラ仕様

### Cloud Run サービス

| サービス | イメージ | ポート | ingress | max-instances | SA |
| --- | --- | --- | --- | --- | --- |
| poc-backend | backend:latest | 8080 | internal | 3 | poc-backend-sa |
| poc-frontend | frontend:latest | 8080 | internal-and-cloud-load-balancing | 3 | poc-frontend-sa |

### サービスアカウント

| SA名 | 役割 | 権限 |
| --- | --- | --- |
| poc-backend-sa | バックエンド用 | GCSバケットへの `roles/storage.objectUser` |
| poc-frontend-sa | フロントエンド用 | 追加権限なし（最小権限の原則） |

### GCS バケット

| 項目 | 値 |
| --- | --- |
| バケット名 | `poc-upload-{PROJECT_ID}` |
| ロケーション | `asia-northeast1` |
| アクセス制御 | 均一バケットレベルアクセス |

### Load Balancer

| 項目 | 値 |
| --- | --- |
| スキーム | EXTERNAL_MANAGED |
| IPバージョン | IPv4（PREMIUM ネットワークティア） |
| URLマップ | `/*` → poc-frontend-bs、`/api/*` → poc-backend-bs |
| SSL | Googleマネージド証明書（DNS認証） |

### Artifact Registry

| 項目 | 値 |
| --- | --- |
| リポジトリ名 | `poc-repo` |
| フォーマット | Docker |
| ロケーション | `asia-northeast1` |

### DNS（Cloudflare）

| レコード | タイプ | 名前 | 値 | プロキシ |
| --- | --- | --- | --- | --- |
| 証明書検証用 | CNAME | `_acme-challenge.poc` | Certificate Manager が発行する値 | DNS のみ（グレー雲） |
| LB向け | A | `poc` | LB の外部IPアドレス | DNS のみ（グレー雲） |
