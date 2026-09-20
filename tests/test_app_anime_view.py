import asyncio
from pathlib import Path
from typing import Any

from kinotyk.app import KinotykApp
from kinotyk.clients.shikimori import ShikimoriError
from kinotyk.db import Database
from kinotyk.domain import Anime
from kinotyk.services.anime_recommendation import AnimeRecommendationService


class FakeShikimori:
    async def get_anime(self, anime_id: int) -> Anime:
        return Anime(
            shikimori_id=anime_id,
            title="Пираты «Чёрной лагуны»",
            original_title="Black Lagoon",
            overview="История о команде наёмников.",
            poster_url="https://shikimori.one/system/animes/original/889.jpg",
            score=8.28,
            year=2006,
            genres=("Экшен", "Сэйнэн"),
            kind="tv",
            episodes=12,
            duration=23,
            studio="Madhouse",
            director="Сунао Катабути",
        )


class BrokenShikimori:
    async def get_anime(self, anime_id: int) -> Anime:
        raise ShikimoriError("boom")


class FakeTelegram:
    def __init__(self) -> None:
        self.answers: list[tuple[str | None, bool]] = []
        self.messages: list[dict[str, Any]] = []
        self.photos: list[dict[str, Any]] = []
        self.deleted: list[tuple[int, int]] = []

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        *,
        show_alert: bool = False,
    ) -> None:
        self.answers.append((text, show_alert))

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )
        return {}

    async def send_photo(
        self,
        chat_id: int,
        photo_url: str,
        caption: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.photos.append(
            {
                "chat_id": chat_id,
                "photo_url": photo_url,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )
        return {}


def _build_app(
    database: Database,
    shikimori: FakeShikimori | BrokenShikimori,
    telegram: FakeTelegram,
) -> KinotykApp:
    anime_service = AnimeRecommendationService(
        database=database,  # type: ignore[arg-type]
        shikimori=shikimori,  # type: ignore[arg-type]
        min_rating=6.0,
        pages=(1,),
    )
    return KinotykApp(
        telegram=telegram,  # type: ignore[arg-type]
        database=database,
        recommendations=None,  # type: ignore[arg-type]
        anime_recommendations=anime_service,  # type: ignore[arg-type]
    )


def _callback(telegram_id: int, message_id: int, data: str) -> dict[str, Any]:
    return {
        "id": "cb-1",
        "from": {"id": telegram_id},
        "message": {"chat": {"id": telegram_id}, "message_id": message_id},
        "data": data,
    }


def test_watchlist_anime_opens_description_and_returns_to_list(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "db.sqlite")
        database.init()
        telegram = FakeTelegram()
        app = _build_app(database, FakeShikimori(), telegram)
        database.upsert_user(77, None, "Test", None)
        anime = await app.anime_recommendations.get_anime(889)
        database.toggle_anime_watchlist(77, anime)

        await app.handle_update(
            {"callback_query": _callback(77, 42, "anv:889:watchlist:0")}
        )

        assert telegram.deleted == [(77, 42)]
        assert telegram.messages == []
        assert len(telegram.photos) == 1
        photo = telegram.photos[0]
        assert photo["photo_url"] == "https://shikimori.one/system/animes/original/889.jpg"
        assert "История о команде наёмников." in photo["caption"]
        assert "Пираты «Чёрной лагуны»" in photo["caption"]
        assert "🏢 Студия: <b>Madhouse</b>" in photo["caption"]
        assert "🎥 Режиссёр: <b>Сунао Катабути</b>" in photo["caption"]
        back_row = photo["reply_markup"]["inline_keyboard"][0]
        assert back_row[0]["callback_data"] == "col:anime:watchlist:0"
        assert telegram.answers == [(None, False)]

        await app.handle_update(
            {"callback_query": _callback(77, 43, "col:anime:watchlist:0")}
        )
        assert len(telegram.messages) == 1

    asyncio.run(scenario())


def test_favorite_anime_description_without_poster_falls_back_to_text(
    tmp_path: Path,
) -> None:
    class NoPosterShikimori(FakeShikimori):
        async def get_anime(self, anime_id: int) -> Anime:
            anime = await super().get_anime(anime_id)
            return Anime(
                shikimori_id=anime.shikimori_id,
                title=anime.title,
                original_title=anime.original_title,
                overview=anime.overview,
                poster_url=None,
                score=anime.score,
                year=anime.year,
                genres=anime.genres,
                kind=anime.kind,
                episodes=anime.episodes,
                duration=anime.duration,
                status=anime.status,
            )

    async def scenario() -> None:
        database = Database(tmp_path / "db.sqlite")
        database.init()
        telegram = FakeTelegram()
        app = _build_app(database, NoPosterShikimori(), telegram)
        database.upsert_user(77, None, "Test", None)
        anime = await app.anime_recommendations.get_anime(889)
        database.toggle_anime_favorite(77, anime)

        await app.handle_update(
            {"callback_query": _callback(77, 42, "anv:889:favorite:0")}
        )

        assert telegram.photos == []
        assert len(telegram.messages) == 1
        assert "История о команде наёмников." in telegram.messages[0]["text"]
        assert telegram.messages[0]["reply_markup"]["inline_keyboard"][0][0][
            "callback_data"
        ] == "col:anime:favorite:0"

    asyncio.run(scenario())


def test_anime_view_with_broken_shikimori_shows_alert(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "db.sqlite")
        database.init()
        telegram = FakeTelegram()
        app = _build_app(database, BrokenShikimori(), telegram)
        database.upsert_user(77, None, "Test", None)

        await app.handle_update(
            {"callback_query": _callback(77, 42, "anv:889:watchlist:0")}
        )

        assert telegram.photos == []
        assert telegram.messages == []
        assert telegram.deleted == []
        assert telegram.answers == [("Не смог загрузить аниме. Попробуй ещё раз.", True)]

    asyncio.run(scenario())


def test_anime_view_rejects_malformed_callbacks(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "db.sqlite")
        database.init()
        telegram = FakeTelegram()
        app = _build_app(database, FakeShikimori(), telegram)
        database.upsert_user(77, None, "Test", None)

        for data in (
            "anv:889",
            "anv:notanumber:watchlist:0",
            "anv:889:hack:0",
            "anv:-5:watchlist:0",
            "anv:889:watchlist:-3",
        ):
            await app.handle_update({"callback_query": _callback(77, 42, data)})

        assert telegram.photos == []
        assert telegram.messages == []
        assert telegram.deleted == []
        assert len(telegram.answers) == 5
        assert all(text == "Некорректная кнопка." for text, _ in telegram.answers)

    asyncio.run(scenario())
