from pathlib import Path

from kinotyk.db import Database
from kinotyk.domain import Movie


def make_movie() -> Movie:
    return Movie(
        imdb_id="tt1375666",
        title="Начало",
        original_title="Inception",
        overview="Описание",
        poster_url="https://example.test/poster.jpg",
        rating=8.8,
        year=2010,
        genres=("Sci-Fi", "Thriller"),
    )


def test_user_movie_flags_and_collection(tmp_path: Path) -> None:
    db = Database(tmp_path / "kinotyk.sqlite3")
    db.init()
    db.upsert_user(42, "neo", "Кирилл", "ru")
    movie = make_movie()

    assert db.collection_stats(42) == {
        "watched": 0,
        "favorite": 0,
        "watchlist": 0,
        "skipped": 0,
    }

    assert db.toggle_watchlist(42, movie) is True
    assert movie.imdb_id in db.excluded_movie_ids(42)
    assert db.collection_stats(42)["watchlist"] == 1

    assert db.toggle_favorite(42, movie) is True
    assert db.collection_stats(42)["favorite"] == 1

    db.mark_watched(42, movie)
    stats = db.collection_stats(42)
    assert stats["watched"] == 1
    assert stats["watchlist"] == 0
    assert stats["favorite"] == 1

    movies, total = db.list_collection(42, "watched")
    assert total == 1
    assert movies[0].title == "Начало"
    assert movies[0].watched is True


def test_skipped_movie_is_excluded(tmp_path: Path) -> None:
    db = Database(tmp_path / "kinotyk.sqlite3")
    db.init()
    db.upsert_user(7, None, "User", "ru")
    movie = make_movie()

    db.mark_skipped(7, movie)

    assert db.excluded_movie_ids(7) == {movie.imdb_id}
    assert db.collection_stats(7)["skipped"] == 1


def test_anime_collection_is_separate_from_movies(tmp_path: Path) -> None:
    from kinotyk.domain import Anime

    db = Database(tmp_path / "media.sqlite3")
    db.init()
    db.upsert_user(77, "user", "User", "ru")
    movie = make_movie()
    anime = Anime(
        shikimori_id=889,
        title="Пираты «Чёрной лагуны»",
        original_title="Black Lagoon",
        overview="Описание",
        poster_url=None,
        score=8.28,
        year=2006,
        genres=("Экшен",),
        kind="tv",
        episodes=12,
        duration=23,
    )

    db.mark_watched(77, movie)
    db.mark_anime_watched(77, anime)

    assert db.collection_stats(77, "movie")["watched"] == 1
    assert db.collection_stats(77, "anime")["watched"] == 1
    assert db.excluded_media_ids(77, "anime") == {"889"}

    anime_items, anime_total = db.list_collection(77, "watched", media_type="anime")
    assert anime_total == 1
    assert anime_items[0].media_type == "anime"
    assert anime_items[0].title == "Пираты «Чёрной лагуны»"


def test_clear_collection_flag_removes_item(tmp_path: Path) -> None:
    from kinotyk.domain import Anime

    db = Database(tmp_path / "remove.sqlite3")
    db.init()
    db.upsert_user(9, None, "User", "ru")
    anime = Anime(
        shikimori_id=2167,
        title="Кланнад",
        original_title="Clannad",
        overview="Описание",
        poster_url=None,
        score=8.2,
        year=2007,
        genres=("Драма",),
    )

    db.toggle_anime_watchlist(9, anime)
    assert db.collection_stats(9, "anime")["watchlist"] == 1

    db.clear_collection_flag(9, "anime", "2167", "watchlist")

    assert db.collection_stats(9, "anime")["watchlist"] == 0
    assert "2167" not in db.excluded_media_ids(9, "anime")
    items, total = db.list_collection(9, "watchlist", media_type="anime")
    assert total == 0
    assert items == []


def test_clear_collection_flag_keeps_other_categories(tmp_path: Path) -> None:
    db = Database(tmp_path / "keep.sqlite3")
    db.init()
    db.upsert_user(9, None, "User", "ru")
    movie = make_movie()

    db.toggle_favorite(9, movie)
    db.mark_watched(9, movie)
    assert db.collection_stats(9, "movie")["favorite"] == 1
    assert db.collection_stats(9, "movie")["watched"] == 1

    db.clear_collection_flag(9, "movie", movie.imdb_id, "favorite")

    stats = db.collection_stats(9, "movie")
    assert stats["favorite"] == 0
    assert stats["watched"] == 1
    watched, total = db.list_collection(9, "watched", media_type="movie")
    assert total == 1
    assert watched[0].external_id == movie.imdb_id

    db.clear_collection_flag(9, "movie", movie.imdb_id, "watched")
    assert db.collection_stats(9, "movie") == {
        "watched": 0,
        "favorite": 0,
        "watchlist": 0,
        "skipped": 0,
    }

    try:
        db.clear_collection_flag(9, "movie", movie.imdb_id, "bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError expected for unknown collection")


def test_global_stats(tmp_path: Path) -> None:
    from kinotyk.domain import Anime

    db = Database(tmp_path / "global.sqlite3")
    db.init()
    assert db.global_stats() == {
        "users": 0,
        "movies": 0,
        "anime": 0,
        "watched": 0,
        "favorite": 0,
    }

    movie = make_movie()
    anime = Anime(
        shikimori_id=2167,
        title="Кланнад",
        original_title="Clannad",
        overview="Описание",
        poster_url=None,
        score=8.2,
        year=2007,
        genres=("Драма",),
    )

    db.upsert_user(1, None, "One", "ru")
    db.upsert_user(2, None, "Two", "ru")
    db.toggle_watchlist(1, movie)
    db.mark_watched(1, movie)
    db.toggle_anime_favorite(2, anime)
    db.mark_anime_watched(2, anime)

    assert db.global_stats() == {
        "users": 2,
        "movies": 1,
        "anime": 1,
        "watched": 2,
        "favorite": 1,
    }


def test_legacy_user_movies_are_migrated(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            language_code TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE user_movies (
            telegram_id INTEGER NOT NULL,
            imdb_id TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            poster_url TEXT,
            watched INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            favorite INTEGER NOT NULL DEFAULT 0,
            watchlist INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, imdb_id)
        );
        INSERT INTO users (telegram_id, first_name) VALUES (5, 'Legacy');
        INSERT INTO user_movies (telegram_id, imdb_id, title, watched)
        VALUES (5, 'tt1375666', 'Начало', 1);
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    db.init()

    items, total = db.list_collection(5, "watched", media_type="movie")
    assert total == 1
    assert items[0].external_id == "tt1375666"
