from __future__ import annotations

import html
import math

from telegram import Update

from arvan_bot.arvan import ArvanError
from arvan_bot.bot import callbacks as cb
from arvan_bot.bot import flow
from arvan_bot.bot.auth import authorized
from arvan_bot.bot.context import Ctx, deps

from .common import DOMAIN_KEY, button, domain_required, fail, keyboard, show

PAGE_SIZE = 10
DOMAINS_KEY = "domains"


async def _show_home(update: Update, context: Ctx, page: int) -> None:
    d = deps(context)
    try:
        items = await d.client.list_domains()
    except ArvanError as exc:
        return await fail(update, context, exc, back=cb.home())
    names = sorted(i["domain"].lower() for i in items)
    context.user_data[DOMAINS_KEY] = names
    if not names:
        return await show(update, d.t("home_empty"))
    pages = math.ceil(len(names) / PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    chunk = list(enumerate(names))[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    rows = [[button(name, cb.domain(idx)) for idx, name in chunk[i : i + 2]] for i in range(0, len(chunk), 2)]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(button("◀️", cb.home(page - 1)))
        nav.append(button(f"{page + 1}/{pages}", cb.NOOP))
        if page < pages - 1:
            nav.append(button("▶️", cb.home(page + 1)))
        rows.append(nav)
    await show(update, d.t("home"), keyboard(*rows))


@authorized
async def start(update: Update, context: Ctx) -> None:
    flow.clear(context.user_data)
    context.user_data.pop(DOMAIN_KEY, None)
    await _show_home(update, context, 0)


@authorized
async def home(update: Update, context: Ctx) -> None:
    flow.clear(context.user_data)
    context.user_data.pop(DOMAIN_KEY, None)
    await _show_home(update, context, int(context.match.group(1) or 0))


@authorized
async def cancel(update: Update, context: Ctx) -> None:
    flow.clear(context.user_data)
    await update.effective_message.reply_text(deps(context).t("cancelled"))


@authorized
async def pick_domain(update: Update, context: Ctx) -> None:
    d = deps(context)
    names = context.user_data.get(DOMAINS_KEY, [])
    index = int(context.match.group(1))
    if index >= len(names):
        return await show(update, d.t("session_expired"))
    flow.clear(context.user_data)
    context.user_data[DOMAIN_KEY] = names[index]
    await _menu(update, context, names[index])


@authorized
@domain_required
async def menu(update: Update, context: Ctx, domain: str) -> None:
    flow.clear(context.user_data)
    await _menu(update, context, domain)


async def _menu(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    rows = [[button(d.t("btn_records"), cb.records())]]
    if not d.settings.read_only:
        rows[0].append(button(d.t("btn_add"), cb.ADD))
        rows.append([button(d.t("btn_purge_all"), cb.PURGE_ALL), button(d.t("btn_purge_urls"), cb.PURGE_URLS)])
    rows.append([button(d.t("btn_info"), cb.INFO)])
    rows.append([button(d.t("btn_domains"), cb.home())])
    await show(update, d.t("menu", domain=domain), keyboard(*rows))


@authorized
@domain_required
async def info(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    try:
        data = await d.client.get_domain(domain)
    except ArvanError as exc:
        return await fail(update, context, exc)
    lines = [f"<b>{html.escape(domain)}</b>"]
    for field, label in (
        ("status", "info_status"),
        ("plan_level", "info_plan"),
        ("type", "info_type"),
        ("ns_keys", "info_ns"),
    ):
        value = data.get(field)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        lines.append(d.t("info_line", label=d.t(label), value=value))
    await show(update, "\n".join(lines), keyboard([button(d.t("btn_back"), cb.MENU)]))


async def noop(update: Update, context: Ctx) -> None:
    if update.callback_query is not None:
        await update.callback_query.answer()
