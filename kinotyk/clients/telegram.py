from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramAPIError(RuntimeError):
    pass


class TelegramClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        bot_token: str,
        poll_timeout_seconds: int,
    ) -> None:
        self.client = client
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.poll_timeout_seconds = poll_timeout_seconds

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self.client.post(
                f"{self.base_url}/{method}",
                json=payload,
                timeout=max(self.poll_timeout_seconds + 5, 15)
                if method == "getUpdates"
                else 15,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramAPIError(f"Telegram method {method} failed") from exc

        if not isinstance(data, dict) or not data.get("ok"):
            description = (
                data.get("description", "unknown Telegram API error")
                if isinstance(data, dict)
                else "invalid response"
            )
            raise TelegramAPIError(f"Telegram method {method}: {description}")
        return data.get("result")

    async def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": self.poll_timeout_seconds,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload)
        return result if isinstance(result, list) else []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self._call("sendMessage", payload)
        return result if isinstance(result, dict) else {}

    async def send_photo(
        self,
        chat_id: int,
        photo_url: str,
        caption: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self._call("sendPhoto", payload)
        return result if isinstance(result, dict) else {}

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        *,
        show_alert: bool = False,
    ) -> None:
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text
        await self._call("answerCallbackQuery", payload)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self._call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        except TelegramAPIError:
            logger.debug("Could not delete message %s in chat %s", message_id, chat_id)

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            await self._call("sendChatAction", {"chat_id": chat_id, "action": action})
        except TelegramAPIError:
            logger.debug("Could not send chat action to %s", chat_id)

    async def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "Главное меню"},
            {"command": "movie", "description": "Подобрать фильм"},
            {"command": "collection", "description": "Моя коллекция"},
            {"command": "help", "description": "Помощь"},
        ]
        await self._call("setMyCommands", {"commands": commands, "language_code": "ru"})
