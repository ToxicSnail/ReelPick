from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

import httpx

from kinotyk.domain import Movie

logger = logging.getLogger(__name__)
_IMDB_ID_RE = re.compile(r"^tt\d+$")
_SPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_TITLE_SUFFIX_RE = re.compile(
    r"\s*\((?:фильм|мультфильм)(?:,?\s*\d{4})?\)\s*$",
    re.IGNORECASE,
)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_PLOT_CUES = (
    "сюжет",
    "повеств",
    "рассказыва",
    "история",
    "герой",
    "героин",
    "семья",
    "персонаж",
    "события",
    "действие",
)
_METADATA_CUES = (
    "режисс",
    "сценар",
    "продюсер",
    "студ",
    "премьера",
    "главные роли",
    "роль испол",
    "в прокат",
)
_RUSSIAN_OVERVIEW_FALLBACK = "Русское описание для этого фильма пока не найдено."


class RussianLocalizer:
    """Best-effort Russian metadata enrichment without API keys.

    The primary lookup uses Wikidata's regular Action API instead of the public
    SPARQL endpoint. We search by the original title and then verify the exact
    IMDb id (P345), so a similarly named movie is not accepted by accident.

    Every external step fails independently. If Wikidata is temporarily down,
    the code still tries a direct full-text search in ru.wikipedia instead of
    returning the English Cinemeta card immediately.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        wikidata_api_url: str,
        wikipedia_api_url: str,
        timeout_seconds: float,
        max_overview_chars: int,
        user_agent: str,
    ) -> None:
        self.client = client
        self.wikidata_api_url = wikidata_api_url
        self.wikipedia_api_url = wikipedia_api_url
        self.timeout_seconds = timeout_seconds
        self.max_overview_chars = max_overview_chars
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._cache: dict[str, tuple[str | None, str]] = {}

    async def localize(self, movie: Movie) -> Movie:
        cached = self._cache.get(movie.imdb_id)
        if cached is not None:
            title, overview = cached
            return movie.localized(title=title, overview=overview)

        title: str | None = None
        page_title: str | None = None
        overview: str | None = None
        search_snippet: str | None = None

        # 1. Prefer an exact Wikidata match validated by IMDb id.
        try:
            title, page_title = await self._resolve_by_imdb(movie)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.info("Wikidata localization unavailable for %s: %s", movie.imdb_id, exc)

        # 2. If Wikidata supplied a Russian article, get a short Russian intro.
        if page_title:
            try:
                overview = await self._get_extract(page_title)
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                logger.info("ru.wikipedia extract failed for %s: %s", movie.imdb_id, exc)

        # 3. Direct Wikipedia fallback. This still runs when Wikidata is down.
        if not title or not overview:
            try:
                fallback_title, fallback_page, search_snippet = await self._search_wikipedia(movie)
                if not title:
                    title = fallback_title
                if not page_title:
                    page_title = fallback_page

                if not overview and fallback_page:
                    try:
                        overview = await self._get_extract(fallback_page)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                        logger.info(
                            "ru.wikipedia fallback extract failed for %s: %s",
                            movie.imdb_id,
                            exc,
                        )
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                logger.info("ru.wikipedia search failed for %s: %s", movie.imdb_id, exc)

        overview = _prepare_russian_overview(
            overview or search_snippet,
            max_chars=self.max_overview_chars,
        )
        if not overview and _looks_russian(movie.overview):
            overview = _shorten_overview(movie.overview, self.max_overview_chars)
        if not overview:
            # Do not leak an English synopsis into an otherwise Russian interface.
            overview = _RUSSIAN_OVERVIEW_FALLBACK

        self._cache[movie.imdb_id] = (title, overview)
        return movie.localized(title=title, overview=overview)

    async def _request_json(self, url: str, *, params: dict[str, str]) -> dict[str, Any]:
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
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        assert last_error is not None
        raise last_error

    async def _resolve_by_imdb(self, movie: Movie) -> tuple[str | None, str | None]:
        if not _IMDB_ID_RE.fullmatch(movie.imdb_id):
            return None, None

        search = await self._request_json(
            self.wikidata_api_url,
            params={
                "action": "wbsearchentities",
                "search": movie.original_title,
                "language": "en",
                "uselang": "ru",
                "type": "item",
                "limit": "8",
                "format": "json",
            },
        )
        raw_results = search.get("search", [])
        if not isinstance(raw_results, list):
            return None, None

        entity_ids = [
            str(item.get("id") or "")
            for item in raw_results
            if isinstance(item, dict) and str(item.get("id") or "").startswith("Q")
        ]
        entities = await self._get_wikidata_entities(entity_ids)
        for entity_id in entity_ids:
            entity = entities.get(entity_id, {})
            if not _entity_has_imdb_id(entity, movie.imdb_id):
                continue

            page_title = _entity_ruwiki_title(entity)
            title = _entity_label(entity, "ru")
            if not title and page_title:
                title = _clean_page_title(page_title)
            return title, page_title

        return None, None

    async def _get_wikidata_entities(
        self, entity_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not entity_ids:
            return {}
        data = await self._request_json(
            self.wikidata_api_url,
            params={
                "action": "wbgetentities",
                "ids": "|".join(entity_ids),
                "props": "labels|sitelinks|claims",
                "languages": "ru|en",
                "format": "json",
            },
        )
        raw_entities = data.get("entities", {})
        if not isinstance(raw_entities, dict):
            return {}
        return {
            entity_id: entity
            for entity_id, entity in raw_entities.items()
            if isinstance(entity_id, str) and isinstance(entity, dict)
        }

    async def _search_wikipedia(self, movie: Movie) -> tuple[str | None, str | None, str | None]:
        year = f" {movie.year}" if movie.year else ""
        query = f'"{movie.original_title}"{year} фильм'
        data = await self._request_json(
            self.wikipedia_api_url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": "0",
                "srlimit": "8",
                "format": "json",
                "formatversion": "2",
                "utf8": "1",
            },
        )
        raw_results = data.get("query", {}).get("search", [])
        if not isinstance(raw_results, list) or not raw_results:
            return None, None, None

        selected = max(
            (item for item in raw_results if isinstance(item, dict)),
            key=lambda item: _wikipedia_result_score(item, movie),
            default=None,
        )
        if not selected:
            return None, None, None

        page_title = str(selected.get("title") or "").strip()
        if not page_title:
            return None, None, None
        snippet = _clean_search_snippet(str(selected.get("snippet") or ""))
        return _clean_page_title(page_title), page_title, snippet or None

    async def _get_extract(self, page_title: str) -> str | None:
        data = await self._request_json(
            self.wikipedia_api_url,
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": "1",
                "explaintext": "1",
                "exsentences": "5",
                "redirects": "1",
                "titles": page_title,
                "format": "json",
                "formatversion": "2",
            },
        )
        pages = data.get("query", {}).get("pages", [])
        if not isinstance(pages, list) or not pages:
            return None
        page = pages[0] if isinstance(pages[0], dict) else {}
        if page.get("missing") is True:
            return None
        extract = page.get("extract")
        if not extract:
            return None
        return _SPACE_RE.sub(" ", str(extract)).strip()


def _entity_has_imdb_id(entity: dict[str, Any], imdb_id: str) -> bool:
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return False
    p345 = claims.get("P345", [])
    if not isinstance(p345, list):
        return False

    for claim in p345:
        if not isinstance(claim, dict):
            continue
        mainsnak = claim.get("mainsnak", {})
        if not isinstance(mainsnak, dict):
            continue
        datavalue = mainsnak.get("datavalue", {})
        if not isinstance(datavalue, dict):
            continue
        if str(datavalue.get("value") or "") == imdb_id:
            return True
    return False


def _entity_label(entity: dict[str, Any], language: str) -> str | None:
    labels = entity.get("labels", {})
    if not isinstance(labels, dict):
        return None
    label = labels.get(language)
    if not isinstance(label, dict):
        return None
    value = str(label.get("value") or "").strip()
    return value or None


def _entity_ruwiki_title(entity: dict[str, Any]) -> str | None:
    sitelinks = entity.get("sitelinks", {})
    if not isinstance(sitelinks, dict):
        return None
    ruwiki = sitelinks.get("ruwiki")
    if not isinstance(ruwiki, dict):
        return None
    title = str(ruwiki.get("title") or "").strip()
    return title or None


def _wikipedia_result_score(item: dict[str, Any], movie: Movie) -> int:
    title = str(item.get("title") or "")
    snippet = _clean_search_snippet(str(item.get("snippet") or ""))
    joined = f"{title} {snippet}".casefold()
    score = 0

    if _looks_russian(title):
        score += 2
    if "(фильм" in title.casefold() or "(мультфильм" in title.casefold():
        score += 4
    if movie.year and str(movie.year) in joined:
        score += 3
    if movie.original_title.casefold() in joined:
        score += 5
    if "фильм" in joined or "мультфильм" in joined:
        score += 2
    return score


def _clean_search_snippet(value: str) -> str:
    value = html.unescape(_TAG_RE.sub("", value))
    return _SPACE_RE.sub(" ", value).strip(" .…")


def _clean_page_title(title: str) -> str:
    return _TITLE_SUFFIX_RE.sub("", title).strip()


def _prepare_russian_overview(text: str | None, *, max_chars: int) -> str | None:
    if not text:
        return None
    text = _SPACE_RE.sub(" ", text).strip()
    if not _looks_russian(text):
        return None

    sentences = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if not sentences:
        return _shorten_overview(text, max_chars)

    # Wikipedia introductions often begin with production metadata. Prefer the
    # first premise-like sentence when it exists, then at most one following
    # sentence. This produces a shorter "what is it about" text and avoids the
    # dedicated plot section entirely.
    for index, sentence in enumerate(sentences):
        lowered = sentence.casefold()
        if any(cue in lowered for cue in _PLOT_CUES) and not any(
            cue in lowered for cue in _METADATA_CUES
        ):
            selected = " ".join(sentences[index : index + 2])
            return _shorten_overview(selected, max_chars)

    # If no premise sentence can be identified, keep only the first few intro
    # sentences rather than returning the whole encyclopedic lead.
    selected = " ".join(sentences[:3])
    return _shorten_overview(selected, max_chars)


def _looks_russian(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text))


def _shorten_overview(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    text = _SPACE_RE.sub(" ", text).strip()
    if len(text) <= limit:
        return text

    clipped = text[: limit + 1]
    sentence_end = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    if sentence_end >= int(limit * 0.55):
        return clipped[: sentence_end + 1].strip()

    word_end = clipped.rfind(" ", 0, limit)
    if word_end <= 0:
        word_end = limit
    return text[:word_end].rstrip(" ,;:-") + "…"
