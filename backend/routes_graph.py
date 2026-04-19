"""/api/graph/* のFastAPIルーター"""
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse

from config import AppConfig
from firestore_tokens import load_token
from oauth import generate_state, build_authorize_url


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

        # トークンあり：Task 9 で実装
        return JSONResponse(
            {"status": "ok", "count": 0, "gcs_path": ""}
        )

    return router
