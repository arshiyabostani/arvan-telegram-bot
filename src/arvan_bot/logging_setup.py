"""Logging with secret redaction.

python-telegram-bot talks to ``api.telegram.org/bot<TOKEN>/...`` and httpx logs
full request URLs at INFO, so without care the bot token lands in the logs.
Two defences: the HTTP libraries are silenced below WARNING, and every
formatted record (tracebacks included) is scrubbed for known secrets.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable

# No \b here: in API URLs the token directly follows "bot" (".../bot123:ABC.../getMe").
_TOKEN_IN_TEXT = re.compile(r"(?<![0-9])\d{5,}:[A-Za-z0-9_-]{30,}")
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str], fmt: str = _FORMAT) -> None:
        super().__init__(fmt)
        self._secrets = sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return _TOKEN_IN_TEXT.sub("***", text)


def configure_logging(level: str, secrets: Iterable[str]) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter(secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Audit records are always emitted, whatever LOG_LEVEL says.
    logging.getLogger("arvan_bot.audit").setLevel(logging.INFO)
