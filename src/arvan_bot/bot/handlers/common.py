from __future__ import annotations

from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest

from arvan_bot.arvan import ArvanError, DomainNotAllowedError, ReadOnlyError
from arvan_bot.bot import callbacks as cb
from arvan_bot.bot import flow
from arvan_bot.bot.auth import authorized
from arvan_bot.bot.context import Ctx, deps

DOMAIN_KEY = "domain"


def button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def keyboard(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows])


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def show(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the message a button belongs to, or send a new message after text input."""
    query = update.callback_query
    if query is not None:
        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as exc:
            if "not modified" not in str(exc).lower():
                raise
        return
    await update.effective_message.reply_text(text, reply_markup=markup)


async def fail(update: Update, context: Ctx, exc: ArvanError, *, back: str = cb.MENU) -> None:
    d = deps(context)
    if isinstance(exc, ReadOnlyError):
        text = d.t("read_only")
    elif isinstance(exc, DomainNotAllowedError):
        text = d.t("domain_not_allowed")
    else:
        text = d.t("api_error", detail=exc.public_message)
    await show(update, text, keyboard([button(d.t("btn_back"), back)]))


async def expired(update: Update, context: Ctx) -> None:
    d = deps(context)
    await show(update, d.t("flow_expired"), keyboard([button(d.t("btn_back"), cb.MENU)]))


def domain_required(fn):
    """Inject the selected domain; send the user back to /start if there is none."""

    @wraps(fn)
    async def wrapper(update: Update, context: Ctx, *args, **kwargs):
        domain = context.user_data.get(DOMAIN_KEY)
        if not domain:
            flow.clear(context.user_data)
            await show(update, deps(context).t("session_expired"))
            return None
        return await fn(update, context, domain, *args, **kwargs)

    return wrapper


@authorized
async def help_command(update: Update, context: Ctx) -> None:
    await update.effective_message.reply_text(deps(context).t("help"))
