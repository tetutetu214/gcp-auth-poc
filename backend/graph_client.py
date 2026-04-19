"""Microsoft Graph API クライアント"""
import httpx

ME_ENDPOINT = "https://graph.microsoft.com/v1.0/me"
MESSAGES_ENDPOINT = "https://graph.microsoft.com/v1.0/me/messages"

# 取得するフィールド。bodyは含めずプレビューのみ（通信量削減）
SELECT_FIELDS = "subject,from,receivedDateTime,bodyPreview"


async def get_me_email(access_token: str) -> str:
    """Graph API /me を叩いてユーザーのメールアドレスを取得"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            ME_ENDPOINT,
            params={"$select": "mail,userPrincipalName"},
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
    # mail が null の場合は userPrincipalName を使う（組織アカウントの挙動）
    email = body.get("mail") or body.get("userPrincipalName") or ""
    return email


async def list_messages(
    access_token: str,
    top: int = 10,
) -> list[dict]:
    """直近のメール一覧を取得する（件名・送信元・受信日時・プレビューのみ）"""
    params = {
        "$top": str(top),
        "$select": SELECT_FIELDS,
        "$orderby": "receivedDateTime desc",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            MESSAGES_ENDPOINT,
            params=params,
            headers=headers,
        )
        if response.status_code >= 400:
            # エラー時の本文をログ出力（診断用）
            import logging
            logging.getLogger("uvicorn.error").error(
                f"Graph API error {response.status_code}: "
                f"{response.text[:500]}"
            )
        response.raise_for_status()
        body = response.json()
    messages: list[dict] = body.get("value", [])
    return messages
