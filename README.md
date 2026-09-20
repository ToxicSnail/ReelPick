# Кинотык

Версия: **1.1.0**

Русскоязычный Telegram-бот для выбора фильма по жанру.

Бот показывает постер, IMDb-рейтинг, год, жанры и короткое вводное описание. Пользователь
может отметить фильм как просмотренный, скрыть его, добавить в избранное или в список
«На потом». История хранится в SQLite отдельно по `telegram_id`.

## Внешние источники

Для фильмов не нужны аккаунты, API keys или платные планы:

- **Cinemeta** (`v3-cinemeta.strem.io`) — каталог, IMDb ID, рейтинг, постер, жанры,
  исходное описание;
- **Wikidata Action API** — поиск сущности с обязательной проверкой точного IMDb ID;
- **Русская Wikipedia Action API** — русское название и вводное описание.

Единственный обязательный секрет — Telegram Bot Token от `@BotFather`.

> Cinemeta — внешний сервис Stremio без гарантированного SLA. Если он временно недоступен,
> бот покажет пользователю понятную ошибку/предложит сменить жанр, а не traceback.

## Возможности

- `/start` — главное меню;
- `/movie` — выбор жанра;
- `/collection` — личная коллекция;
- `/help` — помощь;
- русское меню, русские названия и русские краткие описания;
- если Wikidata недоступна, бот независимо пробует прямой поиск по ru.wikipedia;
- английский synopsis Cinemeta не показывается в русской карточке как fallback;
- фильтрация по минимальному IMDb-рейтингу;
- просмотренные, скрытые и отложенные фильмы исключаются из рекомендаций;
- в рамках текущего процесса один и тот же фильм не повторяется при нажатии «Другой»;
- SQLite с WAL;
- long polling напрямую через Telegram Bot API;
- никаких TMDB/OMDb ключей.

## Быстрый запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\\Scripts\\activate       # Windows PowerShell

pip install -r requirements.txt
cp .env.example .env
```

В `.env` достаточно заменить:

```env
BOT_TOKEN=1234567890:ваш_токен_от_BotFather
```

Запуск:

```bash
python -m kinotyk
```

Либо после установки проекта:

```bash
pip install -e .
kinotyk
```

## Docker

```bash
cp .env.example .env
# вписать BOT_TOKEN

docker compose up --build -d
docker compose logs -f
```

SQLite лежит в `./data/kinotyk.sqlite3` и пробрасывается volume в контейнер.

## Конфигурация

```env
BOT_TOKEN=...
DATABASE_PATH=./data/kinotyk.sqlite3
MIN_IMDB_RATING=6.0
CINEMETA_SKIPS=0,100,200,300
HTTP_TIMEOUT_SECONDS=12
TELEGRAM_POLL_TIMEOUT_SECONDS=30
MAX_OVERVIEW_CHARS=520
LOG_LEVEL=INFO
```

URL источников вынесены в env, чтобы их можно было заменить без изменения кода.

## Архитектура

```text
Telegram user
     │
     ▼
Telegram Bot API
     │
     ▼
 KinotykApp
     │
     ├──────────────► Database (SQLite)
     │                    │
     │                    └─ users / user_movies
     │
     ▼
RecommendationService
     │
     ├──────────────► CinemetaClient
     │                    │
     │                    └─ catalog + movie metadata
     │
     └──────────────► RussianLocalizer
                          │
                          ├─ Wikidata Action API
                          │    └─ title search -> exact IMDb P345 check
                          └─ ru.wikipedia search + intro extract
```

Telegram-фреймворк намеренно не используется: Bot API вызывается через `httpx.AsyncClient`.
Это оставляет runtime-зависимость одну (`httpx`) и не блокирует event loop синхронным
`requests.get()`.

## База данных

Одна SQLite база, но коллекции логически изолированы по Telegram ID:

```text
users
└── telegram_id (PK)

user_movies
├── telegram_id (PK part)
├── imdb_id      (PK part)
├── title
├── year
├── poster_url
├── watched
├── skipped
├── favorite
└── watchlist
```

Отдельная SQLite база на каждого пользователя не создаётся: это усложнило бы миграции,
бэкапы и конкурентный доступ без практической пользы.

## Проверки

Быстрые offline-проверки, не требующие доступа к внешним API:

```bash
python tools/lint.py
python -m compileall -q kinotyk tests
pytest -q
```

Для Ruff:

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
```

HTTP-тесты используют `httpx.MockTransport`, поэтому тестовый прогон не зависит от
доступности Cinemeta, Telegram или Wikipedia.

## Что происходит при выборе жанра

```text
genre:horror
    │
    ▼
получить excluded IDs из SQLite
    │
    ▼
Cinemeta catalog(movie/top, Horror)
    │
    ▼
убрать watched / skipped / watchlist / session_seen
    │
    ▼
проверить IMDb rating
    │
    ▼
Cinemeta movie metadata
    │
    ▼
Wikidata: original title -> candidate items -> exact IMDb ID check
    │
    ▼
ru.wikipedia: только intro/extract
    │
    ▼
Telegram movie card
```

Wikipedia берётся только из вводной части статьи (`exintro=1`), а не из раздела
«Сюжет», чтобы уменьшить вероятность спойлеров. Из интро выбираются короткие
предложения, больше похожие на описание завязки. Если Wikidata временно недоступна,
локализатор всё равно выполняет прямой поиск по русской Wikipedia. Если русское
описание получить не удалось, карточка показывает русское сообщение-заглушку, а не
английский synopsis Cinemeta.

## Ограничения

- внешний Cinemeta endpoint может меняться или быть временно недоступен;
- IMDb vote count Cinemeta не отдаёт в используемом metadata-формате, поэтому бот
  показывает рейтинг без количества голосов;
- русская локализация best-effort: не у каждого фильма есть статья в ru.wikipedia;
- после полного перезапуска процесса фильмы, которые пользователь просто перелистывал
  кнопкой «Другой», могут когда-нибудь встретиться снова; просмотренные/скрытые/отложенные
  сохраняются постоянно.
