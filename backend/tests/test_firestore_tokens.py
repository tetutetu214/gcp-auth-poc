"""firestore_tokens.pyのテスト"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from firestore_tokens import (
    TokenRecord,
    save_token,
    load_token,
    delete_token,
)


def _make_fake_client(
    exists: bool, data: dict | None = None
) -> MagicMock:
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
    client.collection.return_value.document.assert_called_once_with(
        "user@example.com"
    )
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
