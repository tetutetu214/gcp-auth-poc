"""config.pyのテスト"""
import pytest

from config import load_config, ConfigError


def test_load_config_returns_all_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """必須環境変数がそろっていれば辞書で返す"""
    monkeypatch.setenv("ENTRA_TENANT_ID", "t1")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "c1")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "s1")
    monkeypatch.setenv("REDIRECT_URI", "https://example.com/cb")
    monkeypatch.setenv("BUCKET_NAME", "b1")

    cfg = load_config()

    assert cfg.tenant_id == "t1"
    assert cfg.client_id == "c1"
    assert cfg.client_secret == "s1"
    assert cfg.redirect_uri == "https://example.com/cb"
    assert cfg.bucket_name == "b1"


def test_load_config_missing_env_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """環境変数が足りないとConfigErrorを投げる"""
    for key in [
        "ENTRA_TENANT_ID",
        "ENTRA_CLIENT_ID",
        "ENTRA_CLIENT_SECRET",
        "REDIRECT_URI",
        "BUCKET_NAME",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError):
        load_config()
