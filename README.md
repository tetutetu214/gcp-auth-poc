# GCP 認証 PoC

Microsoft Entra ID + Google Identity Platform + IAP を使った認証基盤の PoC です。
アプリケーションコードに認証ロジックを一切書かず、インフラレベル（IAP）で認証を強制する構成を検証しています。

**Phase 7（2026-04-19追加）**：Microsoft Graph API による delegated アクセストークン取得とユーザーメール取得も検証済み（`/api/graph/*`）。

## アーキテクチャ

```
ユーザー
  | HTTPS(443)
  v
Cloud Load Balancing (External Application LB) + IAP
  |
  |-- 未認証 --> Identity Platform --> Microsoft Entra ID (OIDC)
  |                                       |
  |                                   ログイン完了
  |                                       |
  |-- 認証済み -----> Cloud Run: poc-frontend (Next.js)
                          |
                          | Direct VPC egress（内部通信）
                          v
                     Cloud Run: poc-backend (FastAPI)
                          |
                          |-- PDFアップロード ---> Google Cloud Storage (uploads/)
                          |
                          |-- メール取得(Graph) ---> Microsoft Graph API
                                 |
                                 |- OAuth2.0 Authz Code Flow
                                 |  (クライアントシークレット: Secret Manager)
                                 |- トークン保管: Firestore (graph_tokens/)
                                 v
                               Google Cloud Storage (mails/)
```

LB → フロントエンド → バックエンドの 3 層アーキテクチャです。
LB からは全パスをフロントエンド（Next.js）に振り分け、Next.js API Route がバックエンド（FastAPI）に内部通信で中継します。
この構成により、バックエンドの API が増えても LB の設定変更は不要です。

## フロー図
<img width="1136" height="547" alt="image" src="https://github.com/user-attachments/assets/37fe5dbf-8154-4a97-9e4e-bf56e3a3916a" />


## 機能

### PDFアップロード（Phase 1〜6）

トップページからPDFを選択してアップロード。バックエンドが Cloud Storage に保存。

### Microsoft Graph API メール取得（Phase 7）

「メール取得」ボタンで OAuth 2.0 Authorization Code Flow を開始：

1. ユーザーが Entra ID で Mail.Read と offline_access に同意
2. FastAPI が認可コードをアクセストークン＋リフレッシュトークンに交換
3. トークンを Firestore に保存（2回目以降は同意不要）
4. Graph API `/me/messages` で直近10件のメールを取得
5. 結果を GCS に JSON として保存（`gs://{BUCKET}/mails/{user}/{timestamp}.json`）

セキュリティ：
- クライアントシークレットは Secret Manager で管理、アプリには Cloud Run `--set-secrets` 経由で注入
- state + HttpOnly / Secure / SameSite=Lax Cookie で CSRF対策
- アクセストークンは Firestore のみに保持、ブラウザには渡さない

## 技術スタック

| レイヤー | 技術 |
| --- | --- |
| フロントエンド | Next.js 14 (App Router) / Cloud Run |
| バックエンド | FastAPI + Python 3.12 / Cloud Run |
| 認証 | Microsoft Entra ID (OIDC) → Identity Platform → IAP |
| 認可（Graph API） | OAuth 2.0 Authorization Code Flow（delegated、Mail.Read）|
| ストレージ | Google Cloud Storage（PDF・取得メールJSON）|
| トークン保管 | Firestore (Native mode, `graph_tokens` コレクション)|
| シークレット保管 | Google Secret Manager |
| SSL | Google マネージド証明書（DNS認証） |
| LB | External Application Load Balancer |
| ドメイン | poc.tetutetu214.com（Cloudflare Registrar 管理） |
| Cloud Run 間通信 | Direct VPC egress + Private Google Access |
| テスト | pytest + respx（バックエンド21テスト）|

## ディレクトリ構成

```
gcp-auth-poc/
├── backend/                    # FastAPI アプリケーション
│   ├── main.py                 # エントリポイント + 既存 /api/upload
│   ├── config.py               # 環境変数ローダ
│   ├── firestore_tokens.py     # Firestoreトークンリポジトリ
│   ├── oauth.py                # OAuth state / 認可URL / トークン交換・リフレッシュ
│   ├── graph_client.py         # Microsoft Graph API (/me/messages)
│   ├── gcs_writer.py           # GCS JSON 保存
│   ├── routes_graph.py         # /api/graph/sync, /api/graph/callback
│   ├── tests/                  # pytest テスト（21件）
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── Dockerfile
│   └── .dockerignore
├── frontend/                   # Next.js アプリケーション
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx            # PDF アップロード + メール取得ボタン
│   │   └── api/
│   │       ├── upload/route.ts           # PDF用プロキシ
│   │       └── graph/
│   │           ├── sync/route.ts         # Graph 起点プロキシ
│   │           └── callback/route.ts     # Entra ID コールバックプロキシ
│   ├── next.config.js
│   ├── package.json
│   ├── tsconfig.json
│   ├── Dockerfile
│   └── .dockerignore
├── docs/                       # プロジェクトドキュメント
│   ├── plan.md                 # 構築計画
│   ├── spec.md                 # 仕様書
│   ├── todo.md                 # タスク管理
│   ├── knowledge.md            # 開発ナレッジ・ハマりポイント
│   └── superpowers/
│       ├── specs/2026-04-19-graph-api-mail-design.md   # Phase 7設計書
│       └── plans/2026-04-19-graph-api-mail.md          # Phase 7実装計画
├── memo.md                     # 構築手順書（Step 1〜19、削除手順含む）
├── CLAUDE.md                   # Claude Code 用プロジェクト設定
└── README.md
```

## セットアップ

詳細な構築手順は [memo.md](memo.md) を参照してください。概要は以下のとおりです。

### 前提条件

- Google Cloud プロジェクト
- Azure アカウント（Entra ID 用。無料枠で可）
- Cloudflare で管理されたドメイン
- gcloud CLI、gh CLI がインストール済み

### 構築フェーズ

| Phase | 内容 | 作業者 |
| --- | --- | --- |
| 1 | Azure 環境構築（Entra ID アプリ登録） | 手動（Azure ポータル） |
| 2 | GCP 基盤準備（API 有効化、GCS、SA、Private Google Access） | gcloud CLI |
| 3 | アプリケーションデプロイ（Artifact Registry、Cloud Run） | gcloud CLI |
| 4 | HTTPS + ドメイン設定（証明書、LB、DNS） | gcloud CLI + 手動（Cloudflare） |
| 5 | 認証連携設定（Identity Platform、IAP、リダイレクト URI） | 手動（GCP コンソール + Azure ポータル） |
| 6 | 動作確認 | ブラウザ |
| **7** | **Graph API メール取得（Secret Manager、Firestore、Graph 認可フロー）** | gcloud CLI + 手動（Entra ID、ブラウザ）|

## 構築時の注意点

### Cloudflare の DNS 設定

Cloudflare のプロキシ状態は必ず **「DNS のみ（グレー雲）」** にすること。オレンジ雲（プロキシ有効）だと Google マネージド証明書の検証・更新が失敗します。

### IAP + 外部 ID 利用時のリダイレクト URI

Identity Platform のプロバイダ設定画面に表示される `https://{PROJECT_ID}.firebaseapp.com/__/auth/handler` は、IAP 経由で使う場合のコールバック URL ではありません。IAP が自動作成した認証ページ用 Cloud Run の URL（`https://iap-gcip-hosted-ui-{名前}.a.run.app/__/auth/handler`）を Entra ID のリダイレクト URI に登録する必要があります。

### Cloud Run 間の内部通信

Cloud Run はデフォルトで VPC の外に存在します。Cloud Run 同士で `ingress=internal` を使った内部通信をするには、以下の 3 つの設定が必要です。

1. 呼び出し元に Direct VPC egress を設定（`--network`, `--subnet`, `--vpc-egress=all-traffic`）
2. 対象サブネットの Private Google Access を有効化
3. 呼び出し先の `ingress=internal` はそのまま

Private Google Access が無効だと `ETIMEDOUT` エラーになります。

### IAP + 外部 ID（Entra ID）利用時の特殊事情（Phase 7）

Identity Platform 経由で外部 IDを使う構成では、以下の挙動に注意が必要です（詳細は `docs/knowledge.md`）：

- `X-Goog-Authenticated-User-Email` / `X-Goog-IAP-JWT-Assertion` ヘッダは**付与されない**。ユーザー識別は `GCP_IAP_UID` Cookie から行う
- Firestore のドキュメントIDに `/` は使えないためサニタイズ必要
- 個人 Microsoft アカウントで `/me/messages` を使うにはアプリをマルチテナント化＋アプリマニフェストで `requestedAccessTokenVersion: 2`＋authorize/token エンドポイントを `/common` に切替

## リソース削除

PoC 完了後は [memo.md の Step13](memo.md#step13-リソース削除手順) に従ってリソースを削除してください。LB 関連は時間課金のため、不要になったら速やかに削除することを推奨します。

## ランニングコスト概算

| リソース | 費用（1週間） |
| --- | --- |
| LB 転送ルール | 約 $4.20 |
| 外部静的 IP | 約 $0.84 |
| Cloud Run / GCS | ほぼ $0（低トラフィック時） |
| **合計** | **約 $5/週** |
