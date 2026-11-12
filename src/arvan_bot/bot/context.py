from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from telegram.ext import ContextTypes

from arvan_bot.arvan import ArvanClient
from arvan_bot.config import Settings

if TYPE_CHECKING:
    from .auth import RateLimiter
    from .messages import Translator

Ctx = ContextTypes.DEFAULT_TYPE
DEPS_KEY = "deps"


@dataclass(slots=True)
class Deps:
    settings: Settings
    client: ArvanClient
    limiter: RateLimiter
    t: Translator


def deps(context: Ctx) -> Deps:
    return context.bot_data[DEPS_KEY]
