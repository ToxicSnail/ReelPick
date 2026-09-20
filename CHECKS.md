# Проверки перед упаковкой

Версия сборки: `1.1.0`.

В среде сборки выполнено:

```text
$ python tools/lint.py
Lint OK: 23 Python files checked

$ python -m compileall -q kinotyk tests
# exit code 0

$ PYTHONPATH=. pytest -q
............                                                             [100%]
12 passed
```

Дополнительно добавлены regression-тесты для русской локализации:

- точная проверка IMDb ID через Wikidata P345;
- `The Incredibles` -> `Суперсемейка` + русское описание;
- отказ Wikidata -> независимый fallback на ru.wikipedia;
- при полном отказе локализации английский synopsis не попадает в русскую карточку.

`ruff` в sandbox не установлен, поэтому выполнен встроенный статический линтер проекта
(`tools/lint.py`) и компиляция всех Python-модулей. Docker CLI в sandbox также
отсутствует, поэтому `docker compose build` здесь не запускался. Dockerfile и compose
остались без изменений относительно предыдущей рабочей сборки.

Внешний live-smoke-test Cinemeta/Telegram/Wikimedia из среды сборки невозможен: у
sandbox нет DNS-доступа наружу. HTTP-клиенты покрыты offline-тестами через
`httpx.MockTransport`.
