"""OAuth 2.0 Authorization Code Flow 用のユーティリティ"""
import secrets
from urllib.parse import urlencode

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
