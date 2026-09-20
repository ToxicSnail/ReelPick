import asyncio

import httpx

from kinotyk.clients.telegram import TelegramClient


def test_send_message_payload() -> None:
    async def scenario() -> None:
        captured: list[dict] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(__import__("json").loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = TelegramClient(http, bot_token="123:test", poll_timeout_seconds=30)
            result = await client.send_message(5, "Привет", reply_markup={"inline_keyboard": []})

        assert result["message_id"] == 1
        assert captured[0]["chat_id"] == 5
        assert captured[0]["parse_mode"] == "HTML"

    asyncio.run(scenario())
