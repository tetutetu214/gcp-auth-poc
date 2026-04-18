# タスク管理

## 進行中

- [ ] plan.md の確認待ち（てつてつさんの承認）

## 未着手

### Phase 1: Azure環境構築（てつてつさん手動作業）

- [ ] Azure無料アカウント作成
- [ ] Entra ID アプリ登録（`poc-gcp-oidc`）
- [ ] クライアントID・テナントIDをメモ
- [ ] クライアントシークレット作成・メモ（画面を離れると二度と表示されない）
- [ ] IDトークン有効化

### Phase 2: GCP基盤準備

- [ ] GCPプロジェクト設定・API有効化
- [ ] GCSバケット作成
- [ ] サービスアカウント作成・権限付与

### Phase 3: アプリケーション構築・デプロイ

- [ ] バックエンド（FastAPI）コード作成
- [ ] バックエンド Dockerfile 作成
- [ ] Artifact Registry リポジトリ作成
- [ ] バックエンド Cloud Run デプロイ
- [ ] フロントエンド（Next.js）コード作成
- [ ] フロントエンド Dockerfile 作成
- [ ] フロントエンド Cloud Run デプロイ

### Phase 4: HTTPS + ドメイン設定

- [ ] Googleマネージド証明書発行（DNS認証）
- [ ] Cloudflare CNAMEレコード追加（てつてつさん手動）
- [ ] Cloud Load Balancing 構築
- [ ] Cloudflare Aレコード追加（てつてつさん手動）

### Phase 5: 認証連携設定

- [ ] GCP Identity Platform 有効化 + OIDCプロバイダ登録（てつてつさん手動）
- [ ] IAP 有効化・設定（てつてつさん手動）
- [ ] Entra ID にリダイレクトURI追加（てつてつさん手動）

### Phase 6: 動作確認

- [ ] E2E動作確認
- [ ] リソース削除手順の検証

## 完了

- [x] プロジェクトフォルダ作成・Git初期化
- [x] docs/ 配下のドキュメント整備
- [x] CLAUDE.md 作成
