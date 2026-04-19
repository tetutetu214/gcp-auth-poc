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
