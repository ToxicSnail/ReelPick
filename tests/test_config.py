from pathlib import Path

from kinotyk.config import Settings


def test_settings_load_from_env_file(tmp_path: Path, monkeypatch) -> None:
    for name in [
        "BOT_TOKEN",
        "DATABASE_PATH",
        "MIN_IMDB_RATING",
        "CINEMETA_SKIPS",
        "WIKIDATA_API_URL",
    ]:
        monkeypatch.delenv(name, raising=False)

    env = tmp_path / ".env"
    env.write_text(
        "BOT_TOKEN=123:test\n"
        "DATABASE_PATH=./custom.sqlite3\n"
        "MIN_IMDB_RATING=6.5\n"
        "CINEMETA_SKIPS=0,50,100\n"
        "WIKIDATA_API_URL=https://www.wikidata.org/w/api.php\n",
        encoding="utf-8",
    )
    settings = Settings.load(env)

    assert settings.bot_token == "123:test"
    assert settings.database_path == Path("./custom.sqlite3")
    assert settings.min_imdb_rating == 6.5
    assert settings.cinemeta_skips == (0, 50, 100)
    assert settings.wikidata_api_url == "https://www.wikidata.org/w/api.php"


def test_admin_ids_parsing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    monkeypatch.setenv("BOT_TOKEN", "123:test")
    env = tmp_path / "empty.env"

    assert Settings.load(env).admin_ids == ()

    monkeypatch.setenv("ADMIN_IDS", " 42 , 42, 100 ")
    assert Settings.load(env).admin_ids == (42, 100)

    monkeypatch.setenv("ADMIN_IDS", "abc")
    try:
        Settings.load(env)
    except ValueError as exc:
        assert "ADMIN_IDS" in str(exc)
    else:
        raise AssertionError("ValueError expected for non-integer admin id")

    monkeypatch.setenv("ADMIN_IDS", "-5")
    try:
        Settings.load(env)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("ValueError expected for negative admin id")
