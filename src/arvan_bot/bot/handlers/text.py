from __future__ import annotations

from telegram import Update

from arvan_bot.bot import flow
from arvan_bot.bot.auth import authorized
from arvan_bot.bot.context import Ctx, deps

from . import cache, dns


@authorized
async def on_text(update: Update, context: Ctx) -> None:
    """Route free text to whichever multi-step flow is waiting for it."""
    f = flow.current(context.user_data)
    if f is not None and f.kind == dns.ADD and f.step == "name":
        return await dns.receive_name(update, context, f)
    if f is not None and f.kind == dns.ADD and f.step == "value":
        return await dns.receive_value(update, context, f)
    if f is not None and f.kind == cache.PURGE_URLS and f.step == "urls":
        return await cache.receive_urls(update, context, f)
    await update.effective_message.reply_text(deps(context).t("text_hint"))
