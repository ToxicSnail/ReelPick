import asyncio

import httpx

from kinotyk.anime_genres import ANIME_GENRE_BY_KEY
from kinotyk.clients.shikimori import ShikimoriClient


def test_shikimori_catalog_and_detail_parsing() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/animes":
                assert request.url.params["genre_v2"] == "1"
                assert request.url.params["status"] == "released"
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 889,
                            "name": "Black Lagoon",
                            "russian": "Пираты «Чёрной лагуны»",
                            "score": "8.28",
                            "aired_on": "2006-04-09",
                        }
                    ],
                )
            if request.url.path == "/api/animes/889":
                return httpx.Response(
                    200,
                    json={
                        "id": 889,
                        "name": "Black Lagoon",
                        "russian": "Пираты «Чёрной лагуны»",
                        "score": "8.28",
                        "kind": "tv",
                        "status": "released",
                        "episodes": 12,
                        "duration": 23,
                        "aired_on": "2006-04-09",
                        "description": "История о команде наёмников.",
                        "image": {"original": "/system/animes/original/889.jpg"},
                        "genres": [
                            {"name": "Action", "russian": "Экшен"},
                            {"name": "Seinen", "russian": "Сэйнэн"},
                        ],
                        "studios": [
                            {"id": 2, "name": "Fake Studio", "real": False},
                            {"id": 11, "name": "Madhouse", "real": True},
                        ],
                    },
                )
            if request.url.path == "/api/animes/889/roles":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "roles": ["Main"],
                            "character": {"name": "Rock", "russian": "Рок"},
                            "person": None,
                        },
                        {
                            "roles": ["Episode Director"],
                            "character": None,
                            "person": {"id": 1, "name": "Someone Else", "russian": "Кто-то"},
                        },
                        {
                            "roles": ["Director", "Script"],
                            "character": None,
                            "person": {
                                "id": 8947,
                                "name": "Sunao Katabuchi",
                                "russian": "Сунао Катабути",
                            },
                        },
                    ],
                )
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ShikimoriClient(
                http,
                base_url="https://shikimori.one",
                timeout_seconds=2,
                user_agent="Kinotyk-Test/1.2",
            )
            candidates = await client.catalog("action", page=2)
            assert len(candidates) == 1
            assert candidates[0].shikimori_id == 889
            assert candidates[0].title == "Пираты «Чёрной лагуны»"
            assert candidates[0].score == 8.28

            anime = await client.get_anime(889)
            assert anime.title == "Пираты «Чёрной лагуны»"
            assert anime.original_title == "Black Lagoon"
            assert anime.genres == ("Экшен", "Сэйнэн")
            assert anime.episodes == 12
            assert anime.duration == 23
            assert anime.poster_url == "https://shikimori.one/system/animes/original/889.jpg"
            assert anime.studio == "Madhouse"
            assert anime.director == "Сунао Катабути"

    asyncio.run(scenario())


def test_shikimori_detail_survives_roles_endpoint_failure() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/animes/889":
                return httpx.Response(
                    200,
                    json={
                        "id": 889,
                        "name": "Black Lagoon",
                        "russian": "Пираты «Чёрной лагуны»",
                        "kind": "tv",
                        "description": "История о команде наёмников.",
                    },
                )
            if request.url.path == "/api/animes/889/roles":
                return httpx.Response(500)
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ShikimoriClient(
                http,
                base_url="https://shikimori.one",
                timeout_seconds=2,
                user_agent="Kinotyk-Test/1.2",
            )
            anime = await client.get_anime(889)

        assert anime.title == "Пираты «Чёрной лагуны»"
        assert anime.studio is None
        assert anime.director is None

    asyncio.run(scenario())


def test_shikimori_catalog_uses_genre_v2_ids() -> None:
    async def scenario(genre_key: str, expected_genre_v2: str) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            params = request.url.params
            captured["genre_v2"] = params.get("genre_v2", "")
            captured["genre"] = params.get("genre", "")
            return httpx.Response(200, json=[])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ShikimoriClient(
                http,
                base_url="https://shikimori.one",
                timeout_seconds=2,
                user_agent="Kinotyk-Test/1.2",
            )
            candidates = await client.catalog(genre_key)
            assert candidates == []
        assert captured["genre_v2"] == expected_genre_v2
        assert captured["genre"] == ""

    asyncio.run(scenario("suspense", "117"))
    asyncio.run(scenario("psychological", "40"))
    asyncio.run(scenario("action", "1"))


def test_shikimori_catalog_any_genre_has_no_genre_filter() -> None:
    async def scenario() -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            params = request.url.params
            captured["genre_v2"] = params.get("genre_v2", "")
            captured["genre"] = params.get("genre", "")
            return httpx.Response(200, json=[])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ShikimoriClient(
                http,
                base_url="https://shikimori.one",
                timeout_seconds=2,
                user_agent="Kinotyk-Test/1.2",
            )
            await client.catalog("any")

        assert captured["genre_v2"] == ""
        assert captured["genre"] == ""

    asyncio.run(scenario())


def test_anime_genre_v2_ids_are_explicit() -> None:
    assert ANIME_GENRE_BY_KEY["suspense"].genre_v2_id == 117
    assert ANIME_GENRE_BY_KEY["psychological"].genre_v2_id == 40
    assert ANIME_GENRE_BY_KEY["action"].genre_v2_id == 1
    assert ANIME_GENRE_BY_KEY["any"].genre_v2_id is None


def test_shikimori_search_uses_search_param() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/animes"
            assert request.url.params["search"] == "кланнад"
            assert request.url.params["limit"] == "20"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 2167,
                        "name": "Clannad",
                        "russian": "Кланнад",
                        "score": "8.2",
                        "aired_on": "2007-10-05",
                    },
                    {"id": 99999, "name": ""},
                ],
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ShikimoriClient(
                http,
                base_url="https://shikimori.one",
                timeout_seconds=2,
                user_agent="Kinotyk-Test/1.2",
            )
            candidates = await client.search(" кланнад ")

        assert len(candidates) == 1
        assert candidates[0].shikimori_id == 2167
        assert candidates[0].title == "Кланнад"
        assert candidates[0].score == 8.2
        assert candidates[0].year == 2007

    asyncio.run(scenario())


def test_shikimori_search_blank_query_returns_empty() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request expected")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = ShikimoriClient(
                http,
                base_url="https://shikimori.one",
                timeout_seconds=2,
                user_agent="Kinotyk-Test/1.2",
            )
            assert await client.search("   ") == []

    asyncio.run(scenario())
