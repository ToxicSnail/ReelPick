# Checks — Kinotyk 1.2.0

Выполнено перед упаковкой:

```text
python -m compileall -q kinotyk tests
PASS

python tools/lint.py
Lint OK: 28 Python files checked

PYTHONPATH=. pytest -q
.................                                                        [100%]
17 passed
```

Дополнительно проверяется тестами:

- парсинг Cinemeta;
- русская локализация фильмов через Wikidata/ru.wikipedia;
- парсинг публичного REST API Shikimori;
- фильтрация просмотренных аниме;
- раздельная коллекция фильмов/аниме;
- миграция старой `user_movies` в новую `user_media`;
- Telegram payloads и лимит `callback_data <= 64` байт;
- русские карточки фильмов и аниме.

`ruff` указан в dev-зависимостях, но в среде сборки бинарник не установлен, а загрузка из PyPI недоступна по DNS. Поэтому фактически прогнан встроенный статический линтер `tools/lint.py`, compileall и полный pytest suite.
