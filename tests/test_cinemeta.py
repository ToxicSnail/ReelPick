import asyncio

import httpx

from kinotyk.clients.cinemeta import CinemetaClient


def test_catalog_and_movie_parsing() -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if "/catalog/movie/top/genre=Sci-Fi&skip=100.json" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "metas": [
                            {
                                "id": "tt1375666",
                                "name": "Inception",
                                "imdbRating": "8.8",
                                "releaseInfo": "2010",
                            },
                            {"id": "bad-id", "name": "Ignore me"},
                        ]
                    },
                )
            if request.url.path.endswith("/meta/movie/tt1375666.json"):
                return httpx.Response(
                    200,
                    json={
                        "meta": {
                            "id": "tt1375666",
                            "name": "Inception",
                            "imdbRating": "8.8",
                            "releaseInfo": "2010",
                            "poster": "https://example.test/poster.jpg",
                            "description": "A thief enters dreams.",
                            "genres": ["Action", "Sci-Fi", "Thriller"],
                            "director": ["Christopher Nolan"],
                        }
                    },
                )
            return httpx.Response(404, json={"error": "not found"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = CinemetaClient(
                http,
                base_url="https://v3-cinemeta.strem.io",
                timeout_seconds=2,
            )
            candidates = await client.catalog("Sci-Fi", skip=100)
            assert len(candidates) == 1
            assert candidates[0].imdb_id == "tt1375666"
            assert candidates[0].rating == 8.8

            movie = await client.get_movie("tt1375666")
            assert movie.title == "Inception"
            assert movie.year == 2010
            assert movie.genres == ("Action", "Sci-Fi", "Thriller")
            assert movie.director == "Christopher Nolan"
            assert movie.studio is None

    asyncio.run(scenario())


def test_cinemeta_search_parsing() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/catalog/movie/top/search=matrix.json" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "metas": [
                        {
                            "id": "tt0133093",
                            "name": "The Matrix",
                            "imdbRating": "8.7",
                            "releaseInfo": "1999",
                        },
                        {"id": "bad", "name": "Skip me"},
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = CinemetaClient(
                http,
                base_url="https://v3-cinemeta.strem.io",
                timeout_seconds=2,
            )
            candidates = await client.search("matrix")

        assert len(candidates) == 1
        assert candidates[0].imdb_id == "tt0133093"
        assert candidates[0].title == "The Matrix"
        assert candidates[0].rating == 8.7
        assert candidates[0].year == 1999

    asyncio.run(scenario())


def test_cinemeta_search_blank_query_returns_empty() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request expected")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = CinemetaClient(
                http,
                base_url="https://v3-cinemeta.strem.io",
                timeout_seconds=2,
            )
            assert await client.search("   ") == []

    asyncio.run(scenario())
