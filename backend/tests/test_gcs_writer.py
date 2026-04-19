"""gcs_writer.pyのテスト"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

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
