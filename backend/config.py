"""環境変数からアプリ設定を読み込むモジュール"""
import os
from dataclasses import dataclass


class ConfigError(Exception):
    """設定値が不正な場合に投げる例外"""


@dataclass(frozen=True)
class AppConfig:
    """アプリ全体で共有する設定値"""
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    bucket_name: str


def load_config() -> AppConfig:
    """環境変数から設定を読み込む"""
    required = {
        "ENTRA_TENANT_ID": None,
        "ENTRA_CLIENT_ID": None,
        "ENTRA_CLIENT_SECRET": None,
        "REDIRECT_URI": None,
        "BUCKET_NAME": None,
    }
    missing: list[str] = []
    for key in required:
        value = os.environ.get(key)
        if not value:
            missing.append(key)
        else:
            required[key] = value
    if missing:
        raise ConfigError(
            f"環境変数が不足: {', '.join(missing)}"
        )

    return AppConfig(
        tenant_id=required["ENTRA_TENANT_ID"],
        client_id=required["ENTRA_CLIENT_ID"],
        client_secret=required["ENTRA_CLIENT_SECRET"],
        redirect_uri=required["REDIRECT_URI"],
        bucket_name=required["BUCKET_NAME"],
    )
