# GCP 認証 PoC

Microsoft Entra ID + Google Identity Platform + IAP を使った認証基盤の PoC です。
アプリケーションコードに認証ロジックを一切書かず、インフラレベル（IAP）で認証を強制する構成を検証しています。

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
                          v
                     Google Cloud Storage
```

LB → フロントエンド → バックエンドの 3 層アーキテクチャです。
LB からは全パスをフロントエンド（Next.js）に振り分け、Next.js API Route がバックエンド（FastAPI）に内部通信で中継します。
この構成により、バックエンドの API が増えても LB の設定変更は不要です。

## 技術スタック

| レイヤー | 技術 |
| --- | --- |
| フロントエンド | Next.js 14 (App Router) / Cloud Run |
| バックエンド | FastAPI + Python 3.12 / Cloud Run |
| 認証 | Microsoft Entra ID (OIDC) → Identity Platform → IAP |
| ストレージ | Google Cloud Storage |
| SSL | Google マネージド証明書（DNS認証） |
| LB | External Application Load Balancer |
| ドメイン | poc.tetutetu214.com（Cloudflare Registrar 管理） |
| Cloud Run 間通信 | Direct VPC egress + Private Google Access |

## ディレクトリ構成

```
gcp-auth-poc/
├── backend/           # FastAPI アプリケーション
│   ├── main.py        # API エンドポイント（/health, /api/upload）
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/          # Next.js アプリケーション
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx           # PDF アップロード画面
│   │   └── api/upload/
│   │       └── route.ts       # バックエンドへのプロキシ
│   ├── next.config.js
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/              # プロジェクトドキュメント
│   ├── plan.md        # 構築計画
│   ├── spec.md        # 仕様書
│   ├── todo.md        # タスク管理
│   └── knowledge.md   # 開発ナレッジ・ハマりポイント
├── memo.md            # 構築手順書（全ステップ）
├── CLAUDE.md          # Claude Code 用プロジェクト設定
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

## リソース削除

PoC 完了後は [memo.md の Step13](memo.md#step13-リソース削除手順) に従ってリソースを削除してください。LB 関連は時間課金のため、不要になったら速やかに削除することを推奨します。

## ランニングコスト概算

| リソース | 費用（1週間） |
| --- | --- |
| LB 転送ルール | 約 $4.20 |
| 外部静的 IP | 約 $0.84 |
| Cloud Run / GCS | ほぼ $0（低トラフィック時） |
| **合計** | **約 $5/週** |
