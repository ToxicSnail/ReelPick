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
