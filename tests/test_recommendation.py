import asyncio
import random
from pathlib import Path

from kinotyk.db import Database
from kinotyk.domain import Movie, MovieCandidate
from kinotyk.services.recommendation import RecommendationService


class FakeCinemeta:
    async def catalog(self, genre: str | None, *, skip: int = 0) -> list[MovieCandidate]:
        del genre, skip
        return [
            MovieCandidate("tt0000001", "Low", 4.0, 2000),
            MovieCandidate("tt0000002", "Seen", 8.0, 2001),
            MovieCandidate("tt0000003", "Good", 8.5, 2002),
        ]

    async def get_movie(self, imdb_id: str) -> Movie:
        ratings = {"tt0000001": 4.0, "tt0000002": 8.0, "tt0000003": 8.5}
        return Movie(
            imdb_id=imdb_id,
            title=imdb_id,
            original_title=imdb_id,
            overview="overview",
            poster_url=None,
            rating=ratings[imdb_id],
            year=2002,
            genres=("Drama",),
        )


class FakeLocalizer:
    async def localize(self, movie: Movie) -> Movie:
        return movie.localized(title=f"RU {movie.title}")


def test_recommendation_filters_watched_and_low_rating(tmp_path: Path) -> None:
    async def scenario() -> None:
        db = Database(tmp_path / "db.sqlite3")
        db.init()
        db.upsert_user(1, None, "User", "ru")
        seen = Movie(
            imdb_id="tt0000002",
            title="Seen",
            original_title="Seen",
            overview="",
            poster_url=None,
            rating=8.0,
            year=2001,
            genres=("Drama",),
        )
        db.mark_watched(1, seen)

        service = RecommendationService(
            database=db,
            cinemeta=FakeCinemeta(),  # type: ignore[arg-type]
            localizer=FakeLocalizer(),  # type: ignore[arg-type]
            min_imdb_rating=6.0,
            skips=(0,),
            rng=random.Random(0),
        )
        movie = await service.recommend(1, "drama")
        assert movie is not None
        assert movie.imdb_id == "tt0000003"
        assert movie.title == "RU tt0000003"

    asyncio.run(scenario())
