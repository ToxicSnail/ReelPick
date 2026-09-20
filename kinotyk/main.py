from __future__ import annotations

import asyncio
import logging

import httpx

from kinotyk.app import KinotykApp
from kinotyk.clients.cinemeta import CinemetaClient
from kinotyk.clients.localization import RussianLocalizer
from kinotyk.clients.telegram import TelegramClient
from kinotyk.config import Settings
from kinotyk.db import Database
from kinotyk.services.recommendation import RecommendationService


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def async_main() -> None:
    try:
        settings = Settings.load()
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    configure_logging(settings.log_level)

    limits = httpx.Limits(max_connections=30, max_keepalive_connections=10)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        database = Database(settings.database_path)
        cinemeta = CinemetaClient(
            client,
            base_url=settings.cinemeta_base_url,
            timeout_seconds=settings.http_timeout_seconds,
        )
        localizer = RussianLocalizer(
            client,
            wikidata_api_url=settings.wikidata_api_url,
            wikipedia_api_url=settings.wikipedia_api_url,
            timeout_seconds=settings.http_timeout_seconds,
            max_overview_chars=settings.max_overview_chars,
            user_agent=settings.user_agent,
        )
        telegram = TelegramClient(
            client,
            bot_token=settings.bot_token,
            poll_timeout_seconds=settings.telegram_poll_timeout_seconds,
        )
        recommendations = RecommendationService(
            database=database,
            cinemeta=cinemeta,
            localizer=localizer,
            min_imdb_rating=settings.min_imdb_rating,
            skips=settings.cinemeta_skips,
        )
        app = KinotykApp(
            telegram=telegram,
            database=database,
            recommendations=recommendations,
        )
        await app.run()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Kinotyk stopped")


if __name__ == "__main__":
    main()
