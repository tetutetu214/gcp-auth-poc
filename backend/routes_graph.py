"""/api/graph/* のFastAPIルーター"""
import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from config import AppConfig
from firestore_tokens import load_token, save_token
from oauth import (
    generate_state,
    build_authorize_url,
    exchange_code_for_token,
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


def _extract_email_from_iap_jwt(jwt_token: str | None) -> str:
    """IAP JWT（X-Goog-IAP-JWT-Assertion）から email クレームを取り出す

    ※ PoC用途のため署名検証は省略。本番では google-auth 等で検証すること。
    外部ID（Identity Platform 経由の Entra ID）使用時は、メアドヘッダの代わりに
    このJWT経由でユーザー識別することが多い。
    """
    if not jwt_token:
        return ""
    try:
        parts = jwt_token.split(".")
        if len(parts) != 3:
            return ""
        # base64url デコード（パディング補正）
        payload = parts[1]
        padding = "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        claims = json.loads(decoded)
        return claims.get("email", "")
    except (ValueError, json.JSONDecodeError):
        return ""


def _resolve_user_email(
    email_header: str | None,
    jwt_header: str | None,
) -> str:
    """利用可能な複数のIAPヘッダから user email を解決する"""
    from_header = _extract_user_email(email_header)
    if from_header:
        return from_header
    return _extract_email_from_iap_jwt(jwt_header)


def build_router(deps: GraphDeps) -> APIRouter:
    """GraphDepsを束縛したAPIRouterを返す"""
    router = APIRouter()

    @router.get("/api/graph/sync")
    async def sync(
        x_goog_authenticated_user_email: str | None = Header(default=None),
        x_goog_iap_jwt_assertion: str | None = Header(default=None),
    ) -> Response:
        user_email = _resolve_user_email(
            x_goog_authenticated_user_email,
            x_goog_iap_jwt_assertion,
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

    @router.get("/api/graph/callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        x_goog_authenticated_user_email: str | None = Header(
            default=None
        ),
        x_goog_iap_jwt_assertion: str | None = Header(default=None),
    ) -> Response:
        """Entra IDからの認可コールバック。state検証→トークン交換→Firestore保存"""
        user_email = _resolve_user_email(
            x_goog_authenticated_user_email,
            x_goog_iap_jwt_assertion,
        )
        cookie_state = request.cookies.get(STATE_COOKIE_NAME)

        # state検証（CSRF対策）
        if (
            not code
            or not state
            or not cookie_state
            or state != cookie_state
        ):
            return JSONResponse(
                {"detail": "state検証に失敗しました"},
                status_code=400,
            )

        # 認可コード → トークン交換
        record = await exchange_code_for_token(
            tenant_id=deps.config.tenant_id,
            client_id=deps.config.client_id,
            client_secret=deps.config.client_secret,
            code=code,
            redirect_uri=deps.config.redirect_uri,
        )
        save_token(deps.firestore_client, user_email, record)

        # 元のページへリダイレクト。使い終わったstate Cookieを削除
        response = RedirectResponse(url="/", status_code=302)
        response.delete_cookie(STATE_COOKIE_NAME)
        return response

    return router
