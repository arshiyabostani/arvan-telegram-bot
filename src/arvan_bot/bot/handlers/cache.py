from __future__ import annotations

from telegram import Update

from arvan_bot.arvan import ArvanError
from arvan_bot.bot import callbacks as cb
from arvan_bot.bot import flow
from arvan_bot.bot.audit import audit
from arvan_bot.bot.auth import authorized
from arvan_bot.bot.context import Ctx, deps
from arvan_bot.validation import MAX_PURGE_URLS, ValidationError, validate_purge_urls

from .common import button, domain_required, expired, fail, keyboard, show

PURGE_ALL = "purge_all"
PURGE_URLS = "purge_urls"


@authorized
@domain_required
async def purge_all_ask(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    try:
        d.client.ensure_writable()
    except ArvanError as exc:
        return await fail(update, context, exc)
    flow.begin(context.user_data, PURGE_ALL, "confirm", ttl=60, domain=domain)
    await show(
        update,
        d.t("purge_all_confirm", domain=domain),
        keyboard([button(d.t("btn_yes_purge"), cb.PURGE_ALL_CONFIRM), button(d.t("btn_cancel"), cb.MENU)]),
    )


@authorized
@domain_required
async def purge_all_do(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    pending = flow.current(context.user_data, PURGE_ALL, "confirm")
    if pending is None or pending.data.get("domain") != domain:
        return await expired(update, context)
    flow.clear(context.user_data)
    try:
        await d.client.purge_all(domain)
    except ArvanError as exc:
        audit(update, "cache.purge_all", "error", domain=domain, error=exc.public_message)
        return await fail(update, context, exc)
    audit(update, "cache.purge_all", "ok", domain=domain)
    await show(update, d.t("purge_ok"), keyboard([button(d.t("btn_back"), cb.MENU)]))


@authorized
@domain_required
async def purge_urls_start(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    try:
        d.client.ensure_writable()
    except ArvanError as exc:
        return await fail(update, context, exc)
    flow.begin(context.user_data, PURGE_URLS, "urls", domain=domain)
    await show(
        update,
        d.t("purge_urls_prompt", domain=domain, max=MAX_PURGE_URLS),
        keyboard([button(d.t("btn_cancel"), cb.MENU)]),
    )


async def receive_urls(update: Update, context: Ctx, f: flow.Flow) -> None:
    d = deps(context)
    domain = f.data["domain"]
    message = update.effective_message
    try:
        urls = validate_purge_urls(message.text or "", domain)
    except ValidationError as exc:
        return await message.reply_text(d.t("invalid_input", detail=str(exc)))
    flow.clear(context.user_data)
    back = keyboard([button(d.t("btn_back"), cb.MENU)])
    try:
        await d.client.purge_urls(domain, urls)
    except ArvanError as exc:
        audit(update, "cache.purge_urls", "error", domain=domain, count=len(urls), error=exc.public_message)
        return await message.reply_text(d.t("api_error", detail=exc.public_message), reply_markup=back)
    audit(update, "cache.purge_urls", "ok", domain=domain, urls=urls)
    await message.reply_text(d.t("purge_urls_ok", count=len(urls)), reply_markup=back)
