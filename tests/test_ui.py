from kinotyk.domain import Movie
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
    )
    caption = movie_caption(movie)

    assert "Начало &lt;2010&gt;" in caption
    assert "IMDb" in caption
    assert "Фантастика · Триллер" in caption
    assert "Сон &amp; реальность." in caption
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
    )
    caption = anime_caption(anime)
    assert "Пираты «Чёрной лагуны»" in caption
    assert "Black Lagoon" in caption
    assert "12 эп." in caption
    assert "23 мин/эп." in caption
    assert "История &amp; приключения." in caption
    assert len(caption) < 1024

    keyboard = anime_keyboard(anime, "action")
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)
