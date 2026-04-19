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
