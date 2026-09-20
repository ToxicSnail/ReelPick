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
