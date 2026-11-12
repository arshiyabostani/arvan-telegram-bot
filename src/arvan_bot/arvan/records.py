"""Building and displaying DNS record payloads.

Payload shapes follow the examples in the ArvanCloud CDN documentation
(docs.arvancloud.ir, "Add DNS Records").
"""

from __future__ import annotations

import ipaddress
import json
from enum import StrEnum
from typing import Any

from arvan_bot.validation import (
    ValidationError,
    validate_hostname,
    validate_record_name,
    validate_ttl,
)


class RecordType(StrEnum):
    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    ANAME = "ANAME"
    TXT = "TXT"
    MX = "MX"
    NS = "NS"


# Only these can be proxied through the CDN edge ("cloud").
CLOUD_CAPABLE = frozenset({RecordType.A, RecordType.AAAA, RecordType.CNAME, RecordType.ANAME})

TTL_PRESETS = ((120, "2m"), (300, "5m"), (3600, "1h"), (86400, "1d"))
MAX_TXT_LENGTH = 2000


def _ip(raw: str, version: int) -> list[dict[str, Any]]:
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        raise ValidationError(f"not a valid IPv{version} address") from None
    if addr.version != version:
        raise ValidationError(f"not a valid IPv{version} address")
    return [{"country": "", "ip": str(addr), "port": None, "weight": None}]


def parse_value(rtype: RecordType, raw: str) -> Any:
    """Turn what the user typed into the ``value`` field of the API payload."""
    raw = raw.strip()
    if rtype is RecordType.A:
        return _ip(raw, 4)
    if rtype is RecordType.AAAA:
        return _ip(raw, 6)
    if rtype is RecordType.CNAME:
        return {"host_header": "source", "host": validate_hostname(raw), "port": -1}
    if rtype is RecordType.ANAME:
        return {"host_header": "source", "location": validate_hostname(raw), "port": -1}
    if rtype is RecordType.NS:
        return {"host": validate_hostname(raw)}
    if rtype is RecordType.MX:
        parts = raw.split()
        if len(parts) != 2 or not parts[0].isdigit() or not 0 <= int(parts[0]) <= 65535:
            raise ValidationError("expected '<priority> <host>', for example '10 mail.example.com'")
        return {"host": validate_hostname(parts[1]), "priority": str(int(parts[0]))}
    if rtype is RecordType.TXT:
        if not raw or len(raw) > MAX_TXT_LENGTH or not raw.isprintable():
            raise ValidationError(f"text must be 1-{MAX_TXT_LENGTH} printable characters")
        return {"text": raw}
    raise ValidationError("unsupported record type")


def build_record(rtype: RecordType | str, name: str, raw_value: str, ttl: int, cloud: bool = False) -> dict[str, Any]:
    """Validate everything and return the JSON body for ``POST dns-records``."""
    try:
        rtype = RecordType(str(rtype).upper())
    except ValueError:
        raise ValidationError("unsupported record type") from None
    return {
        "type": rtype.value,
        "name": validate_record_name(name),
        "cloud": bool(cloud) and rtype in CLOUD_CAPABLE,
        "value": parse_value(rtype, raw_value),
        "upstream_https": "default",
        "ip_filter_mode": {"count": "single", "geo_filter": "none", "order": "none"},
        "ttl": validate_ttl(ttl),
    }


def format_value(record: dict[str, Any]) -> str:
    """Short, human-readable rendering of a record's value for display."""
    value = record.get("value")
    if isinstance(value, list):
        parts = [str(v.get("ip", v)) if isinstance(v, dict) else str(v) for v in value]
        return ", ".join(parts)
    if isinstance(value, dict):
        if "priority" in value and "host" in value:
            return f"{value['priority']} {value['host']}"
        for key in ("text", "host", "location", "target", "ip", "value"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return "" if value is None else str(value)
