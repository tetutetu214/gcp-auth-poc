"""oauth.pyのテスト（state生成・認可URL）"""
from urllib.parse import urlparse, parse_qs

from oauth import generate_state, build_authorize_url


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
