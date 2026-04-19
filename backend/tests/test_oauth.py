"""oauth.pyのテスト（state生成・認可URL・トークン交換・リフレッシュ）"""
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import httpx
import pytest
import respx

from oauth import (
    generate_state,
    build_authorize_url,
    exchange_code_for_token,
    refresh_access_token,
)


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


@pytest.mark.asyncio
async def test_exchange_code_for_token_sends_correct_request() -> None:
    """認可コード交換が正しいパラメータでPOSTされる"""
    async with respx.mock(
        base_url="https://login.microsoftonline.com"
    ) as mock:
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
    async with respx.mock(
        base_url="https://login.microsoftonline.com"
    ) as mock:
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
    async with respx.mock(
        base_url="https://login.microsoftonline.com"
    ) as mock:
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
