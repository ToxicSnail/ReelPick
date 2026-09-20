from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnimeGenre:
    key: str
    shikimori_name: str | None
    label: str


ANIME_GENRES: tuple[AnimeGenre, ...] = (
    AnimeGenre("action", "Action", "⚔️ Экшен"),
    AnimeGenre("adventure", "Adventure", "🧭 Приключения"),
    AnimeGenre("comedy", "Comedy", "😂 Комедия"),
    AnimeGenre("drama", "Drama", "🎭 Драма"),
    AnimeGenre("fantasy", "Fantasy", "🧙 Фэнтези"),
    AnimeGenre("romance", "Romance", "💕 Романтика"),
    AnimeGenre("sci_fi", "Sci-Fi", "🚀 Фантастика"),
    AnimeGenre("mystery", "Mystery", "🕵️ Тайна"),
    AnimeGenre("sports", "Sports", "🏆 Спорт"),
    AnimeGenre("suspense", "Suspense", "🔪 Триллер"),
    AnimeGenre("psychological", "Psychological", "🧠 Психология"),
    AnimeGenre("school", "School", "🏫 Школа"),
    AnimeGenre("supernatural", "Supernatural", "👻 Сверхъестественное"),
    AnimeGenre("any", None, "🎲 Что угодно"),
)

ANIME_GENRE_BY_KEY = {genre.key: genre for genre in ANIME_GENRES}
