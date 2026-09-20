import asyncio

import httpx

from kinotyk.clients.shikimori import ShikimoriClient


def test_shikimori_catalog_and_detail_parsing() -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/genres":
                return httpx.Response(
                    200,
                    json=[
                        {"id": 1, "name": "Action", "russian": "Экшен", "kind": "genre"},
                        {
                            "id": 40,
                            "name": "Psychological",
                            "russian": "Психологическое",
                            "kind": "theme",
                        },
                    ],
                )
            if request.url.path == "/api/animes":
                assert request.url.params["genre"] == "1"
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
                    },
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

    asyncio.run(scenario())
