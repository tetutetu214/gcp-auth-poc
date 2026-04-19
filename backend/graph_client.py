"""Microsoft Graph API クライアント（/me/messages用）"""
import httpx

MESSAGES_ENDPOINT = "https://graph.microsoft.com/v1.0/me/messages"

# 取得するフィールド。bodyは含めずプレビューのみ（通信量削減）
SELECT_FIELDS = "subject,from,receivedDateTime,bodyPreview"


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
        response.raise_for_status()
        body = response.json()
    messages: list[dict] = body.get("value", [])
    return messages
