# 認証PoC 構築計画

## 目的

企業向けWebアプリケーションにおける認証基盤のPoCを構築する。
Microsoft Entra ID（旧Azure AD）をIDプロバイダとして、Google CloudのIAPでアプリケーションレベルの認証を実現する。

アプリケーションコード側に認証ロジックを一切書かず、インフラレベルで認証を強制できることを検証する。

## アーキテクチャ方針

### 認証フロー

1. ユーザーが `https://poc.tetutetu214.com` にアクセス
2. Cloud Load Balancer が IAP を通じて認証状態をチェック
3. 未認証の場合、Identity Platform の認証ページにリダイレクト
4. Identity Platform が Entra ID（OIDC）にリダイレクト
5. ユーザーが Entra ID でログイン
6. 認証完了後、ブラウザにクッキーが保存され、アプリに到達

### パスルーティング

| パス | 転送先 | 説明 |
|---|---|---|
| `/*` | poc-frontend (Next.js) | フロントエンド |
| `/api/*` | poc-backend (FastAPI) | バックエンドAPI |

### サンプル機能

認証基盤の動作確認用として、PDFファイルアップロード機能を実装する。
フロントエンドでファイルを選択し、バックエンドAPI経由でGCSに保存する。

## 構築フェーズ

### Phase 1: Azure環境構築（手動・てつてつさん作業）
- Azure無料アカウント作成（Microsoftアカウントでサインイン、クレジットカード登録）
- Entra ID テナントの確認（無料アカウント作成時に自動でテナントが付与される）
- Entra ID アプリ登録（`poc-gcp-oidc`）
- クライアントID・テナントID・クライアントシークレットの取得
- IDトークン有効化

### Phase 2: GCP基盤準備
- API有効化
- GCSバケット作成
- サービスアカウント作成・権限付与

### Phase 3: アプリケーション構築・デプロイ
- バックエンド（FastAPI）のコード作成・Dockerize・Cloud Runデプロイ
- フロントエンド（Next.js）のコード作成・Dockerize・Cloud Runデプロイ

### Phase 4: HTTPS + ドメイン設定
- Googleマネージド証明書の発行（DNS認証）
- Cloudflare DNSレコード設定
- Cloud Load Balancing 構築（Serverless NEG → バックエンドサービス → URLマップ → HTTPSプロキシ）

### Phase 5: 認証連携設定
- GCP Identity Platform 有効化 + OIDCプロバイダ登録（Phase 1で取得したEntra IDの情報を使用）
- IAP 有効化・設定（GUIでの手動操作）
- Entra ID 側にリダイレクトURIを追加登録（Identity Platformのコールバック URL）

### Phase 6: 動作確認・ドキュメント整備
- E2E動作確認（未認証→認証→アップロード→GCS確認）
- リソース削除手順の検証

## 技術選定理由

| 選択 | 理由 |
|---|---|
| IAP（アプリコード外で認証） | アプリケーションに認証コードを入れると保守コストが上がる。IAPならLBレベルで強制でき、アプリは認証を意識しなくてよい |
| Identity Platform（Firebase Authの上位版） | 外部IDプロバイダ（Entra ID等）との連携が容易。IAPとネイティブ統合されている |
| Entra ID（OIDC） | 企業環境では Microsoft 365 / Azure AD が広く使われている。OIDCは標準プロトコルで連携が簡単 |
| Googleマネージド証明書 + DNS認証 | Let's Encryptと違い自動更新。DNS認証はLBのIPが変わっても再検証不要 |
| Cloudflareはプロキシ OFF（グレー雲） | Cloudflareプロキシが有効だとGoogleの証明書検証が失敗するため |
| Cloud Run（max-instances=3） | PoC用途なのでコスト抑制。Serverless NEGでLBと統合可能 |

## 前提・制約

- GCPプロジェクトは個人環境（VPC Service Controls なし）
- ドメイン `poc.tetutetu214.com` は Cloudflare Registrar で管理済み
- **Azure環境は未構築**（アカウント作成から必要）
- Azure無料アカウントにはクレジットカード登録が必要だが、Free枠内なら課金なし
- Entra ID（旧Azure AD）はAzure無料アカウントに含まれるため追加費用なし
- 一部のステップ（Azure操作、Cloudflare DNS設定、IAP GUIの設定）はてつてつさんの手動操作が必要
