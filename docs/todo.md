# タスク管理

## 進行中

### Phase 3: アプリケーション構築・デプロイ

- [x] バックエンド（FastAPI）コード作成
- [x] バックエンド Dockerfile 作成
- [ ] Artifact Registry リポジトリ作成
- [ ] バックエンド Cloud Run デプロイ
- [x] フロントエンド（Next.js）コード作成
- [x] フロントエンド Dockerfile 作成
- [ ] フロントエンド Cloud Run デプロイ

## 未着手

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
- [x] plan.md の確認（承認済み）
- [x] spec.md の確認（承認済み）
- [x] Phase 1: Azure環境構築（アカウント作成、Entra IDアプリ登録、シークレット取得、IDトークン有効化）
- [x] Phase 2: GCP基盤準備（API有効化、GCSバケット作成、SA作成・権限付与）
