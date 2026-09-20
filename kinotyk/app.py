from __future__ import annotations

import asyncio
import logging
from typing import Any

from kinotyk.clients.cinemeta import CinemetaError
from kinotyk.clients.shikimori import ShikimoriError
from kinotyk.clients.telegram import TelegramAPIError, TelegramClient
from kinotyk.db import Database
from kinotyk.domain import Anime, Movie
from kinotyk.services.anime_recommendation import AnimeRecommendationService
from kinotyk.services.recommendation import RecommendationService
from kinotyk.ui import (
    COLLECTION_LABELS,
    anime_caption,
    anime_details_keyboard,
    anime_genres_keyboard,
    anime_genres_text,
    anime_keyboard,
    anime_search_results_text,
    collection_keyboard,
    collection_page_keyboard,
    collection_page_text,
    collection_summary_text,
    genres_keyboard,
    genres_text,
    global_stats_text,
    help_text,
    main_menu_keyboard,
    main_menu_text,
    media_collection_keyboard,
    media_collection_text,
    movie_caption,
    movie_details_keyboard,
    movie_keyboard,
    movie_search_results_text,
    search_anime_keyboard,
    search_cancel_keyboard,
    search_media_keyboard,
    search_media_text,
    search_movie_keyboard,
    search_no_results_text,
    search_prompt_text,
    search_results_keyboard,
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
        anime_recommendations: AnimeRecommendationService,
        admin_ids: tuple[int, ...] = (),
    ) -> None:
        self.telegram = telegram
        self.database = database
        self.recommendations = recommendations
        self.anime_recommendations = anime_recommendations
        self.admin_ids = frozenset(admin_ids)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._awaiting_search: dict[int, str] = {}
        self._pending_search: dict[int, str] = {}

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
        elif command == "/anime":
            await self.telegram.send_message(
                chat_id,
                anime_genres_text(),
                reply_markup=anime_genres_keyboard(),
            )
        elif command == "/collection":
            await self._send_collection(chat_id, telegram_id)
        elif command == "/search":
            await self._start_search(chat_id, telegram_id, text)
        elif command == "/stats":
            await self._send_stats(chat_id, telegram_id)
        elif command == "/help":
            await self.telegram.send_message(
                chat_id,
                help_text(),
                reply_markup=main_menu_keyboard(),
            )
        else:
            media_type = self._awaiting_search.get(telegram_id)
            if media_type and text:
                self._awaiting_search.pop(telegram_id, None)
                await self._run_search(chat_id, telegram_id, media_type, text)
                return
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

        if data in {"menu:movie", "menu:find", "nav:movie_genres", "nav:genres"}:
            await self.telegram.answer_callback_query(callback_id)
            await self._replace_with_message(chat_id, message_id, genres_text(), genres_keyboard())
            return

        if data in {"menu:anime", "nav:anime_genres"}:
            await self.telegram.answer_callback_query(callback_id)
            await self._replace_with_message(
                chat_id,
                message_id,
                anime_genres_text(),
                anime_genres_keyboard(),
            )
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

        if data == "menu:search":
            await self.telegram.answer_callback_query(callback_id)
            self._pending_search.pop(telegram_id, None)
            self._awaiting_search.pop(telegram_id, None)
            await self._replace_with_message(
                chat_id,
                message_id,
                search_media_text(),
                search_media_keyboard(),
            )
            return

        if data in {"search:movie", "search:anime"}:
            await self.telegram.answer_callback_query(callback_id)
            await self._handle_search_choice(
                chat_id,
                telegram_id,
                message_id,
                data.split(":", 1)[1],
            )
            return

        if data == "search:cancel":
            self._pending_search.pop(telegram_id, None)
            self._awaiting_search.pop(telegram_id, None)
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
            parts = data.split(":")
            if len(parts) == 2:  # Backward compatibility with v1.1 movie buttons.
                _, genre_key = parts
                await self._show_movie_recommendation(
                    chat_id,
                    telegram_id,
                    genre_key,
                    message_id,
                )
                return
            if len(parts) == 3:
                _, media_type, genre_key = parts
                if media_type == "movie":
                    await self._show_movie_recommendation(
                        chat_id,
                        telegram_id,
                        genre_key,
                        message_id,
                    )
                    return
                if media_type == "anime":
                    await self._show_anime_recommendation(
                        chat_id,
                        telegram_id,
                        genre_key,
                        message_id,
                    )
                    return

        if data.startswith("mvv:"):
            await self._handle_movie_view(
                callback_id,
                chat_id,
                message_id,
                data,
            )
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

        if data.startswith("an:"):
            await self._handle_anime_action(
                callback_id,
                chat_id,
                telegram_id,
                message_id,
                data,
            )
            return

        if data.startswith("anv:"):
            await self._handle_anime_view(
                callback_id,
                chat_id,
                message_id,
                data,
            )
            return

        if data.startswith("rmv:"):
            await self._handle_media_remove(
                callback_id,
                chat_id,
                telegram_id,
                message_id,
                data,
            )
            return

        if data.startswith("smv:"):
            await self._handle_search_movie_view(callback_id, chat_id, data)
            return

        if data.startswith("sav:"):
            await self._handle_search_anime_view(callback_id, chat_id, data)
            return

        if data.startswith("media:"):
            await self.telegram.answer_callback_query(callback_id)
            media_type = data.partition(":")[2]
            if media_type not in {"movie", "anime"}:
                return
            await self._replace_with_media_collection(
                chat_id,
                telegram_id,
                message_id,
                media_type,
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
            await self._show_movie_recommendation(
                chat_id,
                telegram_id,
                genre_key,
                message_id,
            )
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
            await self._show_movie_recommendation(
                chat_id,
                telegram_id,
                genre_key,
                message_id,
            )
            return

        if action == "s":
            self.database.mark_skipped(telegram_id, movie)
            await self.telegram.answer_callback_query(callback_id, "🙅 Больше не буду предлагать")
            await self._show_movie_recommendation(
                chat_id,
                telegram_id,
                genre_key,
                message_id,
            )
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

    async def _handle_anime_action(
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
        _, action, raw_id, genre_key = parts
        try:
            anime_id = int(raw_id)
        except ValueError:
            await self.telegram.answer_callback_query(callback_id, "Некорректный ID аниме.")
            return

        if action == "n":
            await self.telegram.answer_callback_query(callback_id)
            await self._show_anime_recommendation(
                chat_id,
                telegram_id,
                genre_key,
                message_id,
            )
            return

        try:
            anime = await self.anime_recommendations.get_anime(anime_id)
        except (ShikimoriError, ValueError):
            await self.telegram.answer_callback_query(
                callback_id,
                "Не смог загрузить аниме. Попробуй ещё раз.",
                show_alert=True,
            )
            return

        if action == "w":
            self.database.mark_anime_watched(telegram_id, anime)
            await self.telegram.answer_callback_query(callback_id, "✅ Добавил в просмотренные")
            await self._show_anime_recommendation(
                chat_id,
                telegram_id,
                genre_key,
                message_id,
            )
            return

        if action == "s":
            self.database.mark_anime_skipped(telegram_id, anime)
            await self.telegram.answer_callback_query(callback_id, "🙅 Больше не буду предлагать")
            await self._show_anime_recommendation(
                chat_id,
                telegram_id,
                genre_key,
                message_id,
            )
            return

        if action == "f":
            enabled = self.database.toggle_anime_favorite(telegram_id, anime)
            text = "❤️ Добавил в избранное" if enabled else "Убрал из избранного"
            await self.telegram.answer_callback_query(callback_id, text)
            return

        if action == "l":
            enabled = self.database.toggle_anime_watchlist(telegram_id, anime)
            text = "📌 Добавил в «На потом»" if enabled else "Убрал из «На потом»"
            await self.telegram.answer_callback_query(callback_id, text)
            return

        await self.telegram.answer_callback_query(callback_id, "Неизвестное действие.")

    async def _show_movie_recommendation(
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

    async def _show_anime_recommendation(
        self,
        chat_id: int,
        telegram_id: int,
        genre_key: str,
        old_message_id: int | None,
    ) -> None:
        await self.telegram.send_chat_action(chat_id, "typing")
        try:
            anime = await self.anime_recommendations.recommend(telegram_id, genre_key)
        except ValueError:
            anime = None

        if anime is None:
            await self._replace_with_message(
                chat_id,
                old_message_id,
                "😿 <b>Подходящие аниме закончились.</b>\n\n"
                "Попробуй другой жанр или загляни позже.",
                anime_genres_keyboard(),
            )
            return

        if isinstance(old_message_id, int):
            await self.telegram.delete_message(chat_id, old_message_id)
        await self._send_anime(chat_id, anime, genre_key)

    async def _send_movie_details(
        self,
        chat_id: int,
        movie: Movie,
        markup: dict[str, Any],
    ) -> None:
        caption = movie_caption(movie)
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

    async def _send_movie(self, chat_id: int, movie: Movie, genre_key: str) -> None:
        await self._send_movie_details(chat_id, movie, movie_keyboard(movie, genre_key))

    async def _handle_anime_view(
        self,
        callback_id: str,
        chat_id: int,
        message_id: int | None,
        data: str,
    ) -> None:
        parts = data.split(":")
        if len(parts) != 4:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        _, raw_id, collection, raw_offset = parts
        try:
            anime_id = int(raw_id)
            offset = int(raw_offset)
        except ValueError:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        if (
            anime_id <= 0
            or offset < 0
            or collection not in {"watched", "favorite", "watchlist", "skipped"}
        ):
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return

        try:
            anime = await self.anime_recommendations.get_anime(anime_id)
        except (ShikimoriError, ValueError):
            await self.telegram.answer_callback_query(
                callback_id,
                "Не смог загрузить аниме. Попробуй ещё раз.",
                show_alert=True,
            )
            return
        await self.telegram.answer_callback_query(callback_id)

        if isinstance(message_id, int):
            await self.telegram.delete_message(chat_id, message_id)
        await self._send_anime_details(
            chat_id,
            anime,
            anime_details_keyboard(raw_id, collection, offset),
        )

    async def _handle_movie_view(
        self,
        callback_id: str,
        chat_id: int,
        message_id: int | None,
        data: str,
    ) -> None:
        parts = data.split(":")
        if len(parts) != 4:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        _, imdb_id, collection, raw_offset = parts
        try:
            offset = int(raw_offset)
        except ValueError:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        if (
            offset < 0
            or not imdb_id
            or collection not in {"watched", "favorite", "watchlist", "skipped"}
        ):
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
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
        await self.telegram.answer_callback_query(callback_id)

        if isinstance(message_id, int):
            await self.telegram.delete_message(chat_id, message_id)
        await self._send_movie_details(
            chat_id,
            movie,
            movie_details_keyboard(imdb_id, collection, offset),
        )

    async def _handle_media_remove(
        self,
        callback_id: str,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
        data: str,
    ) -> None:
        parts = data.split(":")
        if len(parts) != 5:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        _, media_type, external_id, collection, raw_offset = parts
        try:
            offset = int(raw_offset)
        except ValueError:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        if (
            media_type not in {"movie", "anime"}
            or collection not in {"watched", "favorite", "watchlist", "skipped"}
            or offset < 0
            or not external_id
        ):
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return

        try:
            self.database.clear_collection_flag(telegram_id, media_type, external_id, collection)
        except ValueError:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        label = COLLECTION_LABELS.get(collection, collection)
        await self.telegram.answer_callback_query(callback_id, f"🗑 Убрал из «{label}»")
        await self._handle_collection_page(
            chat_id,
            telegram_id,
            message_id,
            f"col:{media_type}:{collection}:{offset}",
        )

    async def _start_search(self, chat_id: int, telegram_id: int, text: str) -> None:
        self._pending_search.pop(telegram_id, None)
        self._awaiting_search.pop(telegram_id, None)
        parts = text.split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""
        if query:
            self._pending_search[telegram_id] = query[:80]
        await self.telegram.send_message(
            chat_id,
            search_media_text(),
            reply_markup=search_media_keyboard(),
        )

    async def _handle_search_choice(
        self,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
        media_type: str,
    ) -> None:
        if media_type not in {"movie", "anime"}:
            return
        query = self._pending_search.pop(telegram_id, None)
        if query:
            await self._run_search(chat_id, telegram_id, media_type, query, message_id)
            return
        self._awaiting_search[telegram_id] = media_type
        await self._replace_with_message(
            chat_id,
            message_id,
            search_prompt_text(media_type),
            search_cancel_keyboard(),
        )

    async def _run_search(
        self,
        chat_id: int,
        telegram_id: int,
        media_type: str,
        query: str,
        old_message_id: int | None = None,
    ) -> None:
        self._awaiting_search.pop(telegram_id, None)
        self._pending_search.pop(telegram_id, None)
        query = query.strip()[:80]
        if not query:
            await self._replace_with_message(
                chat_id,
                old_message_id,
                search_prompt_text(media_type),
                search_cancel_keyboard(),
            )
            return

        await self.telegram.send_chat_action(chat_id, "typing")
        items: list[Any] | None
        if media_type == "movie":
            try:
                items = await self.recommendations.search(query)
            except CinemetaError:
                items = None
        else:
            try:
                items = await self.anime_recommendations.search(query)
            except ShikimoriError:
                items = None

        if items is None:
            await self._replace_with_message(
                chat_id,
                old_message_id,
                "😿 Поиск не удался. Попробуй ещё раз позже.",
                search_media_keyboard(),
            )
            return
        if not items:
            await self._replace_with_message(
                chat_id,
                old_message_id,
                search_no_results_text(media_type, query),
                search_media_keyboard(),
            )
            return

        if media_type == "movie":
            text = movie_search_results_text(query, items)
            external_ids = [item.imdb_id for item in items]
        else:
            text = anime_search_results_text(query, items)
            external_ids = [str(item.shikimori_id) for item in items]
        await self._replace_with_message(
            chat_id,
            old_message_id,
            text,
            search_results_keyboard(media_type, external_ids),
        )

    async def _handle_search_movie_view(
        self,
        callback_id: str,
        chat_id: int,
        data: str,
    ) -> None:
        imdb_id = data.partition(":")[2]
        try:
            movie = await self.recommendations.get_movie(imdb_id)
        except (CinemetaError, ValueError):
            await self.telegram.answer_callback_query(
                callback_id,
                "Не смог загрузить фильм. Попробуй ещё раз.",
                show_alert=True,
            )
            return
        await self.telegram.answer_callback_query(callback_id)
        await self._send_movie_details(chat_id, movie, search_movie_keyboard(movie))

    async def _handle_search_anime_view(
        self,
        callback_id: str,
        chat_id: int,
        data: str,
    ) -> None:
        raw_id = data.partition(":")[2]
        try:
            anime_id = int(raw_id)
        except ValueError:
            await self.telegram.answer_callback_query(callback_id, "Некорректная кнопка.")
            return
        try:
            anime = await self.anime_recommendations.get_anime(anime_id)
        except (ShikimoriError, ValueError):
            await self.telegram.answer_callback_query(
                callback_id,
                "Не смог загрузить аниме. Попробуй ещё раз.",
                show_alert=True,
            )
            return
        await self.telegram.answer_callback_query(callback_id)
        await self._send_anime_details(chat_id, anime, search_anime_keyboard(anime))

    async def _send_anime_details(
        self,
        chat_id: int,
        anime: Anime,
        markup: dict[str, Any],
    ) -> None:
        caption = anime_caption(anime)
        if anime.poster_url:
            try:
                await self.telegram.send_photo(
                    chat_id,
                    anime.poster_url,
                    caption,
                    reply_markup=markup,
                )
                return
            except TelegramAPIError:
                logger.warning(
                    "Telegram could not send anime poster for %s; falling back to text",
                    anime.shikimori_id,
                )
        await self.telegram.send_message(chat_id, caption, reply_markup=markup)

    async def _send_anime(self, chat_id: int, anime: Anime, genre_key: str) -> None:
        await self._send_anime_details(chat_id, anime, anime_keyboard(anime, genre_key))

    async def _send_collection(self, chat_id: int, telegram_id: int) -> None:
        movie_stats = self.database.collection_stats(telegram_id, "movie")
        anime_stats = self.database.collection_stats(telegram_id, "anime")
        await self.telegram.send_message(
            chat_id,
            collection_summary_text(movie_stats, anime_stats),
            reply_markup=collection_keyboard(),
        )

    async def _send_stats(self, chat_id: int, telegram_id: int) -> None:
        if telegram_id not in self.admin_ids:
            return
        await self.telegram.send_message(chat_id, global_stats_text(self.database.global_stats()))

    async def _replace_with_collection(
        self,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
    ) -> None:
        movie_stats = self.database.collection_stats(telegram_id, "movie")
        anime_stats = self.database.collection_stats(telegram_id, "anime")
        await self._replace_with_message(
            chat_id,
            message_id,
            collection_summary_text(movie_stats, anime_stats),
            collection_keyboard(),
        )

    async def _replace_with_media_collection(
        self,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
        media_type: str,
    ) -> None:
        stats = self.database.collection_stats(telegram_id, media_type)
        await self._replace_with_message(
            chat_id,
            message_id,
            media_collection_text(media_type, stats),
            media_collection_keyboard(media_type),
        )

    async def _handle_collection_page(
        self,
        chat_id: int,
        telegram_id: int,
        message_id: int | None,
        data: str,
    ) -> None:
        parts = data.split(":")
        if len(parts) == 3:  # Old v1.1 callback: movie collection.
            _, collection, raw_offset = parts
            media_type = "movie"
        elif len(parts) == 4:
            _, media_type, collection, raw_offset = parts
        else:
            return
        try:
            offset = max(0, int(raw_offset))
            media, total = self.database.list_collection(
                telegram_id,
                collection,
                media_type=media_type,
                limit=PAGE_SIZE,
                offset=offset,
            )
        except ValueError:
            return

        text = collection_page_text(
            media_type,
            collection,
            media,
            total=total,
            offset=offset,
        )
        markup = collection_page_keyboard(
            media_type,
            collection,
            offset,
            total,
            PAGE_SIZE,
            media,
        )
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
