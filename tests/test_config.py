import pytest

from arvan_bot.config import ConfigError, Settings

TOKEN = "123456789:" + "A" * 35
KEY = "11111111-2222-3333-4444-555555555555"


def env(**extra):
    base = {"TELEGRAM_BOT_TOKEN": TOKEN, "ARVAN_API_KEY": KEY, "ALLOWED_USER_IDS": "42"}
    base.update(extra)
    return base


def test_minimal_ok_and_defaults():
    s = Settings.from_env(env())
    assert s.allowed_user_ids == {42}
    assert s.read_only is False and s.language == "fa" and s.allowed_domains == frozenset()


def test_full_ok():
    s = Settings.from_env(
        env(
            ALLOWED_USER_IDS="1, 2;3",
            ALLOWED_DOMAINS="Example.com, b.ir",
            READ_ONLY="yes",
            BOT_LANGUAGE="EN",
            TELEGRAM_PROXY="socks5://u:secretpw@127.0.0.1:1080",
            ARVAN_API_KEY="Apikey " + KEY,
        )
    )
    assert s.allowed_user_ids == {1, 2, 3}
    assert s.allowed_domains == {"example.com", "b.ir"}
    assert s.read_only and s.language == "en" and s.arvan_api_key == KEY
    assert "secretpw" in s.secrets


def test_repr_hides_secrets():
    text = repr(Settings.from_env(env(TELEGRAM_PROXY="socks5://u:pw12345@h:1")))
    assert TOKEN not in text and KEY not in text and "pw12345" not in text


def test_reports_all_problems_at_once():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "nope",
                "ALLOWED_USER_IDS": "abc,-5",
                "READ_ONLY": "maybe",
                "ARVAN_BASE_URL": "http://x",
            }
        )
    joined = "\n".join(exc.value.problems)
    for needle in (
        "TELEGRAM_BOT_TOKEN",
        "ARVAN_API_KEY is required",
        "ALLOWED_USER_IDS",
        "READ_ONLY",
        "ARVAN_BASE_URL",
    ):
        assert needle in joined


def test_empty_allowlist_is_refused():
    with pytest.raises(ConfigError):
        Settings.from_env(env(ALLOWED_USER_IDS=" , "))
    with pytest.raises(ConfigError):
        Settings.from_env({"TELEGRAM_BOT_TOKEN": TOKEN, "ARVAN_API_KEY": KEY})


def test_secret_from_file(tmp_path):
    f = tmp_path / "token"
    f.write_text(TOKEN + "\n")
    e = env(TELEGRAM_BOT_TOKEN_FILE=str(f))
    e.pop("TELEGRAM_BOT_TOKEN")
    assert Settings.from_env(e).telegram_token == TOKEN
    with pytest.raises(ConfigError):
        Settings.from_env(env(TELEGRAM_BOT_TOKEN_FILE=str(tmp_path / "missing")))
