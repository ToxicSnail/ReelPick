from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kinotyk.domain import Anime, Movie, StoredMedia

_ALLOWED_COLLECTIONS = {"watched", "favorite", "watchlist", "skipped"}
_ALLOWED_MEDIA_TYPES = {"movie", "anime"}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    language_code TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_media (
                    telegram_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'anime')),
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    year INTEGER,
                    poster_url TEXT,
                    watched INTEGER NOT NULL DEFAULT 0 CHECK (watched IN (0, 1)),
                    skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
                    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
                    watchlist INTEGER NOT NULL DEFAULT 0 CHECK (watchlist IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, media_type, external_id),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_media_watched "
                "ON user_media(telegram_id, media_type, watched)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_media_favorite "
                "ON user_media(telegram_id, media_type, favorite)"
            )
            self._migrate_legacy_movies(conn)

    def _migrate_legacy_movies(self, conn: sqlite3.Connection) -> None:
        legacy = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_movies'"
        ).fetchone()
        if legacy is None:
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO user_media (
                telegram_id, media_type, external_id, title, year, poster_url,
                watched, skipped, favorite, watchlist, created_at, updated_at
            )
            SELECT
                telegram_id, 'movie', imdb_id, title, year, poster_url,
                watched, skipped, favorite, watchlist, created_at, updated_at
            FROM user_movies
            """
        )

    def upsert_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, language_code)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    language_code = excluded.language_code,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (telegram_id, username, first_name, language_code),
            )

    def excluded_media_ids(self, telegram_id: int, media_type: str) -> set[str]:
        self._validate_media_type(media_type)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT external_id
                FROM user_media
                WHERE telegram_id = ? AND media_type = ?
                  AND (watched = 1 OR skipped = 1 OR watchlist = 1)
                """,
                (telegram_id, media_type),
            ).fetchall()
        return {str(row["external_id"]) for row in rows}

    def excluded_movie_ids(self, telegram_id: int) -> set[str]:
        return self.excluded_media_ids(telegram_id, "movie")

    def _ensure_media(
        self,
        telegram_id: int,
        media_type: str,
        external_id: str,
        title: str,
        year: int | None,
        poster_url: str | None,
    ) -> None:
        self._validate_media_type(media_type)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_media (
                    telegram_id, media_type, external_id, title, year, poster_url
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id, media_type, external_id) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    poster_url = excluded.poster_url,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (telegram_id, media_type, external_id, title, year, poster_url),
            )

    def _set_watched(self, telegram_id: int, media_type: str, external_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE user_media
                SET watched = 1, skipped = 0, watchlist = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND media_type = ? AND external_id = ?
                """,
                (telegram_id, media_type, external_id),
            )

    def _set_skipped(self, telegram_id: int, media_type: str, external_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE user_media
                SET skipped = 1, watchlist = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND media_type = ? AND external_id = ?
                """,
                (telegram_id, media_type, external_id),
            )

    def _toggle_flag(
        self,
        telegram_id: int,
        media_type: str,
        external_id: str,
        flag: str,
    ) -> bool:
        if flag not in {"favorite", "watchlist"}:
            raise ValueError(f"Unsupported flag: {flag}")
        with self._connect() as conn:
            current = conn.execute(
                f"SELECT {flag} FROM user_media "
                "WHERE telegram_id = ? AND media_type = ? AND external_id = ?",
                (telegram_id, media_type, external_id),
            ).fetchone()
            new_value = not bool(current[flag] if current else 0)
            if flag == "watchlist":
                conn.execute(
                    """
                    UPDATE user_media
                    SET watchlist = ?, skipped = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_id = ? AND media_type = ? AND external_id = ?
                    """,
                    (int(new_value), telegram_id, media_type, external_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE user_media
                    SET favorite = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_id = ? AND media_type = ? AND external_id = ?
                    """,
                    (int(new_value), telegram_id, media_type, external_id),
                )
        return new_value

    def mark_watched(self, telegram_id: int, movie: Movie) -> None:
        self._ensure_media(
            telegram_id, "movie", movie.imdb_id, movie.title, movie.year, movie.poster_url
        )
        self._set_watched(telegram_id, "movie", movie.imdb_id)

    def mark_skipped(self, telegram_id: int, movie: Movie) -> None:
        self._ensure_media(
            telegram_id, "movie", movie.imdb_id, movie.title, movie.year, movie.poster_url
        )
        self._set_skipped(telegram_id, "movie", movie.imdb_id)

    def toggle_favorite(self, telegram_id: int, movie: Movie) -> bool:
        self._ensure_media(
            telegram_id, "movie", movie.imdb_id, movie.title, movie.year, movie.poster_url
        )
        return self._toggle_flag(telegram_id, "movie", movie.imdb_id, "favorite")

    def toggle_watchlist(self, telegram_id: int, movie: Movie) -> bool:
        self._ensure_media(
            telegram_id, "movie", movie.imdb_id, movie.title, movie.year, movie.poster_url
        )
        return self._toggle_flag(telegram_id, "movie", movie.imdb_id, "watchlist")

    def mark_anime_watched(self, telegram_id: int, anime: Anime) -> None:
        external_id = str(anime.shikimori_id)
        self._ensure_media(
            telegram_id, "anime", external_id, anime.title, anime.year, anime.poster_url
        )
        self._set_watched(telegram_id, "anime", external_id)

    def mark_anime_skipped(self, telegram_id: int, anime: Anime) -> None:
        external_id = str(anime.shikimori_id)
        self._ensure_media(
            telegram_id, "anime", external_id, anime.title, anime.year, anime.poster_url
        )
        self._set_skipped(telegram_id, "anime", external_id)

    def toggle_anime_favorite(self, telegram_id: int, anime: Anime) -> bool:
        external_id = str(anime.shikimori_id)
        self._ensure_media(
            telegram_id, "anime", external_id, anime.title, anime.year, anime.poster_url
        )
        return self._toggle_flag(telegram_id, "anime", external_id, "favorite")

    def toggle_anime_watchlist(self, telegram_id: int, anime: Anime) -> bool:
        external_id = str(anime.shikimori_id)
        self._ensure_media(
            telegram_id, "anime", external_id, anime.title, anime.year, anime.poster_url
        )
        return self._toggle_flag(telegram_id, "anime", external_id, "watchlist")

    def clear_collection_flag(
        self,
        telegram_id: int,
        media_type: str,
        external_id: str,
        collection: str,
    ) -> None:
        if collection not in _ALLOWED_COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        self._validate_media_type(media_type)
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE user_media
                SET {collection} = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND media_type = ? AND external_id = ?
                """,
                (telegram_id, media_type, external_id),
            )
            conn.execute(
                """
                DELETE FROM user_media
                WHERE telegram_id = ? AND media_type = ? AND external_id = ?
                  AND watched = 0 AND skipped = 0 AND favorite = 0 AND watchlist = 0
                """,
                (telegram_id, media_type, external_id),
            )

    def collection_stats(self, telegram_id: int, media_type: str | None = None) -> dict[str, int]:
        params: tuple[object, ...]
        media_filter = ""
        if media_type is not None:
            self._validate_media_type(media_type)
            media_filter = " AND media_type = ?"
            params = (telegram_id, media_type)
        else:
            params = (telegram_id,)

        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(watched), 0) AS watched,
                    COALESCE(SUM(favorite), 0) AS favorite,
                    COALESCE(SUM(watchlist), 0) AS watchlist,
                    COALESCE(SUM(skipped), 0) AS skipped
                FROM user_media
                WHERE telegram_id = ?{media_filter}
                """,
                params,
            ).fetchone()
        assert row is not None
        return {key: int(row[key]) for key in _ALLOWED_COLLECTIONS}

    def list_collection(
        self,
        telegram_id: int,
        collection: str,
        *,
        media_type: str = "movie",
        limit: int = 8,
        offset: int = 0,
    ) -> tuple[list[StoredMedia], int]:
        if collection not in _ALLOWED_COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        self._validate_media_type(media_type)
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        with self._connect() as conn:
            total = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM user_media
                    WHERE telegram_id = ? AND media_type = ? AND {collection} = 1
                    """,
                    (telegram_id, media_type),
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT external_id, media_type, title, year, poster_url,
                       watched, skipped, favorite, watchlist
                FROM user_media
                WHERE telegram_id = ? AND media_type = ? AND {collection} = 1
                ORDER BY updated_at DESC, title COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                (telegram_id, media_type, limit, offset),
            ).fetchall()

        media = [
            StoredMedia(
                external_id=str(row["external_id"]),
                media_type=str(row["media_type"]),
                title=str(row["title"]),
                year=int(row["year"]) if row["year"] is not None else None,
                poster_url=str(row["poster_url"]) if row["poster_url"] else None,
                watched=bool(row["watched"]),
                skipped=bool(row["skipped"]),
                favorite=bool(row["favorite"]),
                watchlist=bool(row["watchlist"]),
            )
            for row in rows
        ]
        return media, total

    @staticmethod
    def _validate_media_type(media_type: str) -> None:
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"Unknown media type: {media_type}")
