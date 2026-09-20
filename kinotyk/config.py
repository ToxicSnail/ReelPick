from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Load a tiny .env subset without an extra dependency.

    Existing environment variables always win. Quotes around whole values are
    stripped; comments are supported only on their own lines.
    """
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _get_skips() -> tuple[int, ...]:
    raw = os.getenv("CINEMETA_SKIPS", "0,100,200,300")
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"CINEMETA_SKIPS contains non-integer {part!r}") from exc
        if value < 0:
            raise ValueError("CINEMETA_SKIPS values must be >= 0")
        values.append(value)
    return tuple(values or [0])


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_path: Path
    cinemeta_base_url: str = "https://v3-cinemeta.strem.io"
    wikidata_api_url: str = "https://www.wikidata.org/w/api.php"
    wikipedia_api_url: str = "https://ru.wikipedia.org/w/api.php"
    min_imdb_rating: float = 6.0
    cinemeta_skips: tuple[int, ...] = (0, 100, 200, 300)
    http_timeout_seconds: float = 12.0
    telegram_poll_timeout_seconds: int = 30
    max_overview_chars: int = 520
    log_level: str = "INFO"
    user_agent: str = "Kinotyk/1.1 (Telegram movie discovery bot)"

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "Settings":
        _load_dotenv(Path(env_file))

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("BOT_TOKEN is required. Put it in .env or environment variables.")

        database_path = Path(os.getenv("DATABASE_PATH", "./data/kinotyk.sqlite3"))
        min_rating = _get_float("MIN_IMDB_RATING", 6.0)
        if not 0 <= min_rating <= 10:
            raise ValueError("MIN_IMDB_RATING must be between 0 and 10")

        timeout = _get_float("HTTP_TIMEOUT_SECONDS", 12.0)
        if timeout <= 0:
            raise ValueError("HTTP_TIMEOUT_SECONDS must be > 0")

        poll_timeout = _get_int("TELEGRAM_POLL_TIMEOUT_SECONDS", 30)
        if poll_timeout < 1 or poll_timeout > 50:
            raise ValueError("TELEGRAM_POLL_TIMEOUT_SECONDS must be between 1 and 50")

        max_overview_chars = _get_int("MAX_OVERVIEW_CHARS", 520)
        if max_overview_chars < 120 or max_overview_chars > 700:
            raise ValueError("MAX_OVERVIEW_CHARS must be between 120 and 700")

        return cls(
            bot_token=bot_token,
            database_path=database_path,
            cinemeta_base_url=os.getenv(
                "CINEMETA_BASE_URL", "https://v3-cinemeta.strem.io"
            ).rstrip("/"),
            wikidata_api_url=os.getenv(
                "WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php"
            ),
            wikipedia_api_url=os.getenv(
                "WIKIPEDIA_API_URL", "https://ru.wikipedia.org/w/api.php"
            ),
            min_imdb_rating=min_rating,
            cinemeta_skips=_get_skips(),
            http_timeout_seconds=timeout,
            telegram_poll_timeout_seconds=poll_timeout,
            max_overview_chars=max_overview_chars,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            user_agent=os.getenv(
                "HTTP_USER_AGENT", "Kinotyk/1.1 (Telegram movie discovery bot)"
            ),
        )
