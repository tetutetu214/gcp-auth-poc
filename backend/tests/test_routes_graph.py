"""routes_graph.pyのテスト"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes_graph import build_router, GraphDeps
from config import AppConfig


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
    headers = {
        "X-Goog-Authenticated-User-Email":
            "accounts.google.com:user@example.com"
    }
    response = client.get("/api/graph/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "auth_required"
    assert "login.microsoftonline.com" in body["authorize_url"]
    # state Cookieが立っている
    assert "graph_oauth_state" in response.cookies


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

    with respx.mock(
        base_url="https://graph.microsoft.com",
        assert_all_mocked=False,
        assert_all_called=False,
    ) as graph_mock:
        # /me は GCSパス用のメールアドレス取得のためモック
        graph_mock.get("/v1.0/me").respond(
            json={
                "mail": "user@example.com",
                "userPrincipalName": "user@example.com",
            }
        )
        graph_mock.get("/v1.0/me/messages").respond(
            json={
                "value": [
                    {"subject": "件名1", "bodyPreview": "p1"},
                    {"subject": "件名2", "bodyPreview": "p2"},
                ]
            }
        )

        client = TestClient(_make_app(deps))
        headers = {
            "X-Goog-Authenticated-User-Email":
                "accounts.google.com:user@example.com"
        }
        response = client.get("/api/graph/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 2
    assert body["gcs_path"].startswith(
        "gs://test-bucket/mails/user@example.com/"
    )
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

    with respx.mock(
        assert_all_mocked=False, assert_all_called=False
    ) as mocker:
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
        mocker.get("https://graph.microsoft.com/v1.0/me").respond(
            json={
                "mail": "user@example.com",
                "userPrincipalName": "user@example.com",
            }
        )
        mocker.get(
            "https://graph.microsoft.com/v1.0/me/messages"
        ).respond(json={"value": [{"subject": "件名"}]})

        client = TestClient(_make_app(deps))
        headers = {
            "X-Goog-Authenticated-User-Email":
                "accounts.google.com:user@example.com"
        }
        response = client.get("/api/graph/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 1


def test_callback_exchanges_code_and_saves_token() -> None:
    """stateが一致した場合、codeをトークンに交換してFirestoreに保存する"""
    firestore = MagicMock()
    storage = MagicMock()
    deps = GraphDeps(
        config=_base_config(),
        firestore_client=firestore,
        storage_client=storage,
    )

    with respx.mock(
        assert_all_mocked=False, assert_all_called=False
    ) as mocker:
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
        headers = {
            "X-Goog-Authenticated-User-Email":
                "accounts.google.com:user@example.com"
        }
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
    headers = {
        "X-Goog-Authenticated-User-Email":
            "accounts.google.com:user@example.com"
    }

    response = client.get(
        "/api/graph/callback?code=CODE&state=DIFFERENT",
        headers=headers,
    )

    assert response.status_code == 400
