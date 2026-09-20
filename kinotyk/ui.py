from __future__ import annotations

import html

from kinotyk.domain import Movie, StoredMovie
from kinotyk.genres import GENRES, GENRE_BY_KEY, translate_genres

COLLECTION_LABELS = {
    "watched": "✅ Просмотренные",
    "favorite": "❤️ Избранное",
    "watchlist": "📌 Посмотреть позже",
    "skipped": "🙅 Скрытые",
}


def _button(text: str, callback_data: str) -> dict[str, str]:
    return {"text": text, "callback_data": callback_data}


def main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [_button("🎲 Найти фильм", "menu:find")],
            [_button("📚 Моя коллекция", "menu:collection")],
        ]
    }


def genres_keyboard() -> dict:
    rows: list[list[dict[str, str]]] = []
    regular = [genre for genre in GENRES if genre.key != "any"]
    for index in range(0, len(regular), 2):
        rows.append(
            [_button(genre.label, f"genre:{genre.key}") for genre in regular[index : index + 2]]
        )
    rows.append([_button("🎲 Что угодно", "genre:any")])
    rows.append([_button("🏠 Главное меню", "nav:main")])
    return {"inline_keyboard": rows}


def movie_keyboard(movie: Movie, genre_key: str) -> dict:
    movie_id = movie.imdb_id
    return {
        "inline_keyboard": [
            [_button("✅ Уже смотрел", f"mv:w:{movie_id}:{genre_key}")],
            [
                _button("❤️ В избранное", f"mv:f:{movie_id}:{genre_key}"),
                _button("📌 На потом", f"mv:l:{movie_id}:{genre_key}"),
            ],
            [
                _button("🙅 Не интересно", f"mv:s:{movie_id}:{genre_key}"),
                _button("🎲 Другой", f"mv:n:{movie_id}:{genre_key}"),
            ],
            [_button("🎭 Сменить жанр", "nav:genres")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def collection_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [_button(COLLECTION_LABELS["watched"], "col:watched:0")],
            [_button(COLLECTION_LABELS["favorite"], "col:favorite:0")],
            [_button(COLLECTION_LABELS["watchlist"], "col:watchlist:0")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def collection_page_keyboard(collection: str, offset: int, total: int, page_size: int = 8) -> dict:
    nav: list[dict[str, str]] = []
    if offset > 0:
        nav.append(_button("⬅️ Назад", f"col:{collection}:{max(0, offset - page_size)}"))
    if offset + page_size < total:
        nav.append(_button("Вперёд ➡️", f"col:{collection}:{offset + page_size}"))

    rows: list[list[dict[str, str]]] = []
    if nav:
        rows.append(nav)
    rows.append([_button("📚 Коллекция", "menu:collection")])
    rows.append([_button("🏠 Главное меню", "nav:main")])
    return {"inline_keyboard": rows}


def main_menu_text(first_name: str | None = None) -> str:
    greeting = f", {html.escape(first_name)}" if first_name else ""
    return (
        f"🎬 <b>Кинотык</b>{greeting}\n\n"
        "Выбери жанр, и я предложу фильм с рейтингом, постером и коротким описанием. "
        "Просмотренные фильмы запоминаются и больше не попадают в рекомендации."
    )


def genres_text() -> str:
    return "🎭 <b>Что сегодня смотрим?</b>\n\nВыбери жанр:"


def movie_caption(movie: Movie) -> str:
    title = html.escape(movie.title)
    original = html.escape(movie.original_title)
    lines = [f"🎬 <b>{title}</b>"]
    if movie.title.casefold() != movie.original_title.casefold():
        lines.append(f"<i>{original}</i>")

    rating = f"{movie.rating:.1f} / 10" if movie.rating is not None else "нет данных"
    lines.append("")
    lines.append(f"⭐ IMDb: <b>{rating}</b>")
    if movie.year:
        lines.append(f"📅 {movie.year}")
    if movie.genres:
        genres = " · ".join(html.escape(item) for item in translate_genres(movie.genres)[:4])
        lines.append(f"🎭 {genres}")

    overview = movie.overview.strip() or "Краткое описание пока не найдено."
    lines.extend(["", "<b>Без спойлеров:</b>", html.escape(overview)])
    return "\n".join(lines)


def collection_summary_text(stats: dict[str, int]) -> str:
    return (
        "📚 <b>Моя коллекция</b>\n\n"
        f"✅ Просмотрено: <b>{stats.get('watched', 0)}</b>\n"
        f"❤️ Избранное: <b>{stats.get('favorite', 0)}</b>\n"
        f"📌 Посмотреть позже: <b>{stats.get('watchlist', 0)}</b>\n"
        f"🙅 Скрыто: <b>{stats.get('skipped', 0)}</b>"
    )


def collection_page_text(
    collection: str,
    movies: list[StoredMovie],
    *,
    total: int,
    offset: int,
) -> str:
    label = COLLECTION_LABELS.get(collection, "Коллекция")
    if not movies:
        return f"{label}\n\nЗдесь пока пусто."

    lines = [f"{label} · <b>{total}</b>", ""]
    for index, movie in enumerate(movies, start=offset + 1):
        year = f" ({movie.year})" if movie.year else ""
        lines.append(f"{index}. <b>{html.escape(movie.title)}</b>{year}")
    return "\n".join(lines)


def help_text() -> str:
    return (
        "ℹ️ <b>Как пользоваться Кинотыком</b>\n\n"
        "1. Нажми «Найти фильм» и выбери жанр.\n"
        "2. «Уже смотрел» сохранит фильм и покажет следующий.\n"
        "3. «Не интересно» скроет фильм из дальнейших рекомендаций.\n"
        "4. «На потом» добавит фильм в список просмотра.\n"
        "5. История хранится отдельно для каждого Telegram-пользователя.\n\n"
        "Данные о фильмах: Cinemeta/IMDb. Русские названия и вводные описания: "
        "Wikidata и русская Wikipedia. API-ключи для этих источников не нужны."
    )
