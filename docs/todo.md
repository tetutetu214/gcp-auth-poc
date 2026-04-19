# タスク管理

## 未着手（Phase 7：Microsoft Graph API メール取得機能）

設計書：`docs/superpowers/specs/2026-04-19-graph-api-mail-design.md`
手順書：`memo.md` Step 14〜19

- [ ] `feature/graph-api-mail` ブランチを切る
- [ ] Step 14: Entra ID アプリに `Mail.Read` / `offline_access` とリダイレクト URI を追加
- [ ] Step 15: Secret Manager にクライアントシークレット登録 + `poc-backend-sa` へ権限付与
- [ ] Step 16: Firestore データベース作成 + `poc-backend-sa` へ権限付与
- [ ] Step 17: FastAPI に `/api/graph/sync`、`/api/graph/callback` 実装 + 再デプロイ
- [ ] Step 18: Next.js に「メール取得」ボタン・プロキシ Route 追加 + 再デプロイ
- [ ] Step 19: E2E 動作確認（初回同意 → 取得 → 2回目同意なし取得 → Firestore/GCS 中身確認）
- [ ] 既存の `docs/plan.md` / `docs/spec.md` に Phase 7 の追記
- [ ] PR 作成（`feat(graph): Microsoft Graph APIによるメール取得機能を追加`）

## 未着手（その他）

- [ ] リソース削除手順の検証（PoC完了後に実施）

## 完了

- [x] プロジェクトフォルダ作成・Git初期化
- [x] docs/ 配下のドキュメント整備
- [x] CLAUDE.md 作成
- [x] plan.md の確認（承認済み）
- [x] spec.md の確認（承認済み）
- [x] Phase 1: Azure環境構築（アカウント作成、Entra IDアプリ登録、シークレット取得、IDトークン有効化）
- [x] Phase 2: GCP基盤準備（API有効化、GCSバケット作成、SA作成・権限付与）
- [x] Phase 3: アプリケーション構築・デプロイ（Artifact Registry、バックエンド・フロントエンド Cloud Run デプロイ完了）
- [x] 3層構成への設計変更（LBパスルーティング廃止、Next.jsがバックエンドに中継する構成に変更）
- [x] Phase 4: HTTPS + ドメイン設定（証明書ACTIVE、LB構築完了、DNS設定完了）
- [x] Phase 5: 認証連携設定（Identity Platform、IAP、Entra IDリダイレクトURI設定完了）
- [x] Phase 6: E2E動作確認（認証→PDF画面表示→アップロード→GCS保存 すべて成功）
