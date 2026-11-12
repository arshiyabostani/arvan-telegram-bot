"""Input validation.

Everything that ends up in an API path or payload goes through this module
first. Messages of ``ValidationError`` are safe to show to the user.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit


class ValidationError(ValueError):
    """User input was rejected."""


_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_TLD = r"(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})"
_DOMAIN_RE = re.compile(rf"(?:{_LABEL}\.)+{_TLD}")
_RECORD_LABEL_RE = re.compile(r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?")
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

MIN_TTL = 120
MAX_TTL = 432_000
MAX_URL_LENGTH = 2048
MAX_PURGE_URLS = 30


def validate_domain(value: str) -> str:
    """Return a normalised zone name (lowercase, no trailing dot)."""
    name = value.strip().lower().rstrip(".")
    if len(name) > 253 or not _DOMAIN_RE.fullmatch(name):
        raise ValidationError("invalid domain name")
    return name


def validate_hostname(value: str) -> str:
    """Validate a target host used in CNAME, ANAME, MX and NS values."""
    try:
        return validate_domain(value)
    except ValidationError:
        raise ValidationError("invalid hostname") from None


def validate_record_id(value: str) -> str:
    rid = value.strip().lower()
    if not _UUID_RE.fullmatch(rid):
        raise ValidationError("invalid record id")
    return rid


def validate_record_name(value: str) -> str:
    """Accept ``@``, plain labels, ``_dmarc``-style labels and a leading ``*``."""
    name = value.strip().lower()
    if name == "@":
        return name
    name = name.rstrip(".")
    if not name or len(name) > 253:
        raise ValidationError("invalid record name")
    labels = name.split(".")
    for i, label in enumerate(labels):
        if label == "*" and i == 0:
            continue
        if not _RECORD_LABEL_RE.fullmatch(label):
            raise ValidationError("invalid record name")
    return name


def validate_ttl(value: int) -> int:
    if not MIN_TTL <= value <= MAX_TTL:
        raise ValidationError(f"TTL must be between {MIN_TTL} and {MAX_TTL}")
    return value


def validate_purge_urls(raw: str, domain: str, *, max_urls: int = MAX_PURGE_URLS) -> list[str]:
    """Split user input into URLs and make sure each one belongs to ``domain``.

    Arvan expects absolute URLs. Anything pointing outside the selected zone is
    rejected so a typo cannot purge somebody else's (or the wrong) site.
    """
    tokens = [t for t in re.split(r"[\s,]+", raw.strip()) if t]
    if not tokens:
        raise ValidationError("no URLs given")
    urls: list[str] = []
    for token in tokens:
        if token in urls:
            continue
        if len(token) > MAX_URL_LENGTH or not token.isprintable():
            raise ValidationError("invalid URL")
        try:
            parts = urlsplit(token)
            _ = parts.port
        except ValueError:
            raise ValidationError("invalid URL") from None
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValidationError("URLs must be absolute http(s) URLs")
        if parts.username or parts.password:
            raise ValidationError("URLs must not contain credentials")
        host = parts.hostname.lower().rstrip(".")
        if host != domain and not host.endswith("." + domain):
            raise ValidationError(f"{host} is not part of {domain}")
        urls.append(token)
    if len(urls) > max_urls:
        raise ValidationError(f"at most {max_urls} URLs per request")
    return urls
