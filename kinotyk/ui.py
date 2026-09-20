from __future__ import annotations

import html

from kinotyk.anime_genres import ANIME_GENRES
from kinotyk.domain import Anime, AnimeCandidate, Movie, MovieCandidate, StoredMedia
from kinotyk.genres import GENRES, translate_genres

COLLECTION_LABELS = {
    "watched": "✅ Просмотренные",
    "favorite": "❤️ Избранное",
    "watchlist": "📌 Посмотреть позже",
    "skipped": "🙅 Скрытые",
}
MEDIA_LABELS = {"movie": "🎞 Фильмы", "anime": "🍥 Аниме"}
ANIME_KIND_RU = {
    "tv": "TV-сериал",
    "movie": "Фильм",
    "ova": "OVA",
    "ona": "ONA",
    "special": "Спецвыпуск",
    "music": "Клип",
    "tv_special": "TV-спецвыпуск",
}


def _button(text: str, callback_data: str) -> dict[str, str]:
    return {"text": text, "callback_data": callback_data}


def main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [_button("🎞 Найти фильм", "menu:movie")],
            [_button("🍥 Найти аниме", "menu:anime")],
            [_button("🔍 Поиск", "menu:search")],
            [_button("📚 Моя коллекция", "menu:collection")],
        ]
    }


def search_media_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [_button("🔍 Фильмы", "search:movie"), _button("🔍 Аниме", "search:anime")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def search_cancel_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [_button("⛔ Отмена", "search:cancel")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def search_results_keyboard(media_type: str, external_ids: list[str]) -> dict:
    prefix = "smv" if media_type == "movie" else "sav"
    rows: list[list[dict[str, str]]] = []
    for start in range(0, len(external_ids), 4):
        rows.append(
            [
                _button(str(index + 1), f"{prefix}:{external_id}")
                for index, external_id in enumerate(
                    external_ids[start : start + 4], start=start
                )
            ]
        )
    rows.append([_button("🔍 Новый поиск", "menu:search")])
    rows.append([_button("🏠 Главное меню", "nav:main")])
    return {"inline_keyboard": rows}


def genres_keyboard() -> dict:
    rows: list[list[dict[str, str]]] = []
    regular = [genre for genre in GENRES if genre.key != "any"]
    for index in range(0, len(regular), 2):
        rows.append(
            [
                _button(genre.label, f"genre:movie:{genre.key}")
                for genre in regular[index : index + 2]
            ]
        )
    rows.append([_button("🎲 Что угодно", "genre:movie:any")])
    rows.append([_button("🏠 Главное меню", "nav:main")])
    return {"inline_keyboard": rows}


def anime_genres_keyboard() -> dict:
    rows: list[list[dict[str, str]]] = []
    regular = [genre for genre in ANIME_GENRES if genre.key != "any"]
    for index in range(0, len(regular), 2):
        rows.append(
            [
                _button(genre.label, f"genre:anime:{genre.key}")
                for genre in regular[index : index + 2]
            ]
        )
    rows.append([_button("🎲 Что угодно", "genre:anime:any")])
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
            [_button("🎭 Сменить жанр", "nav:movie_genres")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def anime_keyboard(anime: Anime, genre_key: str) -> dict:
    anime_id = anime.shikimori_id
    return {
        "inline_keyboard": [
            [_button("✅ Уже смотрел", f"an:w:{anime_id}:{genre_key}")],
            [
                _button("❤️ В избранное", f"an:f:{anime_id}:{genre_key}"),
                _button("📌 На потом", f"an:l:{anime_id}:{genre_key}"),
            ],
            [
                _button("🙅 Не интересно", f"an:s:{anime_id}:{genre_key}"),
                _button("🎲 Другое", f"an:n:{anime_id}:{genre_key}"),
            ],
            [_button("🍥 Сменить жанр", "nav:anime_genres")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def collection_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [_button("🎞 Фильмы", "media:movie")],
            [_button("🍥 Аниме", "media:anime")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def media_collection_keyboard(media_type: str) -> dict:
    return {
        "inline_keyboard": [
            [_button(COLLECTION_LABELS["watched"], f"col:{media_type}:watched:0")],
            [_button(COLLECTION_LABELS["favorite"], f"col:{media_type}:favorite:0")],
            [_button(COLLECTION_LABELS["watchlist"], f"col:{media_type}:watchlist:0")],
            [_button("📚 Вся коллекция", "menu:collection")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def collection_page_keyboard(
    media_type: str,
    collection: str,
    offset: int,
    total: int,
    page_size: int = 8,
    media: list[StoredMedia] | None = None,
) -> dict:
    nav: list[dict[str, str]] = []
    if offset > 0:
        nav.append(
            _button(
                "⬅️ Назад",
                f"col:{media_type}:{collection}:{max(0, offset - page_size)}",
            )
        )
    if offset + page_size < total:
        nav.append(
            _button("Вперёд ➡️", f"col:{media_type}:{collection}:{offset + page_size}")
        )

    rows: list[list[dict[str, str]]] = []
    if media:
        prefix = "anv" if media_type == "anime" else "mvv"
        for start in range(0, len(media), 4):
            rows.append(
                [
                    _button(
                        str(offset + index + 1),
                        f"{prefix}:{item.external_id}:{collection}:{offset}",
                    )
                    for index, item in enumerate(media[start : start + 4], start=start)
                ]
            )
    if nav:
        rows.append(nav)
    rows.append([_button(MEDIA_LABELS[media_type], f"media:{media_type}")])
    rows.append([_button("📚 Вся коллекция", "menu:collection")])
    rows.append([_button("🏠 Главное меню", "nav:main")])
    return {"inline_keyboard": rows}


def anime_details_keyboard(media_id: str, collection: str, offset: int) -> dict:
    return {
        "inline_keyboard": [
            [_button("⬅️ К списку", f"col:anime:{collection}:{offset}")],
            [
                _button(
                    f"🗑 Убрать из «{COLLECTION_LABELS[collection]}»",
                    f"rmv:anime:{media_id}:{collection}:{offset}",
                )
            ],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def movie_details_keyboard(media_id: str, collection: str, offset: int) -> dict:
    return {
        "inline_keyboard": [
            [_button("⬅️ К списку", f"col:movie:{collection}:{offset}")],
            [
                _button(
                    f"🗑 Убрать из «{COLLECTION_LABELS[collection]}»",
                    f"rmv:movie:{media_id}:{collection}:{offset}",
                )
            ],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def search_movie_keyboard(movie: Movie) -> dict:
    movie_id = movie.imdb_id
    return {
        "inline_keyboard": [
            [_button("✅ Уже смотрел", f"mv:w:{movie_id}:search")],
            [
                _button("❤️ В избранное", f"mv:f:{movie_id}:search"),
                _button("📌 На потом", f"mv:l:{movie_id}:search"),
            ],
            [_button("🙅 Не интересно", f"mv:s:{movie_id}:search")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def search_anime_keyboard(anime: Anime) -> dict:
    anime_id = anime.shikimori_id
    return {
        "inline_keyboard": [
            [_button("✅ Уже смотрел", f"an:w:{anime_id}:search")],
            [
                _button("❤️ В избранное", f"an:f:{anime_id}:search"),
                _button("📌 На потом", f"an:l:{anime_id}:search"),
            ],
            [_button("🙅 Не интересно", f"an:s:{anime_id}:search")],
            [_button("🏠 Главное меню", "nav:main")],
        ]
    }


def main_menu_text(first_name: str | None = None) -> str:
    greeting = f", {html.escape(first_name)}" if first_name else ""
    return (
        f"🎬 <b>Кинотык</b>{greeting}\n\n"
        "Выбери, что ищем: фильм или аниме. Я покажу рейтинг, постер и короткое "
        "описание, а просмотренное запомню отдельно для твоего аккаунта."
    )


def genres_text() -> str:
    return "🎭 <b>Какой фильм сегодня смотрим?</b>\n\nВыбери жанр:"


def anime_genres_text() -> str:
    return "🍥 <b>Какое аниме сегодня смотрим?</b>\n\nВыбери жанр или тему:"


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
    if movie.director:
        lines.append(f"🎥 Режиссёр: <b>{html.escape(movie.director)}</b>")
    if movie.studio:
        lines.append(f"🏢 Студия: <b>{html.escape(movie.studio)}</b>")
    if movie.genres:
        genres = " · ".join(html.escape(item) for item in translate_genres(movie.genres)[:4])
        lines.append(f"🎭 {genres}")

    overview = movie.overview.strip() or "Краткое описание пока не найдено."
    lines.extend(["", "<b>Без спойлеров:</b>", html.escape(overview)])
    return "\n".join(lines)


def anime_caption(anime: Anime) -> str:
    title = html.escape(anime.title)
    original = html.escape(anime.original_title)
    lines = [f"🍥 <b>{title}</b>"]
    if anime.title.casefold() != anime.original_title.casefold():
        lines.append(f"<i>{original}</i>")

    rating = f"{anime.score:.2f} / 10" if anime.score is not None else "нет данных"
    lines.extend(["", f"⭐ Рейтинг: <b>{rating}</b>"])

    details: list[str] = []
    if anime.kind:
        details.append(ANIME_KIND_RU.get(anime.kind, anime.kind.upper()))
    if anime.episodes:
        details.append(f"{anime.episodes} эп.")
    if anime.duration:
        details.append(f"{anime.duration} мин/эп.")
    if details:
        lines.append("📺 " + " · ".join(html.escape(item) for item in details))
    if anime.year:
        lines.append(f"📅 {anime.year}")
    if anime.director:
        lines.append(f"🎥 Режиссёр: <b>{html.escape(anime.director)}</b>")
    if anime.studio:
        lines.append(f"🏢 Студия: <b>{html.escape(anime.studio)}</b>")
    if anime.genres:
        lines.append("🎭 " + " · ".join(html.escape(item) for item in anime.genres[:5]))

    overview = anime.overview.strip() or "Краткое русское описание пока не найдено."
    lines.extend(["", "<b>Без спойлеров:</b>", html.escape(overview)])
    return "\n".join(lines)


def collection_summary_text(
    movie_stats: dict[str, int],
    anime_stats: dict[str, int],
) -> str:
    return (
        "📚 <b>Моя коллекция</b>\n\n"
        "🎞 <b>Фильмы</b>\n"
        f"✅ Просмотрено: <b>{movie_stats.get('watched', 0)}</b> · "
        f"❤️ {movie_stats.get('favorite', 0)} · 📌 {movie_stats.get('watchlist', 0)}\n\n"
        "🍥 <b>Аниме</b>\n"
        f"✅ Просмотрено: <b>{anime_stats.get('watched', 0)}</b> · "
        f"❤️ {anime_stats.get('favorite', 0)} · 📌 {anime_stats.get('watchlist', 0)}"
    )


def media_collection_text(media_type: str, stats: dict[str, int]) -> str:
    label = MEDIA_LABELS[media_type]
    return (
        f"{label}\n\n"
        f"✅ Просмотрено: <b>{stats.get('watched', 0)}</b>\n"
        f"❤️ Избранное: <b>{stats.get('favorite', 0)}</b>\n"
        f"📌 Посмотреть позже: <b>{stats.get('watchlist', 0)}</b>\n"
        f"🙅 Скрыто: <b>{stats.get('skipped', 0)}</b>"
    )


def collection_page_text(
    media_type: str,
    collection: str,
    media: list[StoredMedia],
    *,
    total: int,
    offset: int,
) -> str:
    label = COLLECTION_LABELS.get(collection, "Коллекция")
    type_label = MEDIA_LABELS.get(media_type, media_type)
    if not media:
        return f"{type_label} · {label}\n\nЗдесь пока пусто."

    lines = [f"{type_label} · {label} · <b>{total}</b>", ""]
    for index, item in enumerate(media, start=offset + 1):
        year = f" ({item.year})" if item.year else ""
        lines.append(f"{index}. <b>{html.escape(item.title)}</b>{year}")
    return "\n".join(lines)


def search_media_text() -> str:
    return "🔍 <b>Что будем искать?</b>\n\nВыбери тип:"


def search_prompt_text(media_type: str) -> str:
    label = MEDIA_LABELS[media_type]
    return (
        f"{label} · 🔍 Поиск\n\n"
        "Напиши название одним сообщением — я покажу подходящие варианты."
    )


def search_no_results_text(media_type: str, query: str) -> str:
    label = MEDIA_LABELS[media_type]
    return (
        f"{label} · 🔍 Поиск\n\n"
        f"По запросу «{html.escape(query)}» ничего не нашлось.\n\n"
        "Попробуй изменить запрос."
    )


def movie_search_results_text(query: str, items: list[MovieCandidate]) -> str:
    lines = [f"🎞 Поиск фильмов · «{html.escape(query)}» · <b>{len(items)}</b>", ""]
    for index, item in enumerate(items, start=1):
        year = f" ({item.year})" if item.year else ""
        rating = f" · ⭐ {item.rating:.1f}" if item.rating is not None else ""
        lines.append(f"{index}. <b>{html.escape(item.title)}</b>{year}{rating}")
    return "\n".join(lines)


def anime_search_results_text(query: str, items: list[AnimeCandidate]) -> str:
    lines = [f"🍥 Поиск аниме · «{html.escape(query)}» · <b>{len(items)}</b>", ""]
    for index, item in enumerate(items, start=1):
        year = f" ({item.year})" if item.year else ""
        score = f" · ⭐ {item.score:.2f}" if item.score is not None else ""
        lines.append(f"{index}. <b>{html.escape(item.title)}</b>{year}{score}")
    return "\n".join(lines)


def global_stats_text(stats: dict[str, int]) -> str:
    return (
        "📊 <b>Статистика Кинотыка</b>\n\n"
        f"👥 Пользователей: <b>{stats.get('users', 0)}</b>\n"
        f"🎬 Фильмов сохранено: <b>{stats.get('movies', 0)}</b>\n"
        f"🍥 Аниме сохранено: <b>{stats.get('anime', 0)}</b>\n"
        f"✅ Просмотрено: <b>{stats.get('watched', 0)}</b>\n"
        f"❤️ Избранное: <b>{stats.get('favorite', 0)}</b>"
    )


def help_text() -> str:
    return (
        "ℹ️ <b>Как пользоваться Кинотыком</b>\n\n"
        "1. Выбери «Найти фильм» или «Найти аниме».\n"
        "2. Выбери жанр.\n"
        "3. «Уже смотрел» сохранит тайтл и покажет следующий.\n"
        "4. «Не интересно» скроет его из рекомендаций.\n"
        "5. «На потом» и «Избранное» хранятся отдельно для каждого пользователя.\n\n"
        "Фильмы: Cinemeta/IMDb + русская Wikipedia. Аниме: публичный каталог Shikimori."
    )
