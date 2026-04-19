"""OAuth 2.0 Authorization Code Flow 用のユーティリティ"""
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx

from firestore_tokens import TokenRecord

AUTHORIZE_ENDPOINT = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
)
TOKEN_ENDPOINT = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
)

# OIDC標準スコープ + offline_access（リフレッシュトークン取得）
# + Mail.Read（Graph APIでメール読取り）
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
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
        )
        response.raise_for_status()
        body = response.json()

    expires_in = int(body.get("expires_in", 3600))
    return TokenRecord(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", ""),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=expires_in),
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
