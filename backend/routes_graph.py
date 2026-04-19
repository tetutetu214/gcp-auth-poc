"""/api/graph/* のFastAPIルーター"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse

from config import AppConfig
from firestore_tokens import load_token, save_token
from oauth import (
    generate_state,
    build_authorize_url,
    refresh_access_token,
)
from graph_client import list_messages
from gcs_writer import save_mails_to_gcs


# state を一時的に保持するCookie名と有効期限（10分）
STATE_COOKIE_NAME = "graph_oauth_state"
STATE_COOKIE_MAX_AGE = 600


@dataclass
class GraphDeps:
    """ルーターが必要とする外部依存"""
    config: AppConfig
    firestore_client: Any
    storage_client: Any


def _extract_user_email(raw: str | None) -> str:
    """IAPヘッダ `X-Goog-Authenticated-User-Email` からメール部分のみ取り出す

    例: 'accounts.google.com:user@example.com' -> 'user@example.com'
    """
    if not raw:
        return ""
    if ":" in raw:
        return raw.split(":", 1)[1]
    return raw


def build_router(deps: GraphDeps) -> APIRouter:
    """GraphDepsを束縛したAPIRouterを返す"""
    router = APIRouter()

    @router.get("/api/graph/sync")
    async def sync(
        x_goog_authenticated_user_email: str | None = Header(default=None),
    ) -> Response:
        user_email = _extract_user_email(
            x_goog_authenticated_user_email
        )
        record = (
            load_token(deps.firestore_client, user_email)
            if user_email
            else None
        )

        if record is None:
            # 未認可：認可URLをJSONで返し、stateをCookieに保存
            state = generate_state()
            authorize_url = build_authorize_url(
                tenant_id=deps.config.tenant_id,
                client_id=deps.config.client_id,
                redirect_uri=deps.config.redirect_uri,
                state=state,
            )
            response = JSONResponse(
                {
                    "status": "auth_required",
                    "authorize_url": authorize_url,
                }
            )
            response.set_cookie(
                key=STATE_COOKIE_NAME,
                value=state,
                max_age=STATE_COOKIE_MAX_AGE,
                httponly=True,
                secure=True,
                samesite="lax",
            )
            return response

        # アクセストークンが失効間近ならリフレッシュ
        if record.is_expired():
            refreshed = await refresh_access_token(
                tenant_id=deps.config.tenant_id,
                client_id=deps.config.client_id,
                client_secret=deps.config.client_secret,
                refresh_token=record.refresh_token,
            )
            # Entra IDはrefresh_tokenを再発行する場合もしない場合もある
            # 返ってこない場合は既存のrefresh_tokenを引き継ぐ
            if not refreshed.refresh_token:
                refreshed.refresh_token = record.refresh_token
            save_token(deps.firestore_client, user_email, refreshed)
            record = refreshed

        # Graph APIから最新メールを10件取得
        messages = await list_messages(
            access_token=record.access_token, top=10
        )

        # GCSに保存
        gcs_path = save_mails_to_gcs(
            storage_client=deps.storage_client,
            bucket_name=deps.config.bucket_name,
            user_email=user_email,
            messages=messages,
            now=datetime.now(timezone.utc),
        )

        return JSONResponse(
            {
                "status": "ok",
                "count": len(messages),
                "gcs_path": gcs_path,
            }
        )

    return router
