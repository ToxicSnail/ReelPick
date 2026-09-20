from kinotyk.domain import Movie, StoredMedia
from kinotyk.ui import movie_caption, movie_keyboard


def test_movie_caption_is_russian_and_html_escaped() -> None:
    movie = Movie(
        imdb_id="tt1375666",
        title="Начало <2010>",
        original_title="Inception",
        overview="Сон & реальность.",
        poster_url=None,
        rating=8.8,
        year=2010,
        genres=("Sci-Fi", "Thriller"),
        director="Кристофер Нолан",
    )
    caption = movie_caption(movie)

    assert "Начало &lt;2010&gt;" in caption
    assert "IMDb" in caption
    assert "Фантастика · Триллер" in caption
    assert "Сон &amp; реальность." in caption
    assert "🎥 Режиссёр: <b>Кристофер Нолан</b>" in caption
    assert "Студия" not in caption
    assert len(caption) < 1024


def test_movie_callbacks_fit_telegram_limit() -> None:
    movie = Movie(
        imdb_id="tt1234567890",
        title="Movie",
        original_title="Movie",
        overview="Text",
        poster_url=None,
        rating=7.0,
        year=2020,
        genres=("Drama",),
    )
    keyboard = movie_keyboard(movie, "sci_fi")
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_anime_caption_and_callbacks() -> None:
    from kinotyk.domain import Anime
    from kinotyk.ui import anime_caption, anime_keyboard

    anime = Anime(
        shikimori_id=889,
        title="Пираты «Чёрной лагуны»",
        original_title="Black Lagoon",
        overview="История & приключения.",
        poster_url=None,
        score=8.28,
        year=2006,
        genres=("Экшен", "Сэйнэн"),
        kind="tv",
        episodes=12,
        duration=23,
        studio="Madhouse",
        director="Сунао Катабути",
    )
    caption = anime_caption(anime)
    assert "Пираты «Чёрной лагуны»" in caption
    assert "Black Lagoon" in caption
    assert "12 эп." in caption
    assert "23 мин/эп." in caption
    assert "История &amp; приключения." in caption
    assert "🎥 Режиссёр: <b>Сунао Катабути</b>" in caption
    assert "🏢 Студия: <b>Madhouse</b>" in caption
    assert len(caption) < 1024

    keyboard = anime_keyboard(anime, "action")
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def _stored_media(external_id: str, media_type: str) -> StoredMedia:
    return StoredMedia(
        external_id=external_id,
        media_type=media_type,
        title=f"Title {external_id}",
        year=2006,
        poster_url=None,
        watched=False,
        skipped=False,
        favorite=True,
        watchlist=False,
    )


def test_anime_collection_page_has_description_buttons() -> None:
    from kinotyk.ui import anime_details_keyboard, collection_page_keyboard

    media = [
        _stored_media(external_id, "anime")
        for external_id in ("889", "1", "16498", "1535", "22319")
    ]
    keyboard = collection_page_keyboard("anime", "favorite", 8, 13, 8, media)
    buttons = [button for row in keyboard["inline_keyboard"] for button in row]

    item_buttons = [button for button in buttons if button["callback_data"].startswith("anv:")]
    assert [button["text"] for button in item_buttons] == ["9", "10", "11", "12", "13"]
    assert item_buttons[0]["callback_data"] == "anv:889:favorite:8"
    assert item_buttons[1]["callback_data"] == "anv:1:favorite:8"
    assert all(len(value["callback_data"].encode("utf-8")) <= 64 for value in item_buttons)

    details = anime_details_keyboard("889", "favorite", 8)
    rows = details["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "col:anime:favorite:8"
    assert rows[1][0]["callback_data"] == "rmv:anime:889:favorite:8"
    assert "Избранное" in rows[1][0]["text"]


def test_movie_collection_page_has_view_and_remove_buttons() -> None:
    from kinotyk.ui import collection_page_keyboard, movie_details_keyboard

    media = [_stored_media("tt1375666", "movie"), _stored_media("tt0133093", "movie")]
    keyboard = collection_page_keyboard("movie", "watchlist", 0, 2, 8, media)
    buttons = [button for row in keyboard["inline_keyboard"] for button in row]

    item_buttons = [button for button in buttons if button["callback_data"].startswith("mvv:")]
    assert [button["callback_data"] for button in item_buttons] == [
        "mvv:tt1375666:watchlist:0",
        "mvv:tt0133093:watchlist:0",
    ]
    assert all(len(value["callback_data"].encode("utf-8")) <= 64 for value in item_buttons)

    details = movie_details_keyboard("tt1375666", "watchlist", 0)
    rows = details["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "col:movie:watchlist:0"
    assert rows[1][0]["callback_data"] == "rmv:movie:tt1375666:watchlist:0"
    assert "Посмотреть позже" in rows[1][0]["text"]


def test_anime_collection_page_without_items_has_no_description_buttons() -> None:
    from kinotyk.ui import collection_page_keyboard

    keyboard = collection_page_keyboard("anime", "watchlist", 0, 0, 8, [])
    buttons = [button for row in keyboard["inline_keyboard"] for button in row]
    assert all(not button["callback_data"].startswith("anv:") for button in buttons)


def test_search_keyboards_and_results() -> None:
    from kinotyk.domain import Anime, Movie
    from kinotyk.ui import (
        anime_search_results_text,
        movie_search_results_text,
        search_anime_keyboard,
        search_media_keyboard,
        search_movie_keyboard,
        search_results_keyboard,
    )

    movie = Movie(
        imdb_id="tt1375666",
        title="Начало & <Основное>",
        original_title="Inception",
        overview="Text",
        poster_url=None,
        rating=8.8,
        year=2010,
        genres=("Sci-Fi",),
    )
    text = movie_search_results_text("нача<", [movie])
    assert "нача&lt;" in text
    assert "Начало &amp; &lt;Основное&gt;" in text
    assert "⭐ 8.8" in text

    anime = Anime(
        shikimori_id=2167,
        title="Кланнад",
        original_title="Clannad",
        overview="Text",
        poster_url=None,
        score=8.2,
        year=2007,
        genres=("Драма",),
    )
    anime_text = anime_search_results_text("кланнад", [anime])
    assert "Кланнад</b> (2007) · ⭐ 8.20" in anime_text

    keyboard = search_results_keyboard("anime", ["2167", "6351"])
    flat = [button for row in keyboard["inline_keyboard"] for button in row]
    assert flat[0]["callback_data"] == "sav:2167"
    assert flat[1]["callback_data"] == "sav:6351"
    assert flat[1]["text"] == "2"

    movie_keyboard = search_results_keyboard("movie", ["tt1375666"])
    assert movie_keyboard["inline_keyboard"][0][0]["callback_data"] == "smv:tt1375666"

    card = search_movie_keyboard(movie)
    callbacks = [button["callback_data"] for row in card["inline_keyboard"] for button in row]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)
    assert all(not value.endswith(":n:search") for value in callbacks)
    assert "mv:f:tt1375666:search" in callbacks

    anime_card = search_anime_keyboard(anime)
    anime_callbacks = [
        button["callback_data"] for row in anime_card["inline_keyboard"] for button in row
    ]
    assert "an:w:2167:search" in anime_callbacks

    media_kb = search_media_keyboard()
    media_callbacks = [
        button["callback_data"] for row in media_kb["inline_keyboard"] for button in row
    ]
    assert media_callbacks == ["search:movie", "search:anime", "nav:main"]
