# GCP認証PoC - プロジェクト設定

## 概要

Microsoft Entra ID + Google Identity Platform + IAP を使った認証基盤のPoC。
Cloud Run上のNext.js（フロントエンド）とFastAPI（バックエンド）に対して、
LBレベルでゼロトラスト認証を実現する。

## 技術スタック

| レイヤー | 技術 |
|---|---|
| クラウド | Google Cloud |
| リージョン | asia-northeast1 |
| フロントエンド | Next.js 14 (App Router) / Cloud Run |
| バックエンド | FastAPI + Python 3.12 / Cloud Run |
| ストレージ | Google Cloud Storage |
| 認証 | Microsoft Entra ID (OIDC) → Identity Platform → IAP |
| SSL | Google マネージド証明書（DNS認証） |
| LB | External Application Load Balancer |
| ドメイン | poc.tetutetu214.com（Cloudflare Registrar管理） |
| コンテナレジストリ | Artifact Registry (asia-northeast1) |

## インフラ構成

```
ユーザー → HTTPS(443) → Cloud LB + IAP → Identity Platform → Entra ID
                              ↓ パスルーティング
                        /* → Cloud Run: poc-frontend (Next.js)
                     /api/* → Cloud Run: poc-backend (FastAPI) → GCS
```

## 開発ルール

- バックエンド（Python）のコードは `/backend` に配置
- フロントエンド（Next.js）のコードは `/frontend` に配置
- インフラ構築は gcloud CLI で手動実行（Terraform等は使わない、PoC のため）
- Cloud Run の max-instances は 3（コスト抑制）
- Cloud Run の ingress は internal（バックエンド）/ internal-and-cloud-load-balancing（フロントエンド）
