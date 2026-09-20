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

    asyncio.run(scenario())
