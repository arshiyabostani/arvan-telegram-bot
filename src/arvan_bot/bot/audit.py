"""Audit trail for every state-changing action.

One line per event; details are JSON-encoded so user-supplied text (record
names, TXT values) cannot forge extra log lines.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from telegram import Update

_log = logging.getLogger("arvan_bot.audit")


def audit(update: Update, action: str, outcome: str, **details: Any) -> None:
    user = update.effective_user
    _log.info(
        "user=%s action=%s outcome=%s details=%s",
        user.id if user else "?",
        action,
        outcome,
        json.dumps(details, ensure_ascii=True, sort_keys=True, default=str)[:600],
    )
