import asyncio
from pathlib import Path
from typing import Any

from kinotyk.app import KinotykApp
from kinotyk.db import Database
from kinotyk.domain import Anime, AnimeCandidate, Movie, MovieCandidate
from kinotyk.services.anime_recommendation import AnimeRecommendationService

ANIME = Anime(
    shikimori_id=2167,
    title="Кланнад",
    original_title="Clannad",
    overview="История о семье.",
    poster_url="https://shikimori.one/system/animes/original/2167.jpg",
    score=8.2,
    year=2007,
    genres=("Драма", "Романтика"),
    kind="tv",
    episodes=23,
    duration=24,
    studio="Kyoto Animation",
    director="Тэцуя Ватанабэ",
)

MOVIE = Movie(
    imdb_id="tt0133093",
    title="Матрица",
    original_title="The Matrix",
    overview="Реальность — иллюзия.",
    poster_url=None,
    rating=8.7,
    year=1999,
    genres=("Action", "Sci-Fi"),
    director="The Wachowskis",
)


class FakeShikimori:
    async def get_anime(self, anime_id: int) -> Anime:
        if anime_id != ANIME.shikimori_id:
            raise ValueError(f"unexpected id: {anime_id}")
        return ANIME

    async def search(self, query: str) -> list[AnimeCandidate]:
        if "клан" not in query.casefold():
            return []
        return [
            AnimeCandidate(
                shikimori_id=ANIME.shikimori_id,
                title=ANIME.title,
                score=ANIME.score,
                year=ANIME.year,
            )
        ]


class FakeMovieService:
    async def get_movie(self, imdb_id: str) -> Movie:
        if imdb_id != MOVIE.imdb_id:
            raise ValueError(f"unexpected id: {imdb_id}")
        return MOVIE

    async def search(self, query: str) -> list[MovieCandidate]:
        if "матриц" not in query.casefold():
            return []
        return [
            MovieCandidate(
                imdb_id=MOVIE.imdb_id,
                title=MOVIE.title,
                rating=MOVIE.rating,
                year=MOVIE.year,
            )
        ]


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

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self.messages.append({"chat_id": chat_id, "chat_action": action})


def _build_app(
    tmp_path: Path,
    *,
    admin_ids: tuple[int, ...] = (),
) -> tuple[KinotykApp, Database, FakeTelegram]:
    database = Database(tmp_path / "db.sqlite")
    database.init()
    telegram = FakeTelegram()
    anime_service = AnimeRecommendationService(
        database=database,  # type: ignore[arg-type]
        shikimori=FakeShikimori(),  # type: ignore[arg-type]
        min_rating=6.0,
        pages=(1,),
    )
    app = KinotykApp(
        telegram=telegram,  # type: ignore[arg-type]
        database=database,
        recommendations=FakeMovieService(),  # type: ignore[arg-type]
        anime_recommendations=anime_service,  # type: ignore[arg-type]
        admin_ids=admin_ids,
    )
    database.upsert_user(77, None, "Test", None)
    return app, database, telegram


def _callback(telegram_id: int, message_id: int, data: str) -> dict[str, Any]:
    return {
        "callback_query": {
            "id": "cb-1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}, "message_id": message_id},
            "data": data,
        }
    }


def _message(telegram_id: int, text: str) -> dict[str, Any]:
    return {"message": {"from": {"id": telegram_id}, "chat": {"id": telegram_id}, "text": text}}


def test_anime_search_flow_with_inline_query(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, _, telegram = _build_app(tmp_path)

        await app.handle_update(_message(77, "/search кланнад"))
        assert "Что будем искать" in telegram.messages[-1]["text"]

        await app.handle_update(_callback(77, 10, "search:anime"))
        results = telegram.messages[-1]
        assert "Поиск аниме" in results["text"]
        assert "Кланнад</b> (2007)" in results["text"]
        flat = [b for row in results["reply_markup"]["inline_keyboard"] for b in row]
        assert flat[0]["callback_data"] == "sav:2167"

        await app.handle_update(_callback(77, 11, "sav:2167"))
        card = telegram.photos[-1]
        assert "История о семье." in card["caption"]
        assert "🏢 Студия: <b>Kyoto Animation</b>" in card["caption"]
        callbacks = [
            b["callback_data"] for row in card["reply_markup"]["inline_keyboard"] for b in row
        ]
        assert "an:w:2167:search" in callbacks
        assert all(not value.startswith("an:n:") for value in callbacks)

    asyncio.run(scenario())


def test_search_flow_asks_text_then_runs_search(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, _, telegram = _build_app(tmp_path)

        await app.handle_update(_callback(77, 10, "menu:search"))
        assert "Что будем искать" in telegram.messages[-1]["text"]

        await app.handle_update(_callback(77, 10, "search:movie"))
        prompt = telegram.messages[-1]
        assert "Напиши название" in prompt["text"]
        assert prompt["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "search:cancel"

        await app.handle_update(_message(77, "Матрица"))
        results = telegram.messages[-1]
        assert "Поиск фильмов" in results["text"]
        flat = [b for row in results["reply_markup"]["inline_keyboard"] for b in row]
        assert flat[0]["callback_data"] == "smv:tt0133093"

        await app.handle_update(_callback(77, 11, "smv:tt0133093"))
        card = telegram.messages[-1]
        assert "Реальность — иллюзия." in card["text"]
        assert "🎥 Режиссёр: <b>The Wachowskis</b>" in card["text"]
        callbacks = [
            b["callback_data"] for row in card["reply_markup"]["inline_keyboard"] for b in row
        ]
        assert "mv:f:tt0133093:search" in callbacks

    asyncio.run(scenario())


def test_search_cancel_and_no_results(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, _, telegram = _build_app(tmp_path)

        await app.handle_update(_callback(77, 10, "search:anime"))
        assert "Напиши название" in telegram.messages[-1]["text"]

        await app.handle_update(_message(77, "йцукенгшщзхъ"))
        results = telegram.messages[-1]
        assert "ничего не нашлось" in results["text"]

        await app.handle_update(_callback(77, 11, "search:cancel"))
        assert telegram.messages[-1]["reply_markup"] is not None

    asyncio.run(scenario())


def test_remove_anime_from_watchlist_via_details(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, database, telegram = _build_app(tmp_path)
        anime = await app.anime_recommendations.get_anime(2167)
        database.toggle_anime_watchlist(77, anime)

        await app.handle_update(_callback(77, 20, "anv:2167:watchlist:0"))
        details = telegram.photos[-1]
        rows = details["reply_markup"]["inline_keyboard"]
        assert rows[1][0]["callback_data"] == "rmv:anime:2167:watchlist:0"

        await app.handle_update(_callback(77, 20, "rmv:anime:2167:watchlist:0"))

        assert telegram.answers[-1] == ("🗑 Убрал из «📌 Посмотреть позже»", False)
        items, total = database.list_collection(77, "watchlist", media_type="anime")
        assert total == 0
        assert items == []
        page = telegram.messages[-1]
        assert "Здесь пока пусто." in page["text"]

    asyncio.run(scenario())


def test_remove_movie_from_favorites_keeps_watched(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, database, telegram = _build_app(tmp_path)
        movie = await app.recommendations.get_movie("tt0133093")
        database.toggle_favorite(77, movie)
        database.mark_watched(77, movie)

        await app.handle_update(_callback(77, 20, "mvv:tt0133093:favorite:0"))
        details = telegram.messages[-1]
        rows = details["reply_markup"]["inline_keyboard"]
        assert rows[1][0]["callback_data"] == "rmv:movie:tt0133093:favorite:0"
        assert "Реальность — иллюзия." in details["text"]

        await app.handle_update(_callback(77, 20, "rmv:movie:tt0133093:favorite:0"))

        stats = database.collection_stats(77, "movie")
        assert stats["favorite"] == 0
        assert stats["watched"] == 1

        await app.handle_update(_callback(77, 21, "rmv:movie:tt0133093:watched:0"))
        assert database.collection_stats(77, "movie")["watched"] == 0
        assert "2167" not in database.excluded_media_ids(77, "anime")

    asyncio.run(scenario())
