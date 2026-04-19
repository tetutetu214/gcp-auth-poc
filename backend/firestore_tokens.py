"""Firestore graph_tokensコレクションのリポジトリ"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any


COLLECTION = "graph_tokens"
# 余裕を持たせて失効扱いにする秒数（この秒数以内に切れるなら既に失効とみなす）
EXPIRY_SAFETY_SECONDS = 60


@dataclass
class TokenRecord:
    """ユーザー1人分のトークンレコード"""
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str
    user_email: str = ""  # id_token から抽出した表示用メアド（GCSパスで利用）

    def is_expired(self) -> bool:
        """アクセストークンが失効間近か"""
        now = datetime.now(timezone.utc)
        return self.expires_at <= now + timedelta(
            seconds=EXPIRY_SAFETY_SECONDS
        )


def save_token(
    client: Any, user_email: str, record: TokenRecord
) -> None:
    """ユーザーのトークンを上書き保存する"""
    doc_ref = client.collection(COLLECTION).document(user_email)
    doc_ref.set(
        {
            "access_token": record.access_token,
            "refresh_token": record.refresh_token,
            "expires_at": record.expires_at,
            "scope": record.scope,
            "user_email": record.user_email,
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
        user_email=data.get("user_email", ""),
    )


def delete_token(client: Any, user_email: str) -> None:
    """ユーザーのトークンを削除する"""
    client.collection(COLLECTION).document(user_email).delete()
