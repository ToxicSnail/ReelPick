from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urljoin

import httpx

from kinotyk.anime_genres import ANIME_GENRE_BY_KEY
from kinotyk.domain import Anime, AnimeCandidate

logger = logging.getLogger(__name__)


class ShikimoriError(RuntimeError):
    pass


class ShikimoriClient:
    """Read-only Shikimori client for public anime metadata.

    No OAuth is used: the bot only reads public catalog/detail endpoints.
    The parser is deliberately defensive because optional fields may be absent.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        timeout_seconds: float,
        user_agent: str,
        max_overview_chars: int = 520,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self.max_overview_chars = max_overview_chars
        self._genre_ids: dict[str, int] | None = None

    async def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self.client.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.3)
        raise ShikimoriError(f"Shikimori request failed: {path}") from last_error

    async def genre_ids(self) -> dict[str, int]:
        if self._genre_ids is not None:
            return self._genre_ids

        data = await self._get_json("/api/genres")
        if not isinstance(data, list):
            raise ShikimoriError("Shikimori genres response must be a list")

        result: dict[str, int] = {}
        for raw in data:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            genre_id = raw.get("id")
            if not name or not isinstance(genre_id, int):
                continue
            result[name.casefold()] = genre_id
        self._genre_ids = result
        return result

    async def catalog(self, genre_key: str, *, page: int = 1) -> list[AnimeCandidate]:
        if page < 1:
            raise ValueError("page must be >= 1")
        genre = ANIME_GENRE_BY_KEY.get(genre_key)
        if genre is None:
            raise ValueError(f"Unknown anime genre: {genre_key}")

        params = {
            "page": str(page),
            "limit": "50",
            "order": "popularity",
            "status": "released",
        }
        if genre.shikimori_name:
            ids = await self.genre_ids()
            genre_id = ids.get(genre.shikimori_name.casefold())
            if genre_id is None:
                raise ShikimoriError(f"Genre not found on Shikimori: {genre.shikimori_name}")
            params["genre"] = str(genre_id)

        data = await self._get_json("/api/animes", params=params)
        if not isinstance(data, list):
            raise ShikimoriError("Shikimori anime catalog response must be a list")

        result: list[AnimeCandidate] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            anime_id = raw.get("id")
            if not isinstance(anime_id, int):
                continue
            title = str(raw.get("russian") or raw.get("name") or "").strip()
            if not title:
                continue
            result.append(
                AnimeCandidate(
                    shikimori_id=anime_id,
                    title=title,
                    score=_parse_score(raw.get("score")),
                    year=_parse_year(raw.get("aired_on") or raw.get("released_on")),
                )
            )
        return result

    async def get_anime(self, anime_id: int) -> Anime:
        if anime_id <= 0:
            raise ValueError("anime_id must be positive")
        data = await self._get_json(f"/api/animes/{anime_id}")
        if not isinstance(data, dict):
            raise ShikimoriError("Shikimori anime detail response must be an object")

        original_title = str(data.get("name") or "").strip()
        title = str(data.get("russian") or original_title).strip()
        if not title:
            raise ShikimoriError("Anime title is missing")

        genres: list[str] = []
        raw_genres = data.get("genres") or []
        if isinstance(raw_genres, list):
            for raw in raw_genres:
                if not isinstance(raw, dict):
                    continue
                value = str(raw.get("russian") or raw.get("name") or "").strip()
                if value:
                    genres.append(value)

        overview = _clean_description(
            str(data.get("description") or ""),
            self.max_overview_chars,
        )
        poster_url = _poster_url(data, self.base_url)
        episodes = _positive_int(data.get("episodes"))
        duration = _positive_int(data.get("duration"))
        kind = str(data.get("kind") or "").strip() or None
        status = str(data.get("status") or "").strip() or None

        return Anime(
            shikimori_id=anime_id,
            title=title,
            original_title=original_title or title,
            overview=overview,
            poster_url=poster_url,
            score=_parse_score(data.get("score")),
            year=_parse_year(data.get("aired_on") or data.get("released_on")),
            genres=tuple(genres),
            kind=kind,
            episodes=episodes,
            duration=duration,
            status=status,
        )


def _parse_score(value: object) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 10 else None


def _parse_year(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        year = date.fromisoformat(text[:10]).year
    except ValueError:
        try:
            year = int(text[:4])
        except (TypeError, ValueError):
            return None
    return year if 1900 <= year <= 2200 else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _poster_url(data: dict[str, Any], base_url: str) -> str | None:
    raw_image = data.get("image")
    if not isinstance(raw_image, dict):
        return None
    raw = str(raw_image.get("original") or raw_image.get("preview") or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return urljoin(f"{base_url}/", raw)


_BBCODE_RE = re.compile(r"\[/?[^\]]+\]")
_SPACE_RE = re.compile(r"[ \t]+")


def _clean_description(value: str, max_chars: int) -> str:
    text = _BBCODE_RE.sub("", value.replace("\r", ""))
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line).strip()
    if len(text) <= max_chars:
        return text
    shortened = text[: max_chars + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return shortened + "…"
