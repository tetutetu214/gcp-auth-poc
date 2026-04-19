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
