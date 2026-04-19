# Microsoft Graph API メール取得機能 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 既存のgcp-auth-pocにMicrosoft Graph API経由でメール取得を検証する機能を追加する。「メール取得」ボタン押下→Entra IDの同意（初回のみ）→アクセストークンをFirestoreに保存→Graph APIで `/me/messages` を10件取得→GCSにJSON保存。

**Architecture:** Next.jsはUI＋プロキシに徹し、FastAPIが実処理（OAuthトークン交換・Firestore保存・Graph呼出・GCS書込）を担う。クライアントシークレットはSecret ManagerからCloud Runに注入、トークンはFirestoreに永続化。state パラメータとHttpOnly Cookie でCSRFを防ぐ。

**Tech Stack:** Python 3.12 + FastAPI / httpx / google-cloud-firestore / google-cloud-secret-manager / google-cloud-storage / Next.js 14 (App Router) / pytest + respx

**参照仕様書:** `docs/superpowers/specs/2026-04-19-graph-api-mail-design.md`

---

## ファイル構成

### 新規作成

**バックエンド**
- `backend/config.py` — 環境変数とSecret Manager由来シークレットの読み込み
- `backend/firestore_tokens.py` — Firestoreトークンリポジトリ（CRUD）
- `backend/oauth.py` — state生成、認可URL組立、トークン交換、リフレッシュ
- `backend/graph_client.py` — Microsoft Graph API `/me/messages` 呼出
- `backend/gcs_writer.py` — GCSへのメールJSON書込
- `backend/routes_graph.py` — `/api/graph/sync` と `/api/graph/callback` のFastAPIルーター
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` — 共通フィクスチャ
- `backend/tests/test_oauth.py`
- `backend/tests/test_firestore_tokens.py`
- `backend/tests/test_graph_client.py`
- `backend/tests/test_gcs_writer.py`
- `backend/tests/test_routes_graph.py`
- `backend/pytest.ini`

**フロントエンド**
- `frontend/app/api/graph/sync/route.ts` — FastAPIへのプロキシ（GET）
- `frontend/app/api/graph/callback/route.ts` — FastAPIへのプロキシ（GET、code+stateを転送）

### 修正

- `backend/main.py` — 新しいルーターを登録
- `backend/requirements.txt` — 依存追加
- `frontend/app/page.tsx` — 「メール取得」ボタンと結果表示を追加

---

## 前提条件（事前にてつてつさんが手動でやる作業）

実装タスクに入る前に、以下のインフラ側作業を `memo.md` Step 14〜16 に従って完了させてください。実装コードはこれらが揃っている前提で動きます。

- [ ] Step 14: Entra ID アプリに `Mail.Read` / `offline_access` 権限追加、リダイレクトURI `https://poc.tetutetu214.com/api/graph/callback` 追加
- [ ] Step 15: Secret Manager に `poc-entra-client-secret` 作成、`poc-backend-sa` に `roles/secretmanager.secretAccessor` 付与
- [ ] Step 16: Firestore Native mode データベース作成（`asia-northeast1`）、`poc-backend-sa` に `roles/datastore.user` 付与

完了後、実装タスクに進む。

---

## Task 1: ブランチ作成とテスト基盤整備

**Files:**
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: feature ブランチを切る**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git switch -c feature/graph-api-mail
```

- [ ] **Step 2: 依存パッケージを `backend/requirements.txt` に追加**

`backend/requirements.txt` の末尾に以下を追記：

```
google-cloud-firestore==2.18.0
google-cloud-secret-manager==2.20.0
httpx==0.27.0
pytest==8.3.3
pytest-asyncio==0.24.0
respx==0.21.1
```

- [ ] **Step 3: `backend/pytest.ini` を作成**

```ini
[pytest]
testpaths = tests
pythonpath = .
asyncio_mode = auto
```

- [ ] **Step 4: `backend/tests/__init__.py` を空ファイルで作成**

```python
```

- [ ] **Step 5: `backend/tests/conftest.py` を作成（共通フィクスチャ）**

```python
"""共通のテスト用フィクスチャ"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def fake_firestore_client() -> MagicMock:
    """Firestoreクライアントのモック"""
    return MagicMock()


@pytest.fixture
def dummy_config() -> dict[str, str]:
    """テスト用の設定値"""
    return {
        "tenant_id": "test-tenant-id",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "redirect_uri": "https://poc.tetutetu214.com/api/graph/callback",
        "bucket_name": "test-bucket",
    }
```

- [ ] **Step 6: 依存をインストールしてテストが走る土台を確認**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

Expected: `no tests ran` or 0 collected（テストがまだ無いのでOK）

- [ ] **Step 7: コミット＆プッシュ**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/requirements.txt backend/pytest.ini backend/tests/__init__.py backend/tests/conftest.py
git commit -m "chore(backend): pytestとGraph用依存を追加"
git push -u origin feature/graph-api-mail
```

---

## Task 2: 設定モジュール (config.py)

**Files:**
- Create: `backend/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_config.py`:

```python
"""config.pyのテスト"""
import os
import pytest

from config import load_config, ConfigError


def test_load_config_returns_all_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """必須環境変数がそろっていれば辞書で返す"""
    monkeypatch.setenv("ENTRA_TENANT_ID", "t1")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "c1")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "s1")
    monkeypatch.setenv("REDIRECT_URI", "https://example.com/cb")
    monkeypatch.setenv("BUCKET_NAME", "b1")

    cfg = load_config()

    assert cfg.tenant_id == "t1"
    assert cfg.client_id == "c1"
    assert cfg.client_secret == "s1"
    assert cfg.redirect_uri == "https://example.com/cb"
    assert cfg.bucket_name == "b1"


def test_load_config_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数が足りないとConfigErrorを投げる"""
    for key in ["ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET",
                "REDIRECT_URI", "BUCKET_NAME"]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError):
        load_config()
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: FAIL（`config`モジュールが存在しないため ImportError）

- [ ] **Step 3: `backend/config.py` を実装**

```python
"""環境変数からアプリ設定を読み込むモジュール"""
import os
from dataclasses import dataclass


class ConfigError(Exception):
    """設定値が不正な場合に投げる例外"""


@dataclass(frozen=True)
class AppConfig:
    """アプリ全体で共有する設定値"""
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    bucket_name: str


def load_config() -> AppConfig:
    """環境変数から設定を読み込む"""
    required = {
        "ENTRA_TENANT_ID": None,
        "ENTRA_CLIENT_ID": None,
        "ENTRA_CLIENT_SECRET": None,
        "REDIRECT_URI": None,
        "BUCKET_NAME": None,
    }
    missing: list[str] = []
    for key in required:
        value = os.environ.get(key)
        if not value:
            missing.append(key)
        else:
            required[key] = value
    if missing:
        raise ConfigError(f"環境変数が不足: {', '.join(missing)}")

    return AppConfig(
        tenant_id=required["ENTRA_TENANT_ID"],
        client_id=required["ENTRA_CLIENT_ID"],
        client_secret=required["ENTRA_CLIENT_SECRET"],
        redirect_uri=required["REDIRECT_URI"],
        bucket_name=required["BUCKET_NAME"],
    )
```

- [ ] **Step 4: テストが通ることを確認**

```bash
pytest tests/test_config.py -v
```

Expected: 2 passed

- [ ] **Step 5: コミット＆プッシュ**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/config.py backend/tests/test_config.py
git commit -m "feat(backend): 環境変数から設定を読み込むconfigモジュールを追加"
git push
```

---

## Task 3: Firestore トークンリポジトリ (firestore_tokens.py)

**Files:**
- Create: `backend/firestore_tokens.py`
- Create: `backend/tests/test_firestore_tokens.py`

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_firestore_tokens.py`:

```python
"""firestore_tokens.pyのテスト"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from firestore_tokens import (
    TokenRecord,
    save_token,
    load_token,
    delete_token,
)


def _make_fake_client(exists: bool, data: dict | None = None) -> MagicMock:
    """Firestoreクライアントのモックを組み立てる"""
    client = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = exists
    snapshot.to_dict.return_value = data or {}
    doc_ref = MagicMock()
    doc_ref.get.return_value = snapshot
    client.collection.return_value.document.return_value = doc_ref
    return client


def test_save_token_writes_to_collection() -> None:
    """save_tokenがgraph_tokensコレクションにsetを呼ぶ"""
    client = _make_fake_client(exists=False)
    at_value = "at"
    rt_value = "rt"
    record = TokenRecord(
        access_token=at_value,
        refresh_token=rt_value,
        expires_at=datetime(2026, 4, 19, 10, 0, 0, tzinfo=timezone.utc),
        scope="Mail.Read",
    )

    save_token(client, "user@example.com", record)

    client.collection.assert_called_once_with("graph_tokens")
    client.collection.return_value.document.assert_called_once_with("user@example.com")
    doc_ref = client.collection.return_value.document.return_value
    doc_ref.set.assert_called_once()
    saved = doc_ref.set.call_args[0][0]
    assert saved["access_token"] == "at"
    assert saved["refresh_token"] == "rt"
    assert saved["scope"] == "Mail.Read"


def test_load_token_returns_none_if_missing() -> None:
    """ドキュメントが無ければNoneを返す"""
    client = _make_fake_client(exists=False)
    assert load_token(client, "no@example.com") is None


def test_load_token_returns_record_if_present() -> None:
    """ドキュメントがあればTokenRecordで返す"""
    expires = datetime(2026, 4, 19, 10, 0, 0, tzinfo=timezone.utc)
    client = _make_fake_client(
        exists=True,
        data={
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": expires,
            "scope": "Mail.Read",
        },
    )

    record = load_token(client, "user@example.com")

    assert record is not None
    assert record.access_token == "at"
    assert record.refresh_token == "rt"
    assert record.expires_at == expires
    assert record.scope == "Mail.Read"


def test_is_expired_true_when_past() -> None:
    """expires_atが過去ならis_expiredがTrue"""
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    record = TokenRecord("at", "rt", past, "Mail.Read")
    assert record.is_expired() is True


def test_is_expired_false_when_future() -> None:
    """expires_atが1分以上先ならis_expiredがFalse"""
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    record = TokenRecord("at", "rt", future, "Mail.Read")
    assert record.is_expired() is False


def test_delete_token_calls_delete() -> None:
    """delete_tokenがdocument.deleteを呼ぶ"""
    client = _make_fake_client(exists=True)
    delete_token(client, "user@example.com")
    doc_ref = client.collection.return_value.document.return_value
    doc_ref.delete.assert_called_once()
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_firestore_tokens.py -v
```

Expected: FAIL（モジュール未実装）

- [ ] **Step 3: `backend/firestore_tokens.py` を実装**

```python
"""Firestore graph_tokensコレクションのリポジトリ"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any


COLLECTION = "graph_tokens"
EXPIRY_SAFETY_SECONDS = 60  # 余裕を持たせて失効扱いにする秒数


@dataclass
class TokenRecord:
    """ユーザー1人分のトークンレコード"""
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str

    def is_expired(self) -> bool:
        """アクセストークンが失効間近か"""
        now = datetime.now(timezone.utc)
        return self.expires_at <= now + timedelta(seconds=EXPIRY_SAFETY_SECONDS)


def save_token(client: Any, user_email: str, record: TokenRecord) -> None:
    """ユーザーのトークンを上書き保存する"""
    doc_ref = client.collection(COLLECTION).document(user_email)
    doc_ref.set(
        {
            "access_token": record.access_token,
            "refresh_token": record.refresh_token,
            "expires_at": record.expires_at,
            "scope": record.scope,
            "updated_at": datetime.now(timezone.utc),
        }
    )


def load_token(client: Any, user_email: str) -> TokenRecord | None:
    """ユーザーのトークンを読み出す。無ければNone"""
    doc_ref = client.collection(COLLECTION).document(user_email)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    return TokenRecord(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=data["expires_at"],
        scope=data["scope"],
    )


def delete_token(client: Any, user_email: str) -> None:
    """ユーザーのトークンを削除する"""
    client.collection(COLLECTION).document(user_email).delete()
```

- [ ] **Step 4: テストが通ることを確認**

```bash
pytest tests/test_firestore_tokens.py -v
```

Expected: 6 passed

- [ ] **Step 5: コミット＆プッシュ**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/firestore_tokens.py backend/tests/test_firestore_tokens.py
git commit -m "feat(backend): Firestoreトークンリポジトリを追加"
git push
```

---

## Task 4: OAuth モジュール — state生成・認可URL

**Files:**
- Create: `backend/oauth.py`
- Create: `backend/tests/test_oauth.py`

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_oauth.py`:

```python
"""oauth.pyのテスト（state生成・認可URL）"""
from urllib.parse import urlparse, parse_qs

from oauth import generate_state, build_authorize_url


def test_generate_state_returns_long_random_string() -> None:
    """stateは少なくとも32文字で、毎回値が違う"""
    s1 = generate_state()
    s2 = generate_state()
    assert len(s1) >= 32
    assert s1 != s2


def test_build_authorize_url_contains_required_params() -> None:
    """認可URLに必要なクエリパラメータがすべて含まれる"""
    url = build_authorize_url(
        tenant_id="tid",
        client_id="cid",
        redirect_uri="https://example.com/cb",
        state="STATE123",
    )

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/tid/oauth2/v2.0/authorize"

    params = parse_qs(parsed.query)
    assert params["client_id"] == ["cid"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == ["https://example.com/cb"]
    assert params["response_mode"] == ["query"]
    assert params["state"] == ["STATE123"]
    # スコープ
    scope = params["scope"][0]
    assert "openid" in scope
    assert "profile" in scope
    assert "email" in scope
    assert "offline_access" in scope
    assert "Mail.Read" in scope
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_oauth.py -v
```

Expected: FAIL（モジュール未実装）

- [ ] **Step 3: `backend/oauth.py` を実装（最初の部分）**

```python
"""OAuth 2.0 Authorization Code Flow 用のユーティリティ"""
import secrets
from urllib.parse import urlencode

AUTHORIZE_ENDPOINT = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "Mail.Read",
]


def generate_state() -> str:
    """CSRF対策用のランダムstate文字列（32バイト相当）を生成"""
    return secrets.token_urlsafe(32)


def build_authorize_url(
    tenant_id: str,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Entra IDの認可エンドポイントURLを組み立てる"""
    base = AUTHORIZE_ENDPOINT.format(tenant_id=tenant_id)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return f"{base}?{urlencode(params)}"
```

- [ ] **Step 4: テストが通ることを確認**

```bash
pytest tests/test_oauth.py -v
```

Expected: 2 passed

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/oauth.py backend/tests/test_oauth.py
git commit -m "feat(backend): OAuth state生成と認可URLビルダーを追加"
git push
```

---

## Task 5: OAuth モジュール — トークン交換とリフレッシュ

**Files:**
- Modify: `backend/oauth.py`
- Modify: `backend/tests/test_oauth.py`

- [ ] **Step 1: 失敗するテストを追記**

`backend/tests/test_oauth.py` の末尾に追記：

```python
import pytest
import respx
import httpx
from datetime import datetime, timezone

from oauth import exchange_code_for_token, refresh_access_token


@pytest.mark.asyncio
async def test_exchange_code_for_token_sends_correct_request() -> None:
    """認可コード交換が正しいパラメータでPOSTされる"""
    async with respx.mock(base_url="https://login.microsoftonline.com") as mock:
        route = mock.post("/tid/oauth2/v2.0/token").respond(
            json={
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3600,
                "scope": "openid Mail.Read",
                "token_type": "Bearer",
            }
        )

        record = await exchange_code_for_token(
            tenant_id="tid",
            client_id="cid",
            client_secret="sec",
            code="CODE",
            redirect_uri="https://example.com/cb",
        )

        assert record.access_token == "AT"
        assert record.refresh_token == "RT"
        assert record.scope == "openid Mail.Read"
        assert record.expires_at > datetime.now(timezone.utc)

        # 送信内容の検証
        request = route.calls.last.request
        body = request.content.decode()
        assert "grant_type=authorization_code" in body
        assert "code=CODE" in body
        assert "client_id=cid" in body
        assert "client_secret=sec" in body


@pytest.mark.asyncio
async def test_refresh_access_token_sends_correct_request() -> None:
    """リフレッシュトークンを使った再発行が正しくPOSTされる"""
    async with respx.mock(base_url="https://login.microsoftonline.com") as mock:
        route = mock.post("/tid/oauth2/v2.0/token").respond(
            json={
                "access_token": "NEW_AT",
                "refresh_token": "NEW_RT",
                "expires_in": 3600,
                "scope": "openid Mail.Read",
                "token_type": "Bearer",
            }
        )

        old_rt_value = "OLD_RT"
        record = await refresh_access_token(
            tenant_id="tid",
            client_id="cid",
            client_secret="sec",
            refresh_token=old_rt_value,
        )

        assert record.access_token == "NEW_AT"
        assert record.refresh_token == "NEW_RT"

        request = route.calls.last.request
        body = request.content.decode()
        assert "grant_type=refresh_token" in body
        assert "refresh_token=OLD_RT" in body


@pytest.mark.asyncio
async def test_exchange_code_raises_on_http_error() -> None:
    """Entra IDが4xxを返したら例外"""
    async with respx.mock(base_url="https://login.microsoftonline.com") as mock:
        mock.post("/tid/oauth2/v2.0/token").respond(
            status_code=400,
            json={"error": "invalid_grant"},
        )

        with pytest.raises(httpx.HTTPStatusError):
            await exchange_code_for_token(
                tenant_id="tid",
                client_id="cid",
                client_secret="sec",
                code="BAD",
                redirect_uri="https://example.com/cb",
            )
```

- [ ] **Step 2: テスト実行して失敗確認**

```bash
pytest tests/test_oauth.py -v
```

Expected: FAIL（`exchange_code_for_token` と `refresh_access_token` が未実装）

- [ ] **Step 3: `backend/oauth.py` に関数を追記**

`backend/oauth.py` の末尾に以下を追加：

```python
from datetime import datetime, timezone, timedelta
import httpx

from firestore_tokens import TokenRecord


async def _post_token(
    tenant_id: str,
    data: dict[str, str],
) -> TokenRecord:
    """Entra IDのtokenエンドポイントにPOSTしてTokenRecordにする共通処理"""
    url = TOKEN_ENDPOINT.format(tenant_id=tenant_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        body = response.json()

    expires_in = int(body.get("expires_in", 3600))
    return TokenRecord(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", ""),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scope=body.get("scope", ""),
    )


async def exchange_code_for_token(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> TokenRecord:
    """認可コードをアクセストークン＋リフレッシュトークンに交換"""
    return await _post_token(
        tenant_id=tenant_id,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )


async def refresh_access_token(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> TokenRecord:
    """リフレッシュトークンで新しいアクセストークンを取得"""
    return await _post_token(
        tenant_id=tenant_id,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
    )
```

- [ ] **Step 4: テストが通ることを確認**

```bash
pytest tests/test_oauth.py -v
```

Expected: 5 passed（既存2 + 新規3）

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/oauth.py backend/tests/test_oauth.py
git commit -m "feat(backend): OAuthトークン交換とリフレッシュ処理を追加"
git push
```

---

## Task 6: Microsoft Graph API クライアント (graph_client.py)

**Files:**
- Create: `backend/graph_client.py`
- Create: `backend/tests/test_graph_client.py`

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_graph_client.py`:

```python
"""graph_client.pyのテスト"""
import pytest
import respx
import httpx

from graph_client import list_messages


@pytest.mark.asyncio
async def test_list_messages_calls_correct_endpoint() -> None:
    """Graph APIの /me/messages を正しいヘッダで叩く"""
    async with respx.mock(base_url="https://graph.microsoft.com") as mock:
        route = mock.get("/v1.0/me/messages").respond(
            json={
                "value": [
                    {
                        "subject": "件名1",
                        "from": {"emailAddress": {"address": "a@x.com"}},
                        "receivedDateTime": "2026-04-19T00:00:00Z",
                        "bodyPreview": "プレビュー1",
                    },
                ]
            }
        )

        at_value = "AT"
        messages = await list_messages(access_token=at_value, top=10)

        assert len(messages) == 1
        assert messages[0]["subject"] == "件名1"

        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer AT"
        assert "$top=10" in str(request.url)
        assert "$select=" in str(request.url)


@pytest.mark.asyncio
async def test_list_messages_raises_on_401() -> None:
    """401が返ったら例外（呼び元でリフレッシュ判定させる）"""
    async with respx.mock(base_url="https://graph.microsoft.com") as mock:
        mock.get("/v1.0/me/messages").respond(status_code=401)

        with pytest.raises(httpx.HTTPStatusError):
            bad_value = "BAD"
            await list_messages(access_token=bad_value, top=10)
```

- [ ] **Step 2: テスト実行して失敗確認**

```bash
pytest tests/test_graph_client.py -v
```

Expected: FAIL

- [ ] **Step 3: `backend/graph_client.py` を実装**

```python
"""Microsoft Graph API クライアント（/me/messages用）"""
import httpx

MESSAGES_ENDPOINT = "https://graph.microsoft.com/v1.0/me/messages"

SELECT_FIELDS = "subject,from,receivedDateTime,bodyPreview"


async def list_messages(
    access_token: str,
    top: int = 10,
) -> list[dict]:
    """直近のメール一覧を取得する（件名・送信元・受信日時・プレビューのみ）"""
    params = {
        "$top": str(top),
        "$select": SELECT_FIELDS,
        "$orderby": "receivedDateTime desc",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            MESSAGES_ENDPOINT,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
    messages: list[dict] = body.get("value", [])
    return messages
```

- [ ] **Step 4: テスト成功を確認**

```bash
pytest tests/test_graph_client.py -v
```

Expected: 2 passed

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/graph_client.py backend/tests/test_graph_client.py
git commit -m "feat(backend): Microsoft Graph API /me/messages クライアントを追加"
git push
```

---

## Task 7: GCS 書き込みヘルパー (gcs_writer.py)

**Files:**
- Create: `backend/gcs_writer.py`
- Create: `backend/tests/test_gcs_writer.py`

- [ ] **Step 1: 失敗するテストを書く**

`backend/tests/test_gcs_writer.py`:

```python
"""gcs_writer.pyのテスト"""
import json
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gcs_writer import save_mails_to_gcs


def test_save_mails_to_gcs_writes_json() -> None:
    """メール配列をJSONとしてバケットにアップロードする"""
    storage_client = MagicMock()
    bucket = MagicMock()
    blob = MagicMock()
    storage_client.bucket.return_value = bucket
    bucket.blob.return_value = blob

    messages = [
        {"subject": "件名", "bodyPreview": "プレビュー"},
    ]
    fixed_now = datetime(2026, 4, 19, 9, 30, 45, tzinfo=timezone.utc)

    path = save_mails_to_gcs(
        storage_client=storage_client,
        bucket_name="my-bucket",
        user_email="user@example.com",
        messages=messages,
        now=fixed_now,
    )

    storage_client.bucket.assert_called_once_with("my-bucket")
    # パスの期待: mails/user@example.com/20260419-093045.json
    bucket.blob.assert_called_once()
    blob_name = bucket.blob.call_args[0][0]
    assert blob_name == "mails/user@example.com/20260419-093045.json"

    # upload_from_string に渡されたJSONの中身を確認
    upload_args = blob.upload_from_string.call_args
    payload = upload_args[0][0]
    assert json.loads(payload) == messages
    assert upload_args[1]["content_type"] == "application/json"

    assert path == f"gs://my-bucket/{blob_name}"
```

- [ ] **Step 2: テスト実行して失敗確認**

```bash
pytest tests/test_gcs_writer.py -v
```

Expected: FAIL

- [ ] **Step 3: `backend/gcs_writer.py` を実装**

```python
"""取得したメールをGCSに保存するヘルパー"""
import json
from datetime import datetime
from typing import Any


def save_mails_to_gcs(
    storage_client: Any,
    bucket_name: str,
    user_email: str,
    messages: list[dict],
    now: datetime,
) -> str:
    """メール配列をJSONファイルとしてGCSにアップロードし、gs://パスを返す"""
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    blob_name = f"mails/{user_email}/{timestamp}.json"
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    payload = json.dumps(messages, ensure_ascii=False, indent=2)
    blob.upload_from_string(payload, content_type="application/json")
    return f"gs://{bucket_name}/{blob_name}"
```

- [ ] **Step 4: テスト成功を確認**

```bash
pytest tests/test_gcs_writer.py -v
```

Expected: 1 passed

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/gcs_writer.py backend/tests/test_gcs_writer.py
git commit -m "feat(backend): GCSへのメールJSON書き込みヘルパーを追加"
git push
```

---

## Task 8: `/api/graph/sync` ルート（トークン有無で分岐）

**Files:**
- Create: `backend/routes_graph.py`
- Create: `backend/tests/test_routes_graph.py`

- [ ] **Step 1: 失敗するテスト（sync: 未認可分岐）を書く**

`backend/tests/test_routes_graph.py`:

```python
"""routes_graph.pyのテスト"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes_graph import build_router, GraphDeps
from config import AppConfig
from firestore_tokens import TokenRecord


def _make_app(deps: GraphDeps) -> FastAPI:
    app = FastAPI()
    app.include_router(build_router(deps))
    return app


def _base_config() -> AppConfig:
    return AppConfig(
        tenant_id="tid",
        client_id="cid",
        client_secret="sec",
        redirect_uri="https://poc.tetutetu214.com/api/graph/callback",
        bucket_name="test-bucket",
    )


def test_sync_returns_auth_required_when_no_token() -> None:
    """トークン未保存なら status=auth_required で認可URLを返し、state Cookieを立てる"""
    firestore = MagicMock()
    firestore.collection.return_value.document.return_value.get.return_value.exists = False
    storage = MagicMock()
    deps = GraphDeps(
        config=_base_config(),
        firestore_client=firestore,
        storage_client=storage,
    )

    client = TestClient(_make_app(deps))
    # IAPが注入するヘッダを模擬
    headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:user@example.com"}
    response = client.get("/api/graph/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "auth_required"
    assert "login.microsoftonline.com" in body["authorize_url"]
    # state Cookieが立っている
    assert "graph_oauth_state" in response.cookies
```

- [ ] **Step 2: テスト実行して失敗確認**

```bash
pytest tests/test_routes_graph.py -v
```

Expected: FAIL（routes_graph未実装）

- [ ] **Step 3: `backend/routes_graph.py` を実装（sync の未認可分岐だけ）**

```python
"""/api/graph/* のFastAPIルーター"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from config import AppConfig
from firestore_tokens import (
    TokenRecord,
    load_token,
    save_token,
    delete_token,
)
from oauth import (
    generate_state,
    build_authorize_url,
    exchange_code_for_token,
    refresh_access_token,
)
from graph_client import list_messages
from gcs_writer import save_mails_to_gcs


STATE_COOKIE_NAME = "graph_oauth_state"
STATE_COOKIE_MAX_AGE = 600  # 10分


@dataclass
class GraphDeps:
    """ルーターが必要とする外部依存"""
    config: AppConfig
    firestore_client: Any
    storage_client: Any


def _extract_user_email(raw: str | None) -> str:
    """IAPヘッダ `X-Goog-Authenticated-User-Email` からメール部分のみ取り出す

    例: 'accounts.google.com:user@example.com' -> 'user@example.com'
    """
    if not raw:
        return ""
    if ":" in raw:
        return raw.split(":", 1)[1]
    return raw


def build_router(deps: GraphDeps) -> APIRouter:
    """GraphDepsを束縛したAPIRouterを返す"""
    router = APIRouter()

    @router.get("/api/graph/sync")
    async def sync(
        x_goog_authenticated_user_email: str | None = Header(default=None),
    ) -> Response:
        user_email = _extract_user_email(x_goog_authenticated_user_email)
        record = load_token(deps.firestore_client, user_email) if user_email else None

        if record is None:
            # 未認可：認可URLをJSONで返し、stateをCookieに保存
            state = generate_state()
            authorize_url = build_authorize_url(
                tenant_id=deps.config.tenant_id,
                client_id=deps.config.client_id,
                redirect_uri=deps.config.redirect_uri,
                state=state,
            )
            response = JSONResponse(
                {"status": "auth_required", "authorize_url": authorize_url}
            )
            response.set_cookie(
                key=STATE_COOKIE_NAME,
                value=state,
                max_age=STATE_COOKIE_MAX_AGE,
                httponly=True,
                secure=True,
                samesite="lax",
            )
            return response

        # トークンあり：ここから先は Task 9 で実装
        return JSONResponse({"status": "ok", "count": 0, "gcs_path": ""})

    return router
```

- [ ] **Step 4: テスト成功を確認**

```bash
pytest tests/test_routes_graph.py::test_sync_returns_auth_required_when_no_token -v
```

Expected: 1 passed

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/routes_graph.py backend/tests/test_routes_graph.py
git commit -m "feat(backend): /api/graph/sync の未認可分岐を実装"
git push
```

---

## Task 9: `/api/graph/sync` ルート（メール取得完遂）

**Files:**
- Modify: `backend/routes_graph.py`
- Modify: `backend/tests/test_routes_graph.py`

- [ ] **Step 1: 失敗するテストを追記（sync: トークンありでメール取得成功）**

`backend/tests/test_routes_graph.py` の末尾に追記：

```python
def test_sync_fetches_mails_when_token_valid() -> None:
    """有効トークンがある場合、Graph APIから取得してGCSに保存する"""
    # Firestoreモック：有効トークンが返る
    firestore = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = True
    future = datetime.now(timezone.utc) + timedelta(minutes=30)
    snapshot.to_dict.return_value = {
        "access_token": "AT",
        "refresh_token": "RT",
        "expires_at": future,
        "scope": "Mail.Read",
    }
    firestore.collection.return_value.document.return_value.get.return_value = snapshot

    # Storageモック
    storage = MagicMock()
    bucket = MagicMock()
    blob = MagicMock()
    storage.bucket.return_value = bucket
    bucket.blob.return_value = blob

    deps = GraphDeps(
        config=_base_config(),
        firestore_client=firestore,
        storage_client=storage,
    )

    with respx.mock(base_url="https://graph.microsoft.com", assert_all_mocked=False, assert_all_called=False) as graph_mock:
        graph_mock.get("/v1.0/me/messages").respond(
            json={
                "value": [
                    {"subject": "件名1", "bodyPreview": "p1"},
                    {"subject": "件名2", "bodyPreview": "p2"},
                ]
            }
        )

        client = TestClient(_make_app(deps))
        headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:user@example.com"}
        response = client.get("/api/graph/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 2
    assert body["gcs_path"].startswith("gs://test-bucket/mails/user@example.com/")
    blob.upload_from_string.assert_called_once()


def test_sync_refreshes_expired_token() -> None:
    """アクセストークン失効時はrefresh_tokenで自動更新して続行する"""
    firestore = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = True
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    snapshot.to_dict.return_value = {
        "access_token": "OLD_AT",
        "refresh_token": "RT",
        "expires_at": past,
        "scope": "Mail.Read",
    }
    firestore.collection.return_value.document.return_value.get.return_value = snapshot

    storage = MagicMock()
    storage.bucket.return_value.blob.return_value = MagicMock()

    deps = GraphDeps(
        config=_base_config(),
        firestore_client=firestore,
        storage_client=storage,
    )

    with respx.mock(assert_all_mocked=False, assert_all_called=False) as mocker:
        mocker.post(
            "https://login.microsoftonline.com/tid/oauth2/v2.0/token"
        ).respond(
            json={
                "access_token": "NEW_AT",
                "refresh_token": "NEW_RT",
                "expires_in": 3600,
                "scope": "Mail.Read",
            }
        )
        mocker.get("https://graph.microsoft.com/v1.0/me/messages").respond(
            json={"value": [{"subject": "件名"}]}
        )

        client = TestClient(_make_app(deps))
        headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:user@example.com"}
        response = client.get("/api/graph/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
```

- [ ] **Step 2: テスト実行して失敗確認**

```bash
pytest tests/test_routes_graph.py -v
```

Expected: 新規2テストが FAIL（トークン有ブランチ未実装）

- [ ] **Step 3: `backend/routes_graph.py` の sync の「トークンあり」分岐を実装**

`backend/routes_graph.py` の `sync` 関数内、`# トークンあり：ここから先は Task 9 で実装` 以降を以下に置き換え：

```python
        # アクセストークンが失効間近ならリフレッシュ
        if record.is_expired():
            refreshed = await refresh_access_token(
                tenant_id=deps.config.tenant_id,
                client_id=deps.config.client_id,
                client_secret=deps.config.client_secret,
                refresh_token=record.refresh_token,
            )
            # Entra IDはrefresh_tokenを再発行する場合もしない場合もある
            if not refreshed.refresh_token:
                refreshed.refresh_token = record.refresh_token
            save_token(deps.firestore_client, user_email, refreshed)
            record = refreshed

        # Graph APIから最新メールを10件取得
        messages = await list_messages(access_token=record.access_token, top=10)

        # GCSに保存
        gcs_path = save_mails_to_gcs(
            storage_client=deps.storage_client,
            bucket_name=deps.config.bucket_name,
            user_email=user_email,
            messages=messages,
            now=datetime.now(timezone.utc),
        )

        return JSONResponse(
            {"status": "ok", "count": len(messages), "gcs_path": gcs_path}
        )
```

- [ ] **Step 4: テスト成功を確認**

```bash
pytest tests/test_routes_graph.py -v
```

Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/routes_graph.py backend/tests/test_routes_graph.py
git commit -m "feat(backend): /api/graph/sync でGraph取得とGCS保存を実装"
git push
```

---

## Task 10: `/api/graph/callback` ルート（state検証＋トークン交換）

**Files:**
- Modify: `backend/routes_graph.py`
- Modify: `backend/tests/test_routes_graph.py`

- [ ] **Step 1: 失敗するテストを追記**

`backend/tests/test_routes_graph.py` の末尾に追記：

```python
def test_callback_exchanges_code_and_saves_token() -> None:
    """stateが一致した場合、codeをトークンに交換してFirestoreに保存する"""
    firestore = MagicMock()
    storage = MagicMock()
    deps = GraphDeps(
        config=_base_config(),
        firestore_client=firestore,
        storage_client=storage,
    )

    with respx.mock(assert_all_mocked=False, assert_all_called=False) as mocker:
        mocker.post(
            "https://login.microsoftonline.com/tid/oauth2/v2.0/token"
        ).respond(
            json={
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3600,
                "scope": "openid Mail.Read",
            }
        )

        client = TestClient(_make_app(deps))
        headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:user@example.com"}
        client.cookies.set("graph_oauth_state", "ABC")

        response = client.get(
            "/api/graph/callback?code=CODE&state=ABC",
            headers=headers,
            follow_redirects=False,
        )

    # 成功時は / にリダイレクトさせる
    assert response.status_code == 302
    assert response.headers["location"] == "/"

    # Firestoreにsetが呼ばれた
    doc_ref = firestore.collection.return_value.document.return_value
    doc_ref.set.assert_called_once()
    saved = doc_ref.set.call_args[0][0]
    assert saved["access_token"] == "AT"


def test_callback_rejects_mismatched_state() -> None:
    """state不一致なら400"""
    firestore = MagicMock()
    storage = MagicMock()
    deps = GraphDeps(
        config=_base_config(),
        firestore_client=firestore,
        storage_client=storage,
    )

    client = TestClient(_make_app(deps))
    client.cookies.set("graph_oauth_state", "COOKIE_STATE")
    headers = {"X-Goog-Authenticated-User-Email": "accounts.google.com:user@example.com"}

    response = client.get(
        "/api/graph/callback?code=CODE&state=DIFFERENT",
        headers=headers,
    )

    assert response.status_code == 400
```

- [ ] **Step 2: テスト実行して失敗確認**

```bash
pytest tests/test_routes_graph.py -v
```

Expected: 新規2テストが FAIL

- [ ] **Step 3: `backend/routes_graph.py` に callback ハンドラを追加**

`build_router` 関数内の `return router` 直前に、以下を追加：

```python
    @router.get("/api/graph/callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        x_goog_authenticated_user_email: str | None = Header(default=None),
    ) -> Response:
        user_email = _extract_user_email(x_goog_authenticated_user_email)
        cookie_state = request.cookies.get(STATE_COOKIE_NAME)

        if not code or not state or not cookie_state or state != cookie_state:
            return JSONResponse(
                {"detail": "state検証に失敗しました"},
                status_code=400,
            )

        record = await exchange_code_for_token(
            tenant_id=deps.config.tenant_id,
            client_id=deps.config.client_id,
            client_secret=deps.config.client_secret,
            code=code,
            redirect_uri=deps.config.redirect_uri,
        )
        save_token(deps.firestore_client, user_email, record)

        response = RedirectResponse(url="/", status_code=302)
        response.delete_cookie(STATE_COOKIE_NAME)
        return response
```

- [ ] **Step 4: テスト成功を確認**

```bash
pytest tests/test_routes_graph.py -v
```

Expected: 5 passed

- [ ] **Step 5: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/routes_graph.py backend/tests/test_routes_graph.py
git commit -m "feat(backend): /api/graph/callback でstate検証とトークン交換を実装"
git push
```

---

## Task 11: main.py にルーターを登録

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: `backend/main.py` を修正してルーターを組み込む**

既存の `backend/main.py` を以下に置き換え：

```python
"""FastAPIアプリケーションエントリポイント"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from google.cloud import storage, firestore

from config import load_config
from routes_graph import build_router, GraphDeps


app = FastAPI()
config = load_config()

# Graph API 用ルーターを登録（Firestore / GCS クライアントを1度だけ作る）
_firestore_client = firestore.Client()
_storage_client = storage.Client()
app.include_router(
    build_router(
        GraphDeps(
            config=config,
            firestore_client=_firestore_client,
            storage_client=_storage_client,
        )
    )
)


@app.get("/health")
def health() -> dict[str, str]:
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """PDFファイルをGCSにアップロードする（既存機能）"""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="PDFファイルのみ受け付けます",
        )

    bucket = _storage_client.bucket(config.bucket_name)
    blob = bucket.blob(f"uploads/{file.filename}")

    contents = await file.read()
    blob.upload_from_string(
        contents, content_type="application/pdf"
    )

    return {
        "message": "アップロード成功",
        "filename": file.filename or "",
    }
```

- [ ] **Step 2: ローカルでの構文チェック（Pythonモジュールとしてimportできるか）**

```bash
cd backend
source .venv/bin/activate
# 必須環境変数をダミーでセットして import 成功するか確認
ENTRA_TENANT_ID=x ENTRA_CLIENT_ID=x ENTRA_CLIENT_SECRET=x \
  REDIRECT_URI=https://x BUCKET_NAME=x \
  python -c "import main; print('OK')"
```

Expected: `OK` が表示される（Firestore/Storageクライアント初期化が実認証を使おうとして失敗する場合は ADC 未設定が原因。`gcloud auth application-default login` 済みかどうかで変わる。**CIやローカルでimportできなくてもこのタスクは通過**：次のTask 12で全体テストを回す）

- [ ] **Step 3: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add backend/main.py
git commit -m "feat(backend): main.pyにGraphルーターを組み込む"
git push
```

---

## Task 12: バックエンド全テストの通し実行

**Files:**
- （テスト実行のみ、ファイル変更なし）

- [ ] **Step 1: 全テストを一括で実行**

```bash
cd backend
source .venv/bin/activate
pytest -v
```

Expected: 全テストが PASSED（config: 2, firestore_tokens: 6, oauth: 5, graph_client: 2, gcs_writer: 1, routes_graph: 5 ＝ 合計 21 passed）

- [ ] **Step 2: テスト失敗があれば該当ファイルを修正**

失敗箇所のメッセージに従って該当 Task に戻り修正する。

- [ ] **Step 3: 問題なければ次タスクへ（コミット不要）**

---

## Task 13: Next.js プロキシ Route を2本追加

**Files:**
- Create: `frontend/app/api/graph/sync/route.ts`
- Create: `frontend/app/api/graph/callback/route.ts`

- [ ] **Step 1: `frontend/app/api/graph/sync/route.ts` を作成**

```typescript
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL;

export async function GET(req: NextRequest) {
  // IAPが注入するユーザー識別ヘッダをバックエンドに中継する
  const forwardHeaders: Record<string, string> = {};
  const email = req.headers.get("x-goog-authenticated-user-email");
  if (email) forwardHeaders["x-goog-authenticated-user-email"] = email;
  const cookie = req.headers.get("cookie");
  if (cookie) forwardHeaders["cookie"] = cookie;

  const res = await fetch(`${BACKEND_URL}/api/graph/sync`, {
    method: "GET",
    headers: forwardHeaders,
    redirect: "manual",
  });

  const body = await res.text();
  const response = new NextResponse(body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/json",
    },
  });
  // バックエンドが立てたSet-Cookieをブラウザに透過
  const setCookie = res.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
```

- [ ] **Step 2: `frontend/app/api/graph/callback/route.ts` を作成**

```typescript
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL;

export async function GET(req: NextRequest) {
  const { search } = new URL(req.url);

  const forwardHeaders: Record<string, string> = {};
  const email = req.headers.get("x-goog-authenticated-user-email");
  if (email) forwardHeaders["x-goog-authenticated-user-email"] = email;
  const cookie = req.headers.get("cookie");
  if (cookie) forwardHeaders["cookie"] = cookie;

  const res = await fetch(`${BACKEND_URL}/api/graph/callback${search}`, {
    method: "GET",
    headers: forwardHeaders,
    redirect: "manual",
  });

  // FastAPIからのレスポンス（リダイレクトかJSON）をそのまま返す
  const body = await res.text();
  const response = new NextResponse(body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/json",
    },
  });
  const location = res.headers.get("location");
  if (location) response.headers.set("location", location);
  const setCookie = res.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
```

- [ ] **Step 3: TypeScriptの型チェック**

```bash
cd frontend
npx tsc --noEmit
```

Expected: エラーなし

- [ ] **Step 4: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add frontend/app/api/graph/sync/route.ts frontend/app/api/graph/callback/route.ts
git commit -m "feat(frontend): Graph API用プロキシRouteを2本追加"
git push
```

---

## Task 14: トップページに「メール取得」ボタンを追加

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: `frontend/app/page.tsx` を以下に置き換える**

```tsx
"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string>("");
  const [uploadLoading, setUploadLoading] = useState<boolean>(false);

  const [mailMessage, setMailMessage] = useState<string>("");
  const [mailLoading, setMailLoading] = useState<boolean>(false);

  const handleUpload = async () => {
    if (!file) {
      setUploadMessage("ファイルを選択してください");
      return;
    }
    setUploadLoading(true);
    setUploadMessage("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setUploadMessage(data.message ?? JSON.stringify(data));
    } catch {
      setUploadMessage("エラーが発生しました");
    } finally {
      setUploadLoading(false);
    }
  };

  const handleFetchMail = async () => {
    setMailLoading(true);
    setMailMessage("");
    try {
      const res = await fetch("/api/graph/sync");
      const data = await res.json();
      if (data.status === "auth_required") {
        // Entra ID の同意画面へ遷移
        window.location.href = data.authorize_url;
        return;
      }
      if (data.status === "ok") {
        setMailMessage(`取得成功：${data.count}件 / ${data.gcs_path}`);
      } else {
        setMailMessage(`エラー：${JSON.stringify(data)}`);
      }
    } catch {
      setMailMessage("通信エラーが発生しました");
    } finally {
      setMailLoading(false);
    }
  };

  return (
    <main style={{ padding: "2rem" }}>
      <h1>PDF アップロード PoC</h1>
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <br /><br />
      <button onClick={handleUpload} disabled={uploadLoading}>
        {uploadLoading ? "アップロード中..." : "アップロード"}
      </button>
      {uploadMessage && <p>{uploadMessage}</p>}

      <hr style={{ margin: "2rem 0" }} />

      <h2>メール取得 PoC</h2>
      <p>Microsoft Graph API で自分の最新メール10件を取得し、GCSに保存します。</p>
      <button onClick={handleFetchMail} disabled={mailLoading}>
        {mailLoading ? "取得中..." : "メールを取得"}
      </button>
      {mailMessage && <p>{mailMessage}</p>}
    </main>
  );
}
```

- [ ] **Step 2: TypeScriptの型チェック**

```bash
cd frontend
npx tsc --noEmit
```

Expected: エラーなし

- [ ] **Step 3: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add frontend/app/page.tsx
git commit -m "feat(frontend): トップページにメール取得ボタンと結果表示を追加"
git push
```

---

## Task 15: バックエンドのビルド・Cloud Runデプロイ（手動）

**Files:**
- （デプロイ作業のみ、ファイル変更なし）

> このタスクはてつてつさんが手動で実施。`memo.md` の Step 17-3, 17-4 と同じ内容。

- [ ] **Step 1: Dockerイメージをビルド・プッシュ**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
PROJECT_ID=$(gcloud config get-value project)

cd backend
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/backend:graph-v1 \
  .
cd ..
```

- [ ] **Step 2: Cloud Run に再デプロイ**

```bash
PROJECT_ID=$(gcloud config get-value project)
BUCKET_NAME="poc-upload-${PROJECT_ID}"
# 実際のEntra ID値を入れる
ENTRA_TENANT_ID="<Entra IDテナントID>"
ENTRA_CLIENT_ID="<Entra IDクライアントID>"

gcloud run deploy poc-backend \
  --image=asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/backend:graph-v1 \
  --region=asia-northeast1 \
  --service-account=poc-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --ingress=internal \
  --no-allow-unauthenticated \
  --max-instances=3 \
  --set-env-vars=BUCKET_NAME=${BUCKET_NAME},ENTRA_TENANT_ID=${ENTRA_TENANT_ID},ENTRA_CLIENT_ID=${ENTRA_CLIENT_ID},REDIRECT_URI=https://poc.tetutetu214.com/api/graph/callback \
  --set-secrets=ENTRA_CLIENT_SECRET=poc-entra-client-secret:latest
```

- [ ] **Step 3: ログが正常に出るか確認（1分ほど待つ）**

```bash
gcloud run services logs read poc-backend --region=asia-northeast1 --limit=50
```

Expected: FastAPI起動ログが出ていて、エラーがない

---

## Task 16: フロントエンドのビルド・Cloud Runデプロイ（手動）

**Files:**
- （デプロイ作業のみ）

- [ ] **Step 1: Dockerイメージをビルド・プッシュ**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
PROJECT_ID=$(gcloud config get-value project)

cd frontend
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/frontend:graph-v1 \
  .
cd ..
```

- [ ] **Step 2: 既存の BACKEND_URL を確認**

```bash
gcloud run services describe poc-frontend \
  --region=asia-northeast1 \
  --format='value(spec.template.spec.containers[0].env)'
```

BACKEND_URL の値をメモ。

- [ ] **Step 3: Cloud Run に再デプロイ**

```bash
PROJECT_ID=$(gcloud config get-value project)
BACKEND_URL="<上記で確認したURL>"

gcloud run deploy poc-frontend \
  --image=asia-northeast1-docker.pkg.dev/${PROJECT_ID}/poc-repo/frontend:graph-v1 \
  --region=asia-northeast1 \
  --service-account=poc-frontend-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --no-allow-unauthenticated \
  --max-instances=3 \
  --network=default \
  --subnet=default \
  --vpc-egress=all-traffic \
  --set-env-vars=BACKEND_URL=${BACKEND_URL}
```

- [ ] **Step 4: ログ確認**

```bash
gcloud run services logs read poc-frontend --region=asia-northeast1 --limit=50
```

Expected: Next.js起動ログが出ていて、エラーがない

---

## Task 17: E2E 動作確認

**Files:**
- （ブラウザ操作のみ。結果を `docs/knowledge.md` に追記する）

- [ ] **Step 1: 初回フロー（同意あり）**

1. ブラウザで `https://poc.tetutetu214.com` にアクセス
2. 既存IAP認証を通過
3. 「メールを取得」ボタンをクリック
4. Entra IDの同意画面が出ることを確認（`Mail.Read` と `offline_access` が要求されている）
5. 「承諾」
6. `/` に戻る

Expected: 画面遷移が成功。コンソールにエラーが出ていない

- [ ] **Step 2: 2回目以降（同意なし）**

1. 再度「メールを取得」ボタンをクリック
2. 同意画面なしで即取得されることを確認

Expected: 「取得成功：N件 / gs://poc-upload-.../mails/.../...json」が表示

- [ ] **Step 3: Firestore の中身確認**

GCPコンソールで Firestore → `graph_tokens` コレクション → ユーザーメールのドキュメント：
- `access_token`、`refresh_token`、`expires_at`、`scope`、`updated_at` があること

- [ ] **Step 4: GCS の中身確認**

```bash
PROJECT_ID=$(gcloud config get-value project)
gcloud storage ls gs://poc-upload-${PROJECT_ID}/mails/
gcloud storage cat gs://poc-upload-${PROJECT_ID}/mails/<user>/<timestamp>.json | head -50
```

Expected: JSONに件名・bodyPreview等が入っている

- [ ] **Step 5: リフレッシュ確認（任意）**

Firestore の `expires_at` を手動で過去日時に書き換え → 再度ボタン → エラーなく取得成功 → `access_token` と `expires_at` が更新されることを確認。

- [ ] **Step 6: 結果とハマった点を `docs/knowledge.md` に追記してコミット**

例：
```markdown
## Phase 7（Graph API メール取得）動作確認結果

- 初回同意：成功
- 2回目取得：同意なしで成功
- Firestore：保存OK
- GCS：JSON保存OK
- リフレッシュ動作：OK

### 気づき・ハマりポイント
- （実際にハマった箇所を記録）
```

```bash
git add docs/knowledge.md
git commit -m "docs(knowledge): Phase 7 Graph API動作確認結果を追記"
git push
```

---

## Task 18: docs 更新とPR作成

**Files:**
- Modify: `docs/todo.md`
- Modify: `docs/spec.md`
- Modify: `docs/plan.md`

- [ ] **Step 1: `docs/todo.md` の Phase 7 タスクを完了にマーク**

未完了（`- [ ]`）を完了（`- [x]`）に書き換える。

- [ ] **Step 2: `docs/spec.md` に Graph API 章を追記**

Graph API 追加に伴う仕様（新エンドポイント、Firestore、Secret Manager 追加）を既存spec.md に追記。詳細は `docs/superpowers/specs/2026-04-19-graph-api-mail-design.md` を参照するリンクを張る。

- [ ] **Step 3: `docs/plan.md` に Phase 7 を追記**

Phase 7 節を追加し、本機能の目的とスコープを書く。

- [ ] **Step 4: コミット**

```bash
cd /home/tetutetu/projects/gcp-auth-poc
git add docs/todo.md docs/spec.md docs/plan.md
git commit -m "docs: Phase 7 Graph API機能の仕様・計画・todoを更新"
git push
```

- [ ] **Step 5: PR 作成**

```bash
gh pr create --title "feat(graph): Microsoft Graph APIによるメール取得機能を追加" --body "$(cat <<'EOF'
## 概要

既存PoCに Microsoft Graph API でユーザーのメール10件を取得してGCSに保存する機能を追加。

- OAuth 2.0 Authorization Code Flow（delegated）
- トークン保管：Firestore
- シークレット保管：Secret Manager
- CSRF対策：state + HttpOnly Cookie
- アクセストークン失効時はリフレッシュトークンで自動更新

## 追加リソース

- Secret Manager: `poc-entra-client-secret`
- Firestore: `(default)` DB, `graph_tokens` コレクション

## テスト

- バックエンド：pytest で21テスト通過（config/firestore_tokens/oauth/graph_client/gcs_writer/routes_graph）
- フロントエンド：TypeScript型チェック通過
- E2E：初回同意→取得、2回目取得（同意なし）、Firestore保存、GCS保存、リフレッシュ動作をすべて確認

## 参考ドキュメント

- 設計書：`docs/superpowers/specs/2026-04-19-graph-api-mail-design.md`
- 実装計画：`docs/superpowers/plans/2026-04-19-graph-api-mail.md`
- 手順書：`memo.md` Step 14〜19

## Test plan
- [ ] ブラウザで初回フロー動作確認
- [ ] 2回目以降の取得動作確認
- [ ] Firestore / GCS の保存確認
EOF
)"
```

Expected: PR URLが表示される

---

## 備考・トラブルシューティング

### pytest で google-cloud-firestore のインポートに時間がかかる

`conftest.py` で `firestore.Client()` をimportしているとテスト起動が遅い。`Any` 型で受け取る設計にしているので実インポート不要。問題が起きたら該当importを遅延importに変える。

### Cloud Run 再デプロイ後に Graph ルートで 500

- `ENTRA_CLIENT_SECRET` が正しくSecret Manager経由で注入されているか（`gcloud run services describe poc-backend` で `valueFrom` が設定されているか）
- `poc-backend-sa` に `roles/secretmanager.secretAccessor` と `roles/datastore.user` が両方あるか

### state Cookie がブラウザで落ちる

- `SameSite=Lax` だと Entra ID からのリダイレクト（トップレベルナビゲーション）には付与される
- `Secure` 属性のため HTTPS 必須。ローカルHTTPでは動かない点に注意（本番は常にHTTPS）

### Firestore Native と Datastore の競合

- プロジェクトごとに `(default)` DBは1つ。Datastoreモードで作成済みだと Native で作成不可。必要なら一度削除してから作成し直す
