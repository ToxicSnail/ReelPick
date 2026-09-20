from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Genre:
    key: str
    cinemeta_name: str | None
    label: str


GENRES: tuple[Genre, ...] = (
    Genre("action", "Action", "💥 Боевик"),
    Genre("adventure", "Adventure", "🧭 Приключения"),
    Genre("animation", "Animation", "🎨 Мультфильм"),
    Genre("comedy", "Comedy", "😂 Комедия"),
    Genre("crime", "Crime", "🚔 Криминал"),
    Genre("drama", "Drama", "🎭 Драма"),
    Genre("family", "Family", "👨‍👩‍👧 Семейный"),
    Genre("fantasy", "Fantasy", "🧙 Фэнтези"),
    Genre("history", "History", "📜 Исторический"),
    Genre("horror", "Horror", "😱 Ужасы"),
    Genre("mystery", "Mystery", "🕵 Детектив"),
    Genre("romance", "Romance", "💕 Мелодрама"),
    Genre("sci_fi", "Sci-Fi", "🚀 Фантастика"),
    Genre("thriller", "Thriller", "🔪 Триллер"),
    Genre("war", "War", "⚔️ Военный"),
    Genre("western", "Western", "🤠 Вестерн"),
    Genre("any", None, "🎲 Что угодно"),
)

GENRE_BY_KEY = {genre.key: genre for genre in GENRES}

GENRE_RU = {
    "Action": "Боевик",
    "Adventure": "Приключения",
    "Animation": "Мультфильм",
    "Biography": "Биография",
    "Comedy": "Комедия",
    "Crime": "Криминал",
    "Documentary": "Документальный",
    "Drama": "Драма",
    "Family": "Семейный",
    "Fantasy": "Фэнтези",
    "History": "Исторический",
    "Horror": "Ужасы",
    "Mystery": "Детектив",
    "Romance": "Мелодрама",
    "Sci-Fi": "Фантастика",
    "Sport": "Спорт",
    "Thriller": "Триллер",
    "War": "Военный",
    "Western": "Вестерн",
}


def translate_genres(genres: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(GENRE_RU.get(genre, genre) for genre in genres)
