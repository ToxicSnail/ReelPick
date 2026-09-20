from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kinotyk.domain import Movie, StoredMovie

_ALLOWED_COLLECTIONS = {"watched", "favorite", "watchlist", "skipped"}


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
                CREATE TABLE IF NOT EXISTS user_movies (
                    telegram_id INTEGER NOT NULL,
                    imdb_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    year INTEGER,
                    poster_url TEXT,
                    watched INTEGER NOT NULL DEFAULT 0 CHECK (watched IN (0, 1)),
                    skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
                    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
                    watchlist INTEGER NOT NULL DEFAULT 0 CHECK (watchlist IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, imdb_id),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_movies_watched "
                "ON user_movies(telegram_id, watched)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_movies_favorite "
                "ON user_movies(telegram_id, favorite)"
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

    def excluded_movie_ids(self, telegram_id: int) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT imdb_id
                FROM user_movies
                WHERE telegram_id = ?
                  AND (watched = 1 OR skipped = 1 OR watchlist = 1)
                """,
                (telegram_id,),
            ).fetchall()
        return {str(row["imdb_id"]) for row in rows}

    def _ensure_movie(self, telegram_id: int, movie: Movie) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_movies (telegram_id, imdb_id, title, year, poster_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id, imdb_id) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    poster_url = excluded.poster_url,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (telegram_id, movie.imdb_id, movie.title, movie.year, movie.poster_url),
            )

    def mark_watched(self, telegram_id: int, movie: Movie) -> None:
        self._ensure_movie(telegram_id, movie)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE user_movies
                SET watched = 1, skipped = 0, watchlist = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND imdb_id = ?
                """,
                (telegram_id, movie.imdb_id),
            )

    def mark_skipped(self, telegram_id: int, movie: Movie) -> None:
        self._ensure_movie(telegram_id, movie)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE user_movies
                SET skipped = 1, watchlist = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND imdb_id = ?
                """,
                (telegram_id, movie.imdb_id),
            )

    def toggle_favorite(self, telegram_id: int, movie: Movie) -> bool:
        self._ensure_movie(telegram_id, movie)
        with self._connect() as conn:
            current = conn.execute(
                "SELECT favorite FROM user_movies WHERE telegram_id = ? AND imdb_id = ?",
                (telegram_id, movie.imdb_id),
            ).fetchone()
            new_value = not bool(current["favorite"] if current else 0)
            conn.execute(
                """
                UPDATE user_movies
                SET favorite = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND imdb_id = ?
                """,
                (int(new_value), telegram_id, movie.imdb_id),
            )
        return new_value

    def toggle_watchlist(self, telegram_id: int, movie: Movie) -> bool:
        self._ensure_movie(telegram_id, movie)
        with self._connect() as conn:
            current = conn.execute(
                "SELECT watchlist FROM user_movies WHERE telegram_id = ? AND imdb_id = ?",
                (telegram_id, movie.imdb_id),
            ).fetchone()
            new_value = not bool(current["watchlist"] if current else 0)
            conn.execute(
                """
                UPDATE user_movies
                SET watchlist = ?, skipped = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND imdb_id = ?
                """,
                (int(new_value), telegram_id, movie.imdb_id),
            )
        return new_value

    def collection_stats(self, telegram_id: int) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(watched), 0) AS watched,
                    COALESCE(SUM(favorite), 0) AS favorite,
                    COALESCE(SUM(watchlist), 0) AS watchlist,
                    COALESCE(SUM(skipped), 0) AS skipped
                FROM user_movies
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
        assert row is not None
        return {key: int(row[key]) for key in _ALLOWED_COLLECTIONS}

    def list_collection(
        self,
        telegram_id: int,
        collection: str,
        *,
        limit: int = 8,
        offset: int = 0,
    ) -> tuple[list[StoredMovie], int]:
        if collection not in _ALLOWED_COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        with self._connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM user_movies WHERE telegram_id = ? AND {collection} = 1",
                    (telegram_id,),
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT imdb_id, title, year, poster_url, watched, skipped, favorite, watchlist
                FROM user_movies
                WHERE telegram_id = ? AND {collection} = 1
                ORDER BY updated_at DESC, title COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                (telegram_id, limit, offset),
            ).fetchall()

        movies = [
            StoredMovie(
                imdb_id=str(row["imdb_id"]),
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
        return movies, total
