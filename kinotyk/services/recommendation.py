from __future__ import annotations

import logging
import random
from collections import defaultdict

from kinotyk.clients.cinemeta import CinemetaClient, CinemetaError
from kinotyk.clients.localization import RussianLocalizer
from kinotyk.db import Database
from kinotyk.domain import Movie, MovieCandidate
from kinotyk.genres import GENRE_BY_KEY

logger = logging.getLogger(__name__)


class RecommendationService:
    def __init__(
        self,
        *,
        database: Database,
        cinemeta: CinemetaClient,
        localizer: RussianLocalizer,
        min_imdb_rating: float,
        skips: tuple[int, ...],
        rng: random.Random | None = None,
    ) -> None:
        self.database = database
        self.cinemeta = cinemeta
        self.localizer = localizer
        self.min_imdb_rating = min_imdb_rating
        self.skips = skips
        self.rng = rng or random.Random()
        self._session_seen: dict[int, set[str]] = defaultdict(set)
        self._movie_cache: dict[str, Movie] = {}

    async def recommend(self, telegram_id: int, genre_key: str) -> Movie | None:
        genre = GENRE_BY_KEY.get(genre_key)
        if genre is None:
            raise ValueError(f"Unknown genre key: {genre_key}")

        movie = await self._find_movie(telegram_id, genre.cinemeta_name)
        if movie is None and self._session_seen[telegram_id]:
            # User may have exhausted only the in-memory session. Reset it once;
            # persistent watched/skipped/watchlist items remain excluded.
            self._session_seen[telegram_id].clear()
            movie = await self._find_movie(telegram_id, genre.cinemeta_name)
        return movie

    async def get_movie(self, imdb_id: str) -> Movie:
        cached = self._movie_cache.get(imdb_id)
        if cached is not None:
            return cached
        movie = await self.cinemeta.get_movie(imdb_id)
        localized = await self.localizer.localize(movie)
        self._movie_cache[imdb_id] = localized
        return localized

    async def search(self, query: str) -> list[MovieCandidate]:
        cleaned = query.strip()
        if not cleaned:
            return []
        return await self.cinemeta.search(cleaned)

    async def _find_movie(self, telegram_id: int, genre: str | None) -> Movie | None:
        excluded = self.database.excluded_movie_ids(telegram_id) | self._session_seen[telegram_id]
        skips = list(self.skips)
        self.rng.shuffle(skips)

        for skip in skips:
            try:
                candidates = await self.cinemeta.catalog(genre, skip=skip)
            except CinemetaError:
                logger.exception("Cinemeta catalog failed for genre=%s skip=%s", genre, skip)
                continue

            candidates = [
                candidate for candidate in candidates if candidate.imdb_id not in excluded
            ]
            self.rng.shuffle(candidates)

            for candidate in candidates[:30]:
                if candidate.rating is not None and candidate.rating < self.min_imdb_rating:
                    continue
                try:
                    movie = await self.cinemeta.get_movie(candidate.imdb_id)
                except CinemetaError:
                    logger.warning("Could not load metadata for %s", candidate.imdb_id)
                    continue
                if movie.rating is None or movie.rating < self.min_imdb_rating:
                    continue

                localized = await self.localizer.localize(movie)
                self._session_seen[telegram_id].add(localized.imdb_id)
                self._movie_cache[localized.imdb_id] = localized
                return localized

        return None
