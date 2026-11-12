"""Configuration, loaded once from the environment and validated up front.

Secrets can be passed as ``NAME`` or as ``NAME_FILE`` (path to a file), which
plays well with Docker and systemd credentials.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from arvan_bot.arvan.client import DEFAULT_BASE_URL
from arvan_bot.validation import ValidationError, validate_domain

LANGUAGES = ("en", "fa")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_TOKEN_RE = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
_API_KEY_RE = re.compile(r"[A-Za-z0-9._~+/=-]{16,200}")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


class ConfigError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("invalid configuration:\n" + "\n".join(f"  - {p}" for p in problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str = field(repr=False)
    arvan_api_key: str = field(repr=False)
    allowed_user_ids: frozenset[int]
    allowed_domains: frozenset[str] = frozenset()
    read_only: bool = False
    language: str = "fa"
    proxy: str | None = field(default=None, repr=False)
    arvan_base_url: str = DEFAULT_BASE_URL
    log_level: str = "INFO"

    @property
    def secrets(self) -> tuple[str, ...]:
        """Values that must never appear in logs."""
        values = [self.telegram_token, self.arvan_api_key]
        if self.proxy:
            values.append(self.proxy)
            parts = urlsplit(self.proxy)
            if parts.password:
                values.append(parts.password)
        return tuple(values)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        problems: list[str] = []

        def read(name: str, *, required: bool = True) -> str | None:
            file_var = env.get(f"{name}_FILE", "").strip()
            if file_var:
                try:
                    return Path(file_var).read_text(encoding="utf-8").strip()
                except OSError as exc:
                    problems.append(f"{name}_FILE: cannot read file ({exc.strerror})")
                    return None
            value = env.get(name, "").strip()
            if not value:
                if required:
                    problems.append(f"{name} is required")
                return None
            return value

        token = read("TELEGRAM_BOT_TOKEN")
        if token and not _TOKEN_RE.fullmatch(token):
            problems.append("TELEGRAM_BOT_TOKEN does not look like a bot token")

        api_key = read("ARVAN_API_KEY")
        if api_key:
            api_key = re.sub(r"^apikey\s+", "", api_key, flags=re.IGNORECASE)
            if not _API_KEY_RE.fullmatch(api_key):
                problems.append("ARVAN_API_KEY has an unexpected format")

        user_ids: set[int] = set()
        raw_ids = read("ALLOWED_USER_IDS")
        for item in (raw_ids or "").replace(";", ",").split(","):
            item = item.strip()
            if not item:
                continue
            if item.isdigit() and int(item) > 0:
                user_ids.add(int(item))
            else:
                problems.append(f"ALLOWED_USER_IDS: {item!r} is not a positive integer")
        if raw_ids is not None and not user_ids and not any("ALLOWED_USER_IDS:" in p for p in problems):
            problems.append("ALLOWED_USER_IDS must contain at least one user id")

        domains: set[str] = set()
        for item in (read("ALLOWED_DOMAINS", required=False) or "").split(","):
            if item.strip():
                try:
                    domains.add(validate_domain(item))
                except ValidationError:
                    problems.append(f"ALLOWED_DOMAINS: {item.strip()!r} is not a valid domain")

        raw_ro = env.get("READ_ONLY", "false").strip().lower()
        if raw_ro not in _TRUE | _FALSE:
            problems.append("READ_ONLY must be true or false")

        language = env.get("BOT_LANGUAGE", "fa").strip().lower() or "fa"
        if language not in LANGUAGES:
            problems.append(f"BOT_LANGUAGE must be one of: {', '.join(LANGUAGES)}")

        log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in LOG_LEVELS:
            problems.append(f"LOG_LEVEL must be one of: {', '.join(LOG_LEVELS)}")

        base_url = env.get("ARVAN_BASE_URL", "").strip() or DEFAULT_BASE_URL
        if not base_url.startswith("https://"):
            problems.append("ARVAN_BASE_URL must start with https://")

        proxy = read("TELEGRAM_PROXY", required=False)
        if proxy and urlsplit(proxy).scheme not in ("http", "https", "socks5", "socks5h"):
            problems.append("TELEGRAM_PROXY must be an http, https, socks5 or socks5h URL")

        if problems:
            raise ConfigError(problems)
        assert token and api_key
        return cls(
            telegram_token=token,
            arvan_api_key=api_key,
            allowed_user_ids=frozenset(user_ids),
            allowed_domains=frozenset(domains),
            read_only=raw_ro in _TRUE,
            language=language,
            proxy=proxy,
            arvan_base_url=base_url,
            log_level=log_level,
        )
