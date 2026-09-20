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
