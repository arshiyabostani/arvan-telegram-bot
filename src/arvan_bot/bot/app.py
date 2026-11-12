from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    Defaults,
    MessageHandler,
    filters,
)

from arvan_bot.arvan import ArvanClient
from arvan_bot.config import Settings

from . import callbacks as cb
from .auth import RateLimiter, is_authorized
from .context import DEPS_KEY, Ctx, Deps
from .handlers import cache, common, dns, domains, text
from .messages import Translator

log = logging.getLogger(__name__)
ALLOWED_UPDATES = [Update.MESSAGE, Update.CALLBACK_QUERY]


async def _on_error(update: object, context: Ctx) -> None:
    log.error("unhandled error", exc_info=context.error)
    if not isinstance(update, Update):
        return
    d: Deps = context.bot_data[DEPS_KEY]
    if not is_authorized(update, d.settings.allowed_user_ids):
        return
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(d.t("unexpected_error"), show_alert=True)
        elif update.effective_message is not None:
            await update.effective_message.reply_text(d.t("unexpected_error"))
    except Exception:
        log.debug("could not notify user about the error", exc_info=True)


def build_application(settings: Settings) -> Application:
    client = ArvanClient(
        settings.arvan_api_key,
        base_url=settings.arvan_base_url,
        read_only=settings.read_only,
        allowed_domains=settings.allowed_domains,
    )

    async def close_client(_: Application) -> None:
        await client.aclose()

    builder = (
        Application.builder()
        .token(settings.telegram_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .concurrent_updates(False)  # per-user flow state assumes sequential handling
        .post_shutdown(close_client)
    )
    if settings.proxy:
        builder = builder.proxy(settings.proxy).get_updates_proxy(settings.proxy)
    app = builder.build()
    app.bot_data[DEPS_KEY] = Deps(
        settings=settings, client=client, limiter=RateLimiter(), t=Translator(settings.language)
    )

    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", domains.start, filters=private))
    app.add_handler(CommandHandler("help", common.help_command, filters=private))
    app.add_handler(CommandHandler("cancel", domains.cancel, filters=private))
    for pattern, handler in (
        (cb.P_HOME, domains.home),
        (cb.P_DOMAIN, domains.pick_domain),
        (cb.P_MENU, domains.menu),
        (cb.P_INFO, domains.info),
        (cb.P_NOOP, domains.noop),
        (cb.P_RECORDS, dns.list_records),
        (cb.P_RECORD, dns.record_detail),
        (cb.P_CLOUD, dns.toggle_cloud),
        (cb.P_DELETE, dns.delete_ask),
        (cb.P_DELETE_CONFIRM, dns.delete_do),
        (cb.P_ADD, dns.add_start),
        (cb.P_TYPE, dns.add_type),
        (cb.P_TTL, dns.add_ttl),
        (cb.P_CLOUD_CHOICE, dns.add_cloud),
        (cb.P_ADD_CONFIRM, dns.add_confirm),
        (cb.P_PURGE_ALL, cache.purge_all_ask),
        (cb.P_PURGE_ALL_CONFIRM, cache.purge_all_do),
        (cb.P_PURGE_URLS, cache.purge_urls_start),
    ):
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private, text.on_text))
    app.add_error_handler(_on_error)
    return app
