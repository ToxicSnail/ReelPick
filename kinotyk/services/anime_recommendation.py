from __future__ import annotations

import logging
import random
from collections import defaultdict

from kinotyk.clients.shikimori import ShikimoriClient, ShikimoriError
from kinotyk.db import Database
from kinotyk.domain import Anime, AnimeCandidate

logger = logging.getLogger(__name__)


class AnimeRecommendationService:
    def __init__(
        self,
        *,
        database: Database,
        shikimori: ShikimoriClient,
        min_rating: float,
        pages: tuple[int, ...],
        rng: random.Random | None = None,
    ) -> None:
        self.database = database
        self.shikimori = shikimori
        self.min_rating = min_rating
        self.pages = pages
        self.rng = rng or random.SystemRandom()
        self._session_seen: dict[int, set[str]] = defaultdict(set)
        self._cache: dict[int, Anime] = {}

    async def get_anime(self, anime_id: int) -> Anime:
        cached = self._cache.get(anime_id)
        if cached is not None:
            return cached
        anime = await self.shikimori.get_anime(anime_id)
        self._cache[anime_id] = anime
        return anime

    async def search(self, query: str) -> list[AnimeCandidate]:
        cleaned = query.strip()
        if not cleaned:
            return []
        return await self.shikimori.search(cleaned)

    async def recommend(self, telegram_id: int, genre_key: str) -> Anime | None:
        excluded = self.database.excluded_media_ids(telegram_id, "anime")
        excluded |= self._session_seen[telegram_id]
        pages = list(self.pages)
        self.rng.shuffle(pages)

        for page in pages:
            try:
                candidates = await self.shikimori.catalog(genre_key, page=page)
            except ShikimoriError:
                logger.exception("Shikimori catalog failed for genre=%s page=%s", genre_key, page)
                continue

            candidates = [
                item for item in candidates if str(item.shikimori_id) not in excluded
            ]
            self.rng.shuffle(candidates)

            for candidate in candidates[:30]:
                if candidate.score is not None and candidate.score < self.min_rating:
                    continue
                try:
                    anime = await self.shikimori.get_anime(candidate.shikimori_id)
                except ShikimoriError:
                    logger.warning("Could not load anime metadata for %s", candidate.shikimori_id)
                    continue
                if anime.score is not None and anime.score < self.min_rating:
                    continue
                self._session_seen[telegram_id].add(str(anime.shikimori_id))
                self._cache[anime.shikimori_id] = anime
                return anime
        return None
