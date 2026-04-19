# 開発ナレッジ

## 決定事項

### 2026-04-19: プロジェクト初期化
- memo.md（てつてつさん作成の手順書）をベースにプロジェクト構造を整備
- フォルダ名は `gcp-auth-poc` に決定
- インフラ構築は gcloud CLI 手動実行方式（Terraform等は使わない）
- Azure環境は未構築。アカウント作成から必要（Phase 1 として最初に実施）
- Azure無料アカウントにはクレジットカード登録が必要だが、Entra IDはFree枠に含まれる

### 2026-04-19: 3層構成への設計変更
- 当初の memo.md ではLBのパスルーティング（`/api/*` → バックエンド）で構成していた
- 今後 Gemini 呼び出し、Outlook メール取得など FastAPI の機能が拡充する予定があるため、LBからは全パスをフロントエンドに振り分ける構成に変更
- 構成: LB → フロントエンド(Next.js) → バックエンド(FastAPI) の3層アーキテクチャ。Next.js API Route がバックエンドへのプロキシ（集約層）として機能
- これにより機能追加時にLBの設定変更が不要になる（route.ts の追加だけで済む）
- バックエンドCloud Runは `--allow-unauthenticated` + `--ingress=internal` に変更（内部通信のみ受付）
- **注意: この構成は「BFF（Backend For Frontend）」ではない。** BFFは「クライアント種別ごとに専用バックエンドを用意する」パターンであり、フロントエンドが1つの場合は該当しない（Microsoft Learn、Sam Newman氏の定義に基づく）

## 注意事項（memo.md から抽出）

- Cloudflare のプロキシ状態は必ず「DNS のみ（グレー雲）」にすること。オレンジ雲だと Google マネージド証明書の検証・更新が失敗する
- Entra ID のクライアントシークレットは作成画面を離れると二度と表示されない。必ずその場でメモする
- LB のプロビジョニングには 5〜10 分かかる
- リソース削除は LB から順番に行うこと

## ハマりポイント

### 2026-04-19: Entra ID の Web プラットフォーム追加時にリダイレクトURIが必須
- Entra ID の「認証」→「プラットフォームを追加」→「Web」の画面で、リダイレクトURIが空だと保存できない
- IDトークンの有効化はこのプラットフォーム追加画面内で行うため、プラットフォーム追加をスキップできない
- 対処: 仮の値 `https://localhost` を設定し、Phase 5（Step 11）で Identity Platform のコールバックURLに差し替える

### 2026-04-19: IAP + 外部ID 利用時のコールバックURLは firebaseapp.com ではない

- Identity Platform のプロバイダ設定画面には `https://{PROJECT_ID}.firebaseapp.com/__/auth/handler` が表示される
- しかし IAP が外部IDを使う構成では、IAP が自動作成した認証ページ用 Cloud Run のURLがコールバックURLとして使われる
- 実際のURL形式: `https://iap-gcip-hosted-ui-{バックエンドサービス名}-{ランダム}.a.run.app/__/auth/handler`
- Entra ID のリダイレクトURIには firebaseapp.com ではなく、IAP が生成した Cloud Run のURLを登録すること
- エラーメッセージ: `AADSTS50011: The redirect URI ... does not match the redirect URIs configured`

### 2026-04-19: Cloud Run 間の内部通信には Private Google Access が必要

- Cloud Run はデフォルトではVPCの外に存在するサーバーレスサービス
- Cloud Run 同士で `ingress=internal` を使った内部通信をするには、以下の3つが必要:
  1. 呼び出し元に Direct VPC egress を設定（`--network`, `--subnet`, `--vpc-egress=all-traffic`）
  2. 対象サブネットの **Private Google Access を有効化**（`gcloud compute networks subnets update --enable-private-ip-google-access`）
  3. 呼び出し先の `ingress=internal` はそのまま
- Private Google Access が無効だと `ETIMEDOUT` エラーになる（VPC内から Google サービスにアクセスできない）
- Private Google Access の有効化に追加コストはかからない
