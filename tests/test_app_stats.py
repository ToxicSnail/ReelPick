import asyncio
from pathlib import Path

from test_app_search import FakeMovieService, FakeShikimori, FakeTelegram, _message

from kinotyk.app import KinotykApp
from kinotyk.db import Database
from kinotyk.services.anime_recommendation import AnimeRecommendationService


def _build_app(
    tmp_path: Path,
    *,
    admin_ids: tuple[int, ...],
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
    return app, database, telegram


def test_stats_command_for_admin(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, database, telegram = _build_app(tmp_path, admin_ids=(77,))
        database.upsert_user(77, None, "Test", None)
        database.upsert_user(88, None, "Other", "ru")
        anime = await app.anime_recommendations.get_anime(2167)
        database.mark_anime_watched(88, anime)
        database.toggle_anime_favorite(88, anime)

        await app.handle_update(_message(77, "/stats"))

        assert len(telegram.messages) == 1
        text = telegram.messages[0]["text"]
        assert "Статистика Кинотыка" in text
        assert "👥 Пользователей: <b>2</b>" in text
        assert "🎬 Фильмов сохранено: <b>0</b>" in text
        assert "🍥 Аниме сохранено: <b>1</b>" in text
        assert "✅ Просмотрено: <b>1</b>" in text
        assert "❤️ Избранное: <b>1</b>" in text

    asyncio.run(scenario())


def test_stats_command_hidden_for_regular_users(tmp_path: Path) -> None:
    async def scenario() -> None:
        app, database, telegram = _build_app(tmp_path, admin_ids=(123456789,))
        database.upsert_user(77, None, "Test", None)

        await app.handle_update(_message(77, "/stats"))

        assert telegram.messages == []

    asyncio.run(scenario())
