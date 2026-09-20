from __future__ import annotations

import asyncio
import logging
from typing import Any

from kinotyk.clients.cinemeta import CinemetaError
from kinotyk.clients.telegram import TelegramAPIError, TelegramClient
from kinotyk.db import Database
from kinotyk.domain import Movie
from kinotyk.services.recommendation import RecommendationService
from kinotyk.ui import (
    collection_keyboard,
    collection_page_keyboard,
    collection_page_text,
    collection_summary_text,
    genres_keyboard,
    genres_text,
    help_text,
    main_menu_keyboard,
    main_menu_text,
    movie_caption,
    movie_keyboard,
)

logger = logging.getLogger(__name__)
PAGE_SIZE = 8


class KinotykApp:
    def __init__(
        self,
        *,
        telegram: TelegramClient,
        database: Database,
        recommendations: RecommendationService,
    ) -> None:
        self.telegram = telegram
        self.database = database
        self.recommendations = recommendations
        self._tasks: set[asyncio.Task[Any]] = set()

    async def run(self) -> None:
        self.database.init()
        try:
            await self.telegram.set_commands()
        except TelegramAPIError:
            logger.warning("Could not register Telegram bot commands; continuing")

        offset: int | None = None
        logger.info("Kinotyk long polling started")
        while True:
            try:
                updates = await self.telegram.get_updates(offset)
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = update_id + 1
                    task = asyncio.create_task(self._safe_handle_update(update))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
            except TelegramAPIError:
                logger.exception("Telegram polling error")
                await asyncio.sleep(2)

    async def _safe_handle_update(self, update: dict[str, Any]) -> None:
        try:
            await self.handle_update(update)
        except Exception:
            logger.exception("Unhandled update processing error")

    async def handle_update(self, update: dict[str, Any]) -> None:
        if isinstance(update.get("message"), dict):
            await self._handle_message(update["message"])
            return
        if isinstance(update.get("callback_query"), dict):
            await self._handle_callback(update["callback_query"])

    async def _handle_message(self, message: dict[str, Any]) -> None:
        user = message.get("from") or {}
        chat = message.get("chat") or {}
        telegram_id = user.get("id")
        chat_id = chat.get("id")
        if not isinstance(telegram_id, int) or not isinstance(chat_id, int):
            return

        self._upsert_user(user)
        text = str(message.get("text") or "").strip()
        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()

        if command == "/movie":
            await self.telegram.send_message(chat_id, genres_text(), reply_markup=genres_keyboard())
        elif command == "/collection":
            await self._send_collection(chat_id, telegram_id)
        elif command == "/help":
            await self.telegram.send_message(
                chat_id, help_text(), reply_markup=main_menu_keyboard()
            )
        else:
            await self.telegram.send_message(
                chat_id,
                main_menu_text(user.get("first_name")),
                reply_markup=main_menu_keyboard(),
            )

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        callback_id = callback.get("id")
        user = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        telegram_id = user.get("id")
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        data = str(callback.get("data") or "")

        if not isinstance(callback_id, str):
            return
        if not isinstance(telegram_id, int) or not isinstance(chat_id, int):
            await self.telegram.answer_callback_query(
                callback_id,
                "Эта кнопка больше не поддерживается.",
                show_alert=True,
            )
            return

        self._upsert_user(user)

        if data == "menu:find" or data == "nav:genres":
            await self.telegram.answer_callback_query(callback_id)
            await self._replace_with_message(chat_id, message_id, genres_text(), genres_keyboard())
            return

        if data == "menu:collection":
            await self.telegram.answer_callback_query(callback_id)
            await self._replace_with_collection(chat_id, telegram_id, message_id)
            return

        if data == "nav:main":
            await self.telegram.answer_callback_query(callback_id)
            await self._replace_with_message(
                chat_id,
                message_id,
                main_menu_text(user.get("first_name")),
                main_menu_keyboard(),
            )
            return

        if data.startswith("genre:"):
            await self.telegram.answer_callback_query(callback_id)
            genre_key = data.partition(":")[2]
            await self._show_recommendation(chat_id, telegram_id, genre_key, message_id)
            return

        if data.startswith("mv:"):
            await self._handle_movie_action(
                callback_id,
                chat_id,
                telegram_id,
                message_id,
                data,
            )
            return

        if data.startswith("col:"):
            await self.telegram.answer_callback_query(callback_id)
            await self._handle_collection_page(chat_id, telegram_id, message_id, data)
            return

        await self.telegram.answer_callback_query(
            callback_id,
            "Кнопка устарела. Открой главное меню заново.",
            show_alert=True,
        )

    async def _handle_movie_action(
        self,
        callback_id: str,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
        data: str,
    ) -> None:
        parts = data.split(":")
        if len(parts) != 4:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        _, action, imdb_id, genre_key = parts

        if action == "n":
            await self.telegram.answer_callback_query(callback_id)
            await self._show_recommendation(chat_id, telegram_id, genre_key, message_id)
            return

        try:
            movie = await self.recommendations.get_movie(imdb_id)
        except (CinemetaError, ValueError):
            await self.telegram.answer_callback_query(
                callback_id,
                "Не смог загрузить фильм. Попробуй ещё раз.",
                show_alert=True,
            )
            return

        if action == "w":
            self.database.mark_watched(telegram_id, movie)
            await self.telegram.answer_callback_query(callback_id, "✅ Добавил в просмотренные")
            await self._show_recommendation(chat_id, telegram_id, genre_key, message_id)
            return

        if action == "s":
            self.database.mark_skipped(telegram_id, movie)
            await self.telegram.answer_callback_query(callback_id, "🙅 Больше не буду предлагать")
            await self._show_recommendation(chat_id, telegram_id, genre_key, message_id)
            return

        if action == "f":
            enabled = self.database.toggle_favorite(telegram_id, movie)
            text = "❤️ Добавил в избранное" if enabled else "Убрал из избранного"
            await self.telegram.answer_callback_query(callback_id, text)
            return

        if action == "l":
            enabled = self.database.toggle_watchlist(telegram_id, movie)
            text = "📌 Добавил в «На потом»" if enabled else "Убрал из «На потом»"
            await self.telegram.answer_callback_query(callback_id, text)
            return

        await self.telegram.answer_callback_query(callback_id, "Неизвестное действие.")

    async def _show_recommendation(
        self,
        chat_id: int,
        telegram_id: int,
        genre_key: str,
        old_message_id: int | None,
    ) -> None:
        await self.telegram.send_chat_action(chat_id, "typing")
        try:
            movie = await self.recommendations.recommend(telegram_id, genre_key)
        except ValueError:
            movie = None

        if movie is None:
            await self._replace_with_message(
                chat_id,
                old_message_id,
                "😿 <b>Подходящие фильмы закончились.</b>\n\n"
                "Попробуй другой жанр или загляни позже.",
                genres_keyboard(),
            )
            return

        if isinstance(old_message_id, int):
            await self.telegram.delete_message(chat_id, old_message_id)
        await self._send_movie(chat_id, movie, genre_key)

    async def _send_movie(self, chat_id: int, movie: Movie, genre_key: str) -> None:
        caption = movie_caption(movie)
        markup = movie_keyboard(movie, genre_key)
        if movie.poster_url:
            try:
                await self.telegram.send_photo(
                    chat_id,
                    movie.poster_url,
                    caption,
                    reply_markup=markup,
                )
                return
            except TelegramAPIError:
                logger.warning(
                    "Telegram could not send poster for %s; falling back to text",
                    movie.imdb_id,
                )
        await self.telegram.send_message(chat_id, caption, reply_markup=markup)

    async def _send_collection(self, chat_id: int, telegram_id: int) -> None:
        stats = self.database.collection_stats(telegram_id)
        await self.telegram.send_message(
            chat_id,
            collection_summary_text(stats),
            reply_markup=collection_keyboard(),
        )

    async def _replace_with_collection(
        self,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
    ) -> None:
        stats = self.database.collection_stats(telegram_id)
        await self._replace_with_message(
            chat_id,
            message_id,
            collection_summary_text(stats),
            collection_keyboard(),
        )

    async def _handle_collection_page(
        self,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
        data: str,
    ) -> None:
        parts = data.split(":")
        if len(parts) != 3:
            return
        _, collection, raw_offset = parts
        try:
            offset = max(0, int(raw_offset))
            movies, total = self.database.list_collection(
                telegram_id,
                collection,
                limit=PAGE_SIZE,
                offset=offset,
            )
        except ValueError:
            return

        text = collection_page_text(collection, movies, total=total, offset=offset)
        markup = collection_page_keyboard(collection, offset, total, PAGE_SIZE)
        await self._replace_with_message(chat_id, message_id, text, markup)

    async def _replace_with_message(
        self,
        chat_id: int,
        message_id: int | None,
        text: str,
        reply_markup: dict[str, Any],
    ) -> None:
        if isinstance(message_id, int):
            await self.telegram.delete_message(chat_id, message_id)
        await self.telegram.send_message(chat_id, text, reply_markup=reply_markup)

    def _upsert_user(self, user: dict[str, Any]) -> None:
        telegram_id = user.get("id")
        if not isinstance(telegram_id, int):
            return
        self.database.upsert_user(
            telegram_id,
            str(user.get("username")) if user.get("username") else None,
            str(user.get("first_name")) if user.get("first_name") else None,
            str(user.get("language_code")) if user.get("language_code") else None,
        )
