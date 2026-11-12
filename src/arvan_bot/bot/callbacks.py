"""Callback-data constants and the exact patterns that accept them.

Patterns are anchored and strict: anything that does not match is dropped
before it reaches a handler.
"""

from __future__ import annotations

import re

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

MENU = "menu"
INFO = "info"
ADD = "add"
ADD_CONFIRM = "ok"
PURGE_ALL = "pall"
PURGE_ALL_CONFIRM = "pallok"
PURGE_URLS = "purls"
NOOP = "noop"


def home(page: int = 0) -> str:
    return f"home:{page}"


def domain(index: int) -> str:
    return f"d:{index}"


def records(page: int = 0) -> str:
    return f"recs:{page}"


def record(rid: str) -> str:
    return f"rec:{rid}"


def cloud(rid: str, enabled: bool) -> str:
    return f"cloud:{rid}:{int(enabled)}"


def delete(rid: str) -> str:
    return f"del:{rid}"


def delete_confirm(rid: str) -> str:
    return f"delok:{rid}"


def rtype(value: str) -> str:
    return f"t:{value}"


def ttl(value: int) -> str:
    return f"ttl:{value}"


def cloud_choice(enabled: bool) -> str:
    return f"cl:{int(enabled)}"


def _p(expr: str) -> re.Pattern[str]:
    return re.compile(expr)


P_HOME = _p(r"^home(?::(\d{1,2}))?$")
P_DOMAIN = _p(r"^d:(\d{1,3})$")
P_MENU = _p(rf"^{MENU}$")
P_INFO = _p(rf"^{INFO}$")
P_RECORDS = _p(r"^recs:(\d{1,3})$")
P_RECORD = _p(rf"^rec:({UUID})$")
P_CLOUD = _p(rf"^cloud:({UUID}):([01])$")
P_DELETE = _p(rf"^del:({UUID})$")
P_DELETE_CONFIRM = _p(rf"^delok:({UUID})$")
P_ADD = _p(rf"^{ADD}$")
P_TYPE = _p(r"^t:(A|AAAA|CNAME|ANAME|TXT|MX|NS)$")
P_TTL = _p(r"^ttl:(\d{3,6})$")
P_CLOUD_CHOICE = _p(r"^cl:([01])$")
P_ADD_CONFIRM = _p(rf"^{ADD_CONFIRM}$")
P_PURGE_ALL = _p(rf"^{PURGE_ALL}$")
P_PURGE_ALL_CONFIRM = _p(rf"^{PURGE_ALL_CONFIRM}$")
P_PURGE_URLS = _p(rf"^{PURGE_URLS}$")
P_NOOP = _p(rf"^{NOOP}$")
