from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote

import httpx

from kinotyk.domain import Movie, MovieCandidate

logger = logging.getLogger(__name__)
_IMDB_ID_RE = re.compile(r"^tt\d+$")
_YEAR_RE = re.compile(r"(18|19|20|21)\d{2}")


class CinemetaError(RuntimeError):
    pass


class CinemetaClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _get_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self.client.get(url, timeout=self.timeout_seconds)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise CinemetaError("Cinemeta returned a non-object JSON response")
                return data
            except (httpx.HTTPError, ValueError, CinemetaError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        raise CinemetaError("Cinemeta request failed") from last_error

    async def catalog(self, genre: str | None, *, skip: int = 0) -> list[MovieCandidate]:
        if skip < 0:
            raise ValueError("skip must be >= 0")

        extras: list[str] = []
        if genre:
            extras.append(f"genre={quote(genre, safe='')}")
        if skip:
            extras.append(f"skip={skip}")

        suffix = f"/{'&'.join(extras)}" if extras else ""
        return await self._fetch_metas(f"{self.base_url}/catalog/movie/top{suffix}.json")

    async def search(self, query: str) -> list[MovieCandidate]:
        cleaned = query.strip()
        if not cleaned:
            return []
        url = f"{self.base_url}/catalog/movie/top/search={quote(cleaned, safe='')}.json"
        return await self._fetch_metas(url)

    async def _fetch_metas(self, url: str) -> list[MovieCandidate]:
        data = await self._get_json(url)
        raw_metas = data.get("metas", [])
        if not isinstance(raw_metas, list):
            raise CinemetaError("Cinemeta catalog has invalid 'metas' field")

        candidates: list[MovieCandidate] = []
        for raw in raw_metas:
            if not isinstance(raw, dict):
                continue
            imdb_id = str(raw.get("id") or "")
            title = str(raw.get("name") or "").strip()
            if not _IMDB_ID_RE.fullmatch(imdb_id) or not title:
                continue
            candidates.append(
                MovieCandidate(
                    imdb_id=imdb_id,
                    title=title,
                    rating=_parse_rating(raw.get("imdbRating")),
                    year=_parse_year(raw.get("releaseInfo") or raw.get("released")),
                )
            )
        return candidates

    async def get_movie(self, imdb_id: str) -> Movie:
        if not _IMDB_ID_RE.fullmatch(imdb_id):
            raise ValueError(f"Invalid IMDb id: {imdb_id!r}")

        url = f"{self.base_url}/meta/movie/{imdb_id}.json"
        data = await self._get_json(url)
        raw = data.get("meta")
        if not isinstance(raw, dict):
            raise CinemetaError("Cinemeta metadata response does not contain 'meta'")

        title = str(raw.get("name") or "").strip()
        if not title:
            raise CinemetaError("Movie title is missing")

        genres_raw = raw.get("genres") or []
        genres = tuple(str(item).strip() for item in genres_raw if str(item).strip())
        poster = str(raw.get("poster") or "").strip() or None
        description = str(raw.get("description") or "").strip()

        return Movie(
            imdb_id=imdb_id,
            title=title,
            original_title=title,
            overview=description,
            poster_url=poster,
            rating=_parse_rating(raw.get("imdbRating")),
            year=_parse_year(raw.get("releaseInfo") or raw.get("released")),
            genres=genres,
            director=_parse_names(raw.get("director")),
        )


def _parse_rating(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= rating <= 10:
        return rating
    return None


def _parse_year(value: object) -> int | None:
    if value is None:
        return None
    match = _YEAR_RE.search(str(value))
    return int(match.group(0)) if match else None


def _parse_names(value: object, *, limit: int = 2) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if not isinstance(value, list):
        return None
    names = [str(item).strip() for item in value if str(item).strip()]
    return ", ".join(names[:limit]) or None
