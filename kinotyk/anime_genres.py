from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnimeGenre:
    key: str
    genre_v2_id: int | None
    label: str


# IDs are explicit because Shikimori's /api/genres still serves the legacy
# taxonomy (no "Suspense") while /api/animes expects genre_v2 IDs.
ANIME_GENRES: tuple[AnimeGenre, ...] = (
    AnimeGenre("action", 1, "⚔️ Экшен"),
    AnimeGenre("adventure", 2, "🧭 Приключения"),
    AnimeGenre("comedy", 4, "😂 Комедия"),
    AnimeGenre("drama", 8, "🎭 Драма"),
    AnimeGenre("fantasy", 10, "🧙 Фэнтези"),
    AnimeGenre("romance", 22, "💕 Романтика"),
    AnimeGenre("sci_fi", 24, "🚀 Фантастика"),
    AnimeGenre("mystery", 7, "🕵️ Тайна"),
    AnimeGenre("sports", 30, "🏆 Спорт"),
    AnimeGenre("suspense", 117, "🔪 Триллер"),
    AnimeGenre("psychological", 40, "🧠 Психология"),
    AnimeGenre("school", 23, "🏫 Школа"),
    AnimeGenre("supernatural", 37, "👻 Сверхъестественное"),
    AnimeGenre("any", None, "🎲 Что угодно"),
)

ANIME_GENRE_BY_KEY = {genre.key: genre for genre in ANIME_GENRES}
