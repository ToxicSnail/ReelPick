import asyncio

import httpx

from kinotyk.clients.localization import RussianLocalizer
from kinotyk.domain import Movie


def _movie(
    *,
    imdb_id: str = "tt1375666",
    title: str = "Inception",
    overview: str = "English overview",
    year: int = 2010,
) -> Movie:
    return Movie(
        imdb_id=imdb_id,
        title=title,
        original_title=title,
        overview=overview,
        poster_url=None,
        rating=8.8,
        year=year,
        genres=("Sci-Fi",),
    )


def _localizer(http: httpx.AsyncClient) -> RussianLocalizer:
    return RussianLocalizer(
        http,
        wikidata_api_url="https://www.wikidata.org/w/api.php",
        wikipedia_api_url="https://ru.wikipedia.org/w/api.php",
        timeout_seconds=2,
        max_overview_chars=520,
        user_agent="Kinotyk-Test/1.1",
    )


def test_localize_by_exact_imdb_via_wikidata_and_ruwiki() -> None:
    async def scenario() -> None:
        calls = {"search": 0, "entity": 0, "wiki": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "www.wikidata.org":
                action = request.url.params.get("action")
                if action == "wbsearchentities":
                    calls["search"] += 1
                    return httpx.Response(200, json={"search": [{"id": "Q25188"}]})
                if action == "wbgetentities":
                    calls["entity"] += 1
                    return httpx.Response(
                        200,
                        json={
                            "entities": {
                                "Q25188": {
                                    "labels": {"ru": {"value": "Начало"}},
                                    "sitelinks": {
                                        "ruwiki": {"title": "Начало (фильм, 2010)"}
                                    },
                                    "claims": {
                                        "P345": [
                                            {
                                                "mainsnak": {
                                                    "datavalue": {"value": "tt1375666"}
                                                }
                                            }
                                        ]
                                    },
                                }
                            }
                        },
                    )
            if request.url.host == "ru.wikipedia.org":
                calls["wiki"] += 1
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": [
                                {
                                    "title": "Начало (фильм, 2010)",
                                    "extract": (
                                        "«Начало» — научно-фантастический фильм Кристофера Нолана. "
                                        "Сюжет рассказывает о специалисте, который умеет проникать "
                                        "в сны других людей. Ему предлагают необычную задачу."
                                    ),
                                }
                            ]
                        }
                    },
                )
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            localizer = _localizer(http)
            localized = await localizer.localize(_movie())
            localized_again = await localizer.localize(_movie())

        assert localized.title == "Начало"
        assert localized.overview.startswith("Сюжет рассказывает")
        assert "Кристофера Нолана" not in localized.overview
        assert localized_again == localized
        assert calls == {"search": 1, "entity": 1, "wiki": 1}

    asyncio.run(scenario())


def test_incredibles_gets_russian_title_and_overview() -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "www.wikidata.org":
                action = request.url.params.get("action")
                if action == "wbsearchentities":
                    return httpx.Response(200, json={"search": [{"id": "Q213081"}]})
                if action == "wbgetentities":
                    return httpx.Response(
                        200,
                        json={
                            "entities": {
                                "Q213081": {
                                    "labels": {"ru": {"value": "Суперсемейка"}},
                                    "sitelinks": {"ruwiki": {"title": "Суперсемейка"}},
                                    "claims": {
                                        "P345": [
                                            {
                                                "mainsnak": {
                                                    "datavalue": {"value": "tt0317705"}
                                                }
                                            }
                                        ]
                                    },
                                }
                            }
                        },
                    )
            if request.url.host == "ru.wikipedia.org":
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": [
                                {
                                    "title": "Суперсемейка",
                                    "extract": (
                                        "«Суперсемейка» — американский анимационный фильм. "
                                        "История рассказывает о семье бывших супергероев, которые "
                                        "пытаются вести обычную жизнь. Но обстоятельства снова "
                                        "заставляют их использовать свои способности."
                                    ),
                                }
                            ]
                        }
                    },
                )
            return httpx.Response(404)

        movie = _movie(
            imdb_id="tt0317705",
            title="The Incredibles",
            overview="While trying to lead a quiet suburban life...",
            year=2004,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            localized = await _localizer(http).localize(movie)

        assert localized.title == "Суперсемейка"
        assert localized.original_title == "The Incredibles"
        assert localized.overview.startswith("История рассказывает")
        assert "While trying" not in localized.overview

    asyncio.run(scenario())


def test_wikidata_failure_still_falls_back_to_russian_wikipedia() -> None:
    async def scenario() -> None:
        calls = {"wikidata": 0, "wiki_search": 0, "wiki_extract": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "www.wikidata.org":
                calls["wikidata"] += 1
                return httpx.Response(503, text="temporarily unavailable")

            if request.url.host == "ru.wikipedia.org":
                if request.url.params.get("list") == "search":
                    calls["wiki_search"] += 1
                    return httpx.Response(
                        200,
                        json={
                            "query": {
                                "search": [
                                    {
                                        "title": "Суперсемейка",
                                        "snippet": (
                                            "The Incredibles — мультфильм 2004 года о семье "
                                            "супергероев."
                                        ),
                                    }
                                ]
                            }
                        },
                    )
                calls["wiki_extract"] += 1
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": [
                                {
                                    "title": "Суперсемейка",
                                    "extract": (
                                        "«Суперсемейка» — анимационный фильм. "
                                        "Сюжет рассказывает о семье супергероев, которая пытается "
                                        "совмещать обычную жизнь со своими способностями."
                                    ),
                                }
                            ]
                        }
                    },
                )
            return httpx.Response(404)

        movie = _movie(
            imdb_id="tt0317705",
            title="The Incredibles",
            overview="English synopsis that must not be shown",
            year=2004,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            localized = await _localizer(http).localize(movie)

        assert localized.title == "Суперсемейка"
        assert localized.overview.startswith("Сюжет рассказывает")
        # Wikidata is retried, then Wikipedia still works independently.
        assert calls == {"wikidata": 2, "wiki_search": 1, "wiki_extract": 1}

    asyncio.run(scenario())


def test_english_overview_is_not_leaked_when_all_localization_sources_fail() -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="offline")

        movie = _movie(overview="This English synopsis should never reach the Russian card.")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            localized = await _localizer(http).localize(movie)

        assert localized.title == "Inception"
        assert localized.overview == "Русское описание для этого фильма пока не найдено."
        assert "English" not in localized.overview

    asyncio.run(scenario())
