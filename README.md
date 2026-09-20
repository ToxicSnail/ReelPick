# Кинотык 1.2.0

Русскоязычный Telegram-бот для подбора **фильмов и аниме** с персональной историей просмотра.

## Источники

- Фильмы: Cinemeta/IMDb; русские названия и описания — Wikidata + ru.wikipedia.
- Аниме: публичные read-only endpoints Shikimori (`/api/animes`, `/api/animes/{id}`, `/api/genres`).
- Никаких API-ключей для контентных источников не требуется.
- Нужен только `BOT_TOKEN` Telegram-бота.

## Возможности

- отдельные режимы `🎞 Фильмы` и `🍥 Аниме`;
- русские жанры и русские карточки;
- рейтинг, постер, год, описание;
- для аниме: тип, число эпизодов, длительность серии;
- `✅ Уже смотрел`, `❤️ Избранное`, `📌 На потом`, `🙅 Не интересно`;
- отдельная история фильмов и аниме для каждого Telegram-пользователя;
- автоматическая миграция старой таблицы `user_movies` из версии 1.1 в `user_media`;
- SQLite хранится в `./data/kinotyk.sqlite3`.

## Запуск

```bash
cp .env.example .env
nano .env
```

Укажи:

```env
BOT_TOKEN=1234567890:your_real_token
```

### Docker Compose v2

```bash
docker compose up --build -d
docker compose logs -f
```

### Старый docker-compose v1 (включая 1.25 на Ubuntu 20.04)

`docker-compose.yml` содержит `version: "3.7"`, поэтому совместим с установленным у тебя `docker-compose` v1:

```bash
docker-compose up --build -d
docker-compose logs -f
```

## Обновление с 1.1

Не удаляй каталог `data/`. Просто замени код и пересобери контейнер:

```bash
docker-compose down
docker-compose up --build -d
docker-compose logs -f
```

При первом запуске новая таблица `user_media` создастся автоматически, а старые записи фильмов из `user_movies` будут перенесены как `media_type='movie'`.

## Команды

- `/start` — главное меню
- `/movie` — подбор фильма
- `/anime` — подбор аниме
- `/collection` — коллекция
- `/help` — помощь

## Настройки

Смотри `.env.example`. Основные параметры:

```env
MIN_IMDB_RATING=6.0
MIN_ANIME_RATING=6.0
CINEMETA_SKIPS=0,100,200,300
ANIME_PAGES=1,2,3,4,5
```

## Проверки

Результаты сборки зафиксированы в `CHECKS.md`.
