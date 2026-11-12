"""Access control for every handler.

Rules, applied in this order:
1. Only private chats. In a group the bot's replies would be visible to others.
2. Only user ids on the allowlist. Everyone else is ignored silently: no reply,
   so the bot does not confirm its own existence or act as a spam relay.
3. A per-user sliding-window rate limit.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from functools import wraps

from telegram import Update
from telegram.constants import ChatType

from .context import Ctx, deps

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_calls: int = 20, period: float = 10.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._max = max_calls
        self._period = period
        self._clock = clock
        self._hits: dict[int, deque[float]] = {}

    def allow(self, key: int) -> bool:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self._period:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True


def is_authorized(update: Update, allowed: frozenset[int]) -> bool:
    user, chat = update.effective_user, update.effective_chat
    return user is not None and chat is not None and chat.type == ChatType.PRIVATE and user.id in allowed


def authorized(fn):
    @wraps(fn)
    async def wrapper(update: Update, context: Ctx, *args, **kwargs):
        d = deps(context)
        if not is_authorized(update, d.settings.allowed_user_ids):
            user, chat = update.effective_user, update.effective_chat
            log.warning(
                "ignored update from unauthorized source user_id=%s chat_type=%s",
                user.id if user else None,
                chat.type if chat else None,
            )
            if update.callback_query is not None:
                await update.callback_query.answer()
            return None
        if not d.limiter.allow(update.effective_user.id):
            if update.callback_query is not None:
                await update.callback_query.answer(d.t("rate_limited"))
            elif update.effective_message is not None:
                await update.effective_message.reply_text(d.t("rate_limited"))
            return None
        return await fn(update, context, *args, **kwargs)

    return wrapper
