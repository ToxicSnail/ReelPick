import asyncio
import random
from pathlib import Path

from kinotyk.db import Database
from kinotyk.domain import Anime, AnimeCandidate
from kinotyk.services.anime_recommendation import AnimeRecommendationService


class FakeShikimori:
    async def catalog(self, genre_key: str, *, page: int = 1) -> list[AnimeCandidate]:
        del genre_key, page
        return [
            AnimeCandidate(1, "Low", 4.0, 2000),
            AnimeCandidate(2, "Seen", 8.0, 2001),
            AnimeCandidate(3, "Good", 8.5, 2002),
        ]

    async def get_anime(self, anime_id: int) -> Anime:
        ratings = {1: 4.0, 2: 8.0, 3: 8.5}
        return Anime(
            shikimori_id=anime_id,
            title=f"Anime {anime_id}",
            original_title=f"Anime {anime_id}",
            overview="Описание",
            poster_url=None,
            score=ratings[anime_id],
            year=2002,
            genres=("Драма",),
            kind="tv",
            episodes=12,
            duration=24,
        )


def test_anime_recommendation_filters_watched_and_low_rating(tmp_path: Path) -> None:
    async def scenario() -> None:
        db = Database(tmp_path / "db.sqlite3")
        db.init()
        db.upsert_user(1, None, "User", "ru")
        seen = await FakeShikimori().get_anime(2)
        db.mark_anime_watched(1, seen)

        service = AnimeRecommendationService(
            database=db,
            shikimori=FakeShikimori(),  # type: ignore[arg-type]
            min_rating=6.0,
            pages=(1,),
            rng=random.Random(0),
        )
        anime = await service.recommend(1, "drama")
        assert anime is not None
        assert anime.shikimori_id == 3

    asyncio.run(scenario())
