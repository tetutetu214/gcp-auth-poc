# Microsoft Graph API メール取得機能 設計書

- 作成日：2026-04-19
- 対象ブランチ：`feature/graph-api-mail`
- 対象リポジトリ：既存の `gcp-auth-poc` に追加（フォークしない）

---

## 1. 目的

既存の認証PoC（Entra ID + Identity Platform + IAP）に、**Microsoft Graph API でユーザーのメール情報を取得できること**を検証する機能を追加する。

既存の IAP はユーザーの「認証（AuthN）」を担っており、Microsoft のアクセストークンはアプリに渡らない。そのため Graph API を呼ぶには、アプリが独自に OAuth 2.0 Authorization Code Flow を実装し、ユーザーから明示的な「認可（AuthZ）」を受ける必要がある。この設計書ではその検証構成を定義する。

---

## 2. 背景

| 要素 | 既存PoC | 本設計で追加 |
|---|---|---|
| ユーザー認証（AuthN） | IAP + Identity Platform が代行 | 変更なし |
| ユーザー認可（AuthZ）＝ Graph API 権限 | なし | **Entra ID から delegated access token を取得** |
| クライアントシークレット保管 | Identity Platform が保持（コンソール登録） | **Secret Manager に別途保管**（FastAPI が参照） |
| ユーザートークン保管 | — | **Firestore**（アクセストークン＋リフレッシュトークン） |
| 取得データの保管 | — | **GCS**（既存バケットを流用） |

---

## 3. アーキテクチャ

### 3.1 全体構成図

```
ユーザー
  │ ①「メール取得」ボタンクリック
  v
Cloud Load Balancer + IAP（既存）
  │
  v
Cloud Run: poc-frontend（Next.js）
  │ ②プロキシとして FastAPI に転送
  v
Cloud Run: poc-backend（FastAPI）
  │
  ├─ ③ Firestore でトークン確認
  │      └─ トークンあり → ⑦へ
  │      └─ トークンなし → ④へ
  │
  ├─ ④ Entra ID 認可URL を生成してブラウザにリダイレクト
  │
  ├─ ⑤ ユーザーが Entra ID で同意
  │      └─ 認可コード付きで /api/graph/callback にリダイレクト（Next.js着地）
  │      └─ Next.js が FastAPI に code を転送
  │
  ├─ ⑥ FastAPI が Secret Manager からシークレット取得 → Entra ID とトークン交換
  │      └─ アクセストークン＋リフレッシュトークンを Firestore に保存
  │
  ├─ ⑦ アクセストークンで Microsoft Graph API `/me/messages` を呼ぶ
  │      └─ 失効していたらリフレッシュトークンで自動更新
  │
  └─ ⑧ 取得したメール情報を GCS に JSON で保存
         └─ フロントに「取得件数」「保存先パス」を返す
```

### 3.2 役割分担の原則

| レイヤー | 既存PoCでの役割 | 本機能での役割 |
|---|---|---|
| Next.js | UI とバックエンドへのプロキシ | 同じ（「メール取得」ボタン追加、2つのプロキシRoute追加） |
| FastAPI | 業務処理と外部 I/O | 同じ（OAuth トークン交換、Graph 呼び出し、GCS 保存） |

**クライアントシークレットは FastAPI 側にしか配置しない。** Next.js はコールバック URL で `code` を受け取って FastAPI へ流すだけで、シークレットには触れない。

### 3.3 なぜコールバックが Next.js を経由するか

既存 LB の URLマップは `/*` をすべて Next.js に振り分けており、FastAPI は `ingress=internal` のためインターネットから直接到達できない。Entra ID からのリダイレクト先は外部到達可能な URL でなければならないため、必然的に Next.js 側が入口になる。

---

## 4. 認証・認可フロー詳細

### 4.1 OAuth 2.0 Authorization Code Flow

```
（1）ユーザーがNext.jsのボタンを押す
       fetch GET /api/graph/sync
         │
         v
（2）Next.js → FastAPI：GET /api/graph/sync
         │
         v
（3）FastAPI：Firestore で IAP メールをキーにトークン検索
       - あり → （9）へジャンプ
       - なし → （4）へ

（4）FastAPI：認可URLを JSON で返却（ステータス 200）
       {
         "status": "auth_required",
         "authorize_url":
           "https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize
              ?client_id={CLIENT_ID}
              &response_type=code
              &redirect_uri=https://poc.tetutetu214.com/api/graph/callback
              &response_mode=query
              &scope=openid profile email offline_access Mail.Read
              &state={CSRF対策用ランダム文字列}"
       }
       ※ HTTP 302 ではなく JSON で返す理由：
          ブラウザの fetch() はクロスオリジンの 302 を自動で辿らないため、
          フロント側の JS で window.location.href に代入して遷移させる
         │
         v
（5）ブラウザが authorize_url に遷移 → ユーザーがログイン＆同意
         │
         v
（6）Entra ID が ?code=XYZ&state=... でリダイレクト
       https://poc.tetutetu214.com/api/graph/callback?code=XYZ&state=...
         │
         v
（7）Next.js の /api/graph/callback Route：
       code と state を FastAPI に転送
         │
         v
（8）FastAPI：
       - state を検証（CSRF 対策）
       - Secret Manager から CLIENT_SECRET を取得
       - POST https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token
             grant_type=authorization_code
             client_id={CLIENT_ID}
             client_secret={CLIENT_SECRET}
             code=XYZ
             redirect_uri=...
       - アクセストークン + リフレッシュトークンを受け取る
       - Firestore にユーザーメールをキーに保存
       - 元のページにリダイレクト

（9）FastAPI：Graph API を呼ぶ
       - アクセストークンが有効期限内 → そのまま使う
       - 失効していたら → リフレッシュトークンで再発行
       - GET https://graph.microsoft.com/v1.0/me/messages?$top=10&$select=subject,from,receivedDateTime,bodyPreview
       - 失効はアクセストークンの exp をチェック or 401 応答で検知

（10）FastAPI：取得データを GCS に保存
       gs://poc-upload-{PROJECT_ID}/mails/{user-email}/{YYYYMMDD-HHMMSS}.json

（11）FastAPI → Next.js → ブラウザ：
       {"count": 10, "path": "gs://..."} を返す
```

### 4.2 state パラメータによる CSRF 対策

- `state` には 32バイトのランダム文字列を生成
- 認可URLにセットすると同時に、HttpOnly Cookie にも保存
- コールバックで受け取った `state` と Cookie の値が一致することを検証

### 4.3 scope の内訳

| scope | 目的 |
|---|---|
| `openid` | OIDC 準拠。ID トークン取得に必要 |
| `profile` | ユーザー名などの基本プロファイル |
| `email` | ユーザーのメールアドレス（IDトークン内） |
| `offline_access` | **リフレッシュトークンの発行を有効化** |
| `Mail.Read` | **Graph API でメールを読む** |

---

## 5. コンポーネント設計

### 5.1 Entra ID アプリ登録の変更

既存の `poc-gcp-oidc` アプリに以下を**追加**する（新規アプリは作らない）。

| 項目 | 追加内容 |
|---|---|
| API のアクセス許可 | Microsoft Graph → Delegated → `Mail.Read`、`offline_access`（追加、ユーザー同意で可） |
| リダイレクトURI | `https://poc.tetutetu214.com/api/graph/callback` を追加 |
| 既存のクライアントシークレット | 再利用可。新規発行しない |

### 5.2 Secret Manager

| 項目 | 値 |
|---|---|
| シークレット名 | `poc-entra-client-secret` |
| 値 | Entra ID アプリの既存クライアントシークレット |
| アクセス権 | `poc-backend-sa` に `roles/secretmanager.secretAccessor` |
| Cloud Run 連携方式 | `gcloud run deploy --set-secrets=ENTRA_CLIENT_SECRET=poc-entra-client-secret:latest` |

### 5.3 Firestore

| 項目 | 値 |
|---|---|
| データベースモード | Native mode |
| ロケーション | `asia-northeast1`（既存リソースと同リージョン） |
| データベース名 | `(default)` |
| コレクション | `graph_tokens` |
| ドキュメントID | ユーザーのメールアドレス（例：`taro.yamada@example.com`） |
| アクセス権 | `poc-backend-sa` に `roles/datastore.user` |

#### ドキュメントスキーマ

```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "M.C1...",
  "expires_at": "2026-04-19T10:30:00Z",
  "scope": "openid profile email offline_access Mail.Read",
  "updated_at": "2026-04-19T09:30:00Z"
}
```

### 5.4 FastAPI（バックエンド）

既存 `backend/main.py` に新規エンドポイントを追加。

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/api/graph/sync` | ボタン起点。トークン確認して「メール取得」or「認可URL返却」を分岐 |
| GET | `/api/graph/callback` | Next.js から転送された `code` をトークン交換し Firestore 保存 |

#### 追加する Python パッケージ

```
google-cloud-firestore==2.18.0
google-cloud-secret-manager==2.20.0
httpx==0.27.0
```

※ Graph API は SDK を使わず `httpx` で直接叩く（学習目的と依存の軽さのため）

#### 必要な環境変数

| 変数名 | 値 | 取得元 |
|---|---|---|
| `BUCKET_NAME` | 既存 | 既存環境変数 |
| `ENTRA_TENANT_ID` | Entra ID テナントID | Cloud Run 環境変数（公開情報） |
| `ENTRA_CLIENT_ID` | Entra ID クライアントID | Cloud Run 環境変数（公開情報） |
| `ENTRA_CLIENT_SECRET` | Entra ID クライアントシークレット | **Secret Manager 参照** |
| `REDIRECT_URI` | `https://poc.tetutetu214.com/api/graph/callback` | Cloud Run 環境変数 |

### 5.5 Next.js（フロントエンド）

#### 追加するファイル・変更箇所

| 変更 | 内容 |
|---|---|
| `app/page.tsx` | 既存のPDFアップロードUIはそのまま残し、「メール取得」ボタンを追加 |
| `app/api/graph/sync/route.ts`（新規） | GET を受けて FastAPI の `/api/graph/sync` にプロキシ。302 が返ったらそのままリダイレクトを伝える |
| `app/api/graph/callback/route.ts`（新規） | GET を受けて `code` と `state` を FastAPI に転送 |

Next.js から FastAPI への通信は既存の `BACKEND_URL` 環境変数を流用。

### 5.6 GCS

既存バケット `poc-upload-{PROJECT_ID}` を流用。パスプレフィックスで分離する。

```
gs://poc-upload-{PROJECT_ID}/
  ├── uploads/    （既存：PDFアップロード用）
  └── mails/      （新規：Graph取得メール保存用）
       └── {user-email}/
             └── {YYYYMMDD-HHMMSS}.json
```

既存の `poc-backend-sa` は `roles/storage.objectUser` を持つため、権限追加は不要。

---

## 6. API 仕様

### 6.1 GET /api/graph/sync（FastAPI）

**役割：** トークン状態を判定し、メール取得 or 認可URLリダイレクトに分岐する。

**リクエスト：** なし（IAP JWT は Cloud Run がヘッダで注入。`X-Goog-Authenticated-User-Email` からユーザーメアドを取得）

**レスポンスパターン：**

1. **トークンありの場合（メール取得成功）：**
   - ステータス `200`
   - ボディ：
     ```json
     {
       "status": "ok",
       "count": 10,
       "gcs_path": "gs://poc-upload-{PROJECT_ID}/mails/user@example.com/20260419-093045.json"
     }
     ```

2. **トークンなし／認可が必要な場合：**
   - ステータス `200`（302 ではなく JSON で返す。フロントでJS経由でリダイレクトするため）
   - ボディ：
     ```json
     {
       "status": "auth_required",
       "authorize_url": "https://login.microsoftonline.com/..."
     }
     ```

3. **エラー：**
   - ステータス `500` + `{"detail": "エラー詳細"}`

### 6.2 GET /api/graph/callback（FastAPI）

**役割：** Entra ID からの認可コードを受け取ってトークン交換し、Firestore に保存。

**リクエストクエリ：**
- `code`（必須）：認可コード
- `state`（必須）：CSRF 検証用

**レスポンス：**
- 成功時：302 リダイレクト → `/`
- state 不一致：400
- トークン交換失敗：500

### 6.3 Next.js API Route

`app/api/graph/sync/route.ts` と `app/api/graph/callback/route.ts` は FastAPI の同名エンドポイントにプロキシするだけ。IAP ヘッダや Cookie は透過的に転送する。

---

## 7. 画面仕様

### 7.1 トップページ（`/`）

既存のPDFアップロードUIに「メール取得」セクションを追加。

```
┌─────────────────────────────────┐
│  PDF アップロード PoC            │
│  [ファイル選択] [アップロード]   │
│                                 │
│  ─────────────────────────      │
│                                 │
│  メール取得 PoC                  │
│  [メールを取得]                  │
│  取得結果：（空 / 結果メッセージ）│
└─────────────────────────────────┘
```

**挙動：**
1. 「メールを取得」をクリック → `GET /api/graph/sync`
2. レスポンスが `status: "ok"` → 「10件取得しました。GCSパス: ...」を表示
3. レスポンスが `status: "auth_required"` → `window.location.href = authorize_url` でEntra IDへ遷移
4. Entra ID 同意後、自動で元のページに戻ってくる（このとき再度ボタンを押すとメール取得される）

---

## 8. エラーハンドリング・失効対応

### 8.1 アクセストークン失効

- `expires_at < now` の場合は自動的にリフレッシュトークンで再発行
- リフレッシュ成功 → Firestore 更新 → そのまま Graph 呼び出し続行

### 8.2 リフレッシュトークン失効（約90日）

- リフレッシュ自体が失敗した場合、Firestore のエントリを削除 → 次回は新規認可フローへ
- ユーザーは「メールを取得」ボタンを押すと Entra ID に再誘導される

### 8.3 Graph API エラー

| HTTP status | 対処 |
|---|---|
| 401 | トークン失効とみなし、リフレッシュして1回だけリトライ |
| 403 | 権限不足（scope 不備）。ユーザーに再認可を促す |
| 429 | レート制限。PoCではエラーをそのまま返す |
| その他 | ログ出力してエラーを返す |

---

## 9. セキュリティ設計

| 項目 | 対策 |
|---|---|
| クライアントシークレット漏洩 | Secret Manager に保管、IAM 最小権限、コード・ログに出力しない |
| アクセストークン漏洩 | ブラウザには一切渡さない（Firestore にのみ保管） |
| CSRF | `state` パラメータ + HttpOnly Cookie で検証 |
| 認可コード傍受 | HTTPS 強制（既存 LB で担保） |
| IAP バイパス | FastAPI は `ingress=internal` 維持、認可系エンドポイントも同様 |
| トークン長期保持 | リフレッシュトークンは Firestore のみ、暗号化はGCPの保管時暗号化に依存（PoCとして受容） |

---

## 10. インフラ変更点（新規追加リソース）

| リソース | 新規追加 | 備考 |
|---|---|---|
| Secret Manager API | 有効化 | `secretmanager.googleapis.com` |
| Firestore API | 有効化 | `firestore.googleapis.com` |
| Secret Manager シークレット | `poc-entra-client-secret` | 値は Entra ID の既存シークレット |
| Firestore データベース | `(default)`（Native mode） | リージョン `asia-northeast1` |
| IAM：`poc-backend-sa` | `roles/secretmanager.secretAccessor` と `roles/datastore.user` 追加 | |
| Entra ID アプリ | リダイレクトURI 1件追加、API権限 `Mail.Read` `offline_access` 追加 | 既存アプリを流用 |

削除時は既存の Step13 に追記する必要あり（別途 memo.md 更新）。

---

## 11. 既存PoCへの影響

| 既存機能 | 影響 |
|---|---|
| IAP による認証 | **影響なし**。Graph は IAP 通過後のアプリ内処理 |
| PDF アップロード | **影響なし**。同じバケットのプレフィックス違いで共存 |
| Cloud Run の ingress 設定 | 変更なし |
| LB の URLマップ | 変更なし（既存の `/*` → Next.js で全て賄える） |
| Entra ID アプリ登録 | **追記のみ**（既存設定は保持） |

---

## 12. テスト・動作確認シナリオ

| # | シナリオ | 期待結果 |
|---|---|---|
| 1 | 初回「メール取得」クリック | Entra ID 同意画面にリダイレクトされる |
| 2 | 同意後、自動で元ページに戻る | 戻ってくる。再度ボタン→10件取得成功 |
| 3 | 2回目以降の「メール取得」 | 同意画面なしで直接10件取得 |
| 4 | Firestore に access_token, refresh_token, expires_at が保存 | GCP コンソールで確認 |
| 5 | GCS にメール JSON が保存 | `mails/{email}/{timestamp}.json` を確認 |
| 6 | アクセストークン失効後に取得 | 裏でリフレッシュされ、エラーなく取得できる |
| 7 | 別ユーザーでログイン | 同意画面 → その人のメールが取得される |
| 8 | state 不一致（手動で書き換え） | 400 エラー |

---

## 13. 対象外（非スコープ）

以下は PoC の目的を超えるため本設計書では扱わない：

- メール本文の全文取得（`bodyPreview` のみ）
- 添付ファイルの取得
- 取得したメールのフロントエンド表示（GCS 保存のみで、ブラウザにはパスと件数だけ返す）
- トークンの暗号化保存（Firestore 側の保管時暗号化に依存）
- 複数ユーザーの同時並行処理の性能検証
- メール取得のジョブ化・定期実行

---

## 14. 会社環境への移植

本PoCは個人GCP＋個人Entra IDで構築する。会社環境に移植する際は、以下を会社側の値に差し替える：

| 項目 | 個人環境 | 会社環境で差し替え |
|---|---|---|
| `PROJECT_ID` | 個人プロジェクト | 会社プロジェクト |
| ドメイン | `poc.tetutetu214.com` | 会社ドメイン |
| Entra ID テナントID | 個人テナント | 会社テナント |
| Entra ID アプリ登録 | 個人で作成 | 会社 IT 部門に依頼または権限があれば自前 |
| Firestore ロケーション | `asia-northeast1` | 会社ポリシーに準拠 |
| Secret Manager のシークレット値 | 個人アプリのシークレット | 会社アプリのシークレット |

**手順書（memo.md）側では、環境変数化して差し替え可能な構成にすることで移植コストを下げる。**

---

## 15. 参考情報

- [Microsoft identity platform: OAuth 2.0 Authorization Code Flow](https://learn.microsoft.com/ja-jp/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft Graph: List messages](https://learn.microsoft.com/ja-jp/graph/api/user-list-messages)
- [Google Cloud Secret Manager: Cloud Run integration](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Google Cloud Firestore: Native mode](https://cloud.google.com/firestore/docs/firestore-or-datastore)
