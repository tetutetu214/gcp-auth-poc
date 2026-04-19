"""graph_client.pyのテスト"""
from urllib.parse import unquote

import httpx
import pytest
import respx

from graph_client import list_messages


@pytest.mark.asyncio
async def test_list_messages_calls_correct_endpoint() -> None:
    """Graph APIの /me/messages を正しいヘッダで叩く"""
    async with respx.mock(
        base_url="https://graph.microsoft.com"
    ) as mock:
        route = mock.get("/v1.0/me/messages").respond(
            json={
                "value": [
                    {
                        "subject": "件名1",
                        "from": {
                            "emailAddress": {"address": "a@x.com"}
                        },
                        "receivedDateTime": "2026-04-19T00:00:00Z",
                        "bodyPreview": "プレビュー1",
                    },
                ]
            }
        )

        at_value = "AT"
        messages = await list_messages(access_token=at_value, top=10)

        assert len(messages) == 1
        assert messages[0]["subject"] == "件名1"

        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer AT"
        # URL の $ は %24 にエンコードされるのでデコードして検証
        decoded_url = unquote(str(request.url))
        assert "$top=10" in decoded_url
        assert "$select=" in decoded_url


@pytest.mark.asyncio
async def test_list_messages_raises_on_401() -> None:
    """401が返ったら例外（呼び元でリフレッシュ判定させる）"""
    async with respx.mock(
        base_url="https://graph.microsoft.com"
    ) as mock:
        mock.get("/v1.0/me/messages").respond(status_code=401)

        with pytest.raises(httpx.HTTPStatusError):
            bad_value = "BAD"
            await list_messages(access_token=bad_value, top=10)
