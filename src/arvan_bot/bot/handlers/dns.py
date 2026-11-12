from __future__ import annotations

import math

from telegram import Update

from arvan_bot.arvan import ArvanError
from arvan_bot.arvan.records import (
    CLOUD_CAPABLE,
    TTL_PRESETS,
    RecordType,
    build_record,
    format_value,
    parse_value,
)
from arvan_bot.bot import callbacks as cb
from arvan_bot.bot import flow
from arvan_bot.bot.audit import audit
from arvan_bot.bot.auth import authorized
from arvan_bot.bot.context import Ctx, deps
from arvan_bot.validation import ValidationError, validate_record_name, validate_ttl

from .common import button, domain_required, expired, fail, keyboard, show, truncate

PAGE_SIZE = 8
ADD = "add_record"
DELETE = "delete_record"


def _cloud_text(d, record: dict) -> str:
    return d.t("cloud_on") if record.get("cloud") else d.t("cloud_off")


# ------------------------------------------------------------------ listing
@authorized
@domain_required
async def list_records(update: Update, context: Ctx, domain: str) -> None:
    flow.clear(context.user_data)
    d = deps(context)
    try:
        records = await d.client.list_records(domain)
    except ArvanError as exc:
        return await fail(update, context, exc)
    pages = max(1, math.ceil(len(records) / PAGE_SIZE))
    page = min(int(context.match.group(1)), pages - 1)
    rows = []
    for rec in records[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
        dot = "🟠" if rec.get("cloud") else "⚪"
        label = f"{dot} {str(rec.get('type', '?')).upper()} {rec.get('name', '?')} → {format_value(rec)}"
        rows.append([button(truncate(label, 60), cb.record(str(rec.get("id"))))])
    nav = []
    if page > 0:
        nav.append(button("◀️", cb.records(page - 1)))
    nav.append(button(f"{page + 1}/{pages}", cb.NOOP))
    if page < pages - 1:
        nav.append(button("▶️", cb.records(page + 1)))
    rows.append(nav)
    rows.append([button(d.t("btn_back"), cb.MENU)])
    await show(update, d.t("records", domain=domain, count=len(records)), keyboard(*rows))


async def _render_record(update: Update, context: Ctx, domain: str, rid: str) -> None:
    d = deps(context)
    try:
        rec = await d.client.get_record(domain, rid)
    except ArvanError as exc:
        return await fail(update, context, exc, back=cb.records())
    rtype = str(rec.get("type", "")).upper()
    text = d.t(
        "record",
        name=rec.get("name", "?"),
        domain=domain,
        type=rtype,
        value=truncate(format_value(rec), 300),
        ttl=rec.get("ttl", "?"),
        cloud=_cloud_text(d, rec),
        id=rid,
    )
    rows = []
    if not d.settings.read_only:
        if rtype in CLOUD_CAPABLE:
            enabled = bool(rec.get("cloud"))
            label = d.t("btn_cloud_off" if enabled else "btn_cloud_on")
            rows.append([button(label, cb.cloud(rid, not enabled))])
        rows.append([button(d.t("btn_delete"), cb.delete(rid))])
    rows.append([button(d.t("btn_back"), cb.records())])
    await show(update, text, keyboard(*rows))


@authorized
@domain_required
async def record_detail(update: Update, context: Ctx, domain: str) -> None:
    flow.clear(context.user_data)
    await _render_record(update, context, domain, context.match.group(1))


# ----------------------------------------------------------------- mutations
@authorized
@domain_required
async def toggle_cloud(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    rid, enabled = context.match.group(1), context.match.group(2) == "1"
    try:
        await d.client.set_cloud(domain, rid, enabled)
    except ArvanError as exc:
        audit(update, "dns.cloud", "error", domain=domain, record=rid, error=exc.public_message)
        return await fail(update, context, exc, back=cb.records())
    audit(update, "dns.cloud", "ok", domain=domain, record=rid, cloud=enabled)
    await _render_record(update, context, domain, rid)


@authorized
@domain_required
async def delete_ask(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    rid = context.match.group(1)
    try:
        d.client.ensure_writable()
        rec = await d.client.get_record(domain, rid)
    except ArvanError as exc:
        return await fail(update, context, exc, back=cb.records())
    flow.begin(context.user_data, DELETE, "confirm", ttl=60, domain=domain, record=rid)
    desc = f"{str(rec.get('type', '?')).upper()} {rec.get('name', '?')} → {truncate(format_value(rec), 80)}"
    await show(
        update,
        d.t("delete_confirm", desc=desc),
        keyboard([button(d.t("btn_yes_delete"), cb.delete_confirm(rid)), button(d.t("btn_cancel"), cb.record(rid))]),
    )


@authorized
@domain_required
async def delete_do(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    rid = context.match.group(1)
    pending = flow.current(context.user_data, DELETE, "confirm")
    if pending is None or pending.data != {"domain": domain, "record": rid}:
        return await expired(update, context)
    flow.clear(context.user_data)
    try:
        await d.client.delete_record(domain, rid)
    except ArvanError as exc:
        audit(update, "dns.delete", "error", domain=domain, record=rid, error=exc.public_message)
        return await fail(update, context, exc, back=cb.records())
    audit(update, "dns.delete", "ok", domain=domain, record=rid)
    await show(update, d.t("deleted"), keyboard([button(d.t("btn_back"), cb.records())]))


# ---------------------------------------------------------------- add record
def _valid(f: flow.Flow | None, domain: str) -> bool:
    return f is not None and f.data.get("domain") == domain


@authorized
@domain_required
async def add_start(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    try:
        d.client.ensure_writable()
    except ArvanError as exc:
        return await fail(update, context, exc)
    flow.begin(context.user_data, ADD, "type", domain=domain)
    types = list(RecordType)
    rows = [[button(t.value, cb.rtype(t.value)) for t in types[i : i + 4]] for i in range(0, len(types), 4)]
    rows.append([button(d.t("btn_cancel"), cb.MENU)])
    await show(update, d.t("add_type"), keyboard(*rows))


@authorized
@domain_required
async def add_type(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    f = flow.current(context.user_data, ADD, "type")
    if not _valid(f, domain):
        return await expired(update, context)
    f.data["type"] = context.match.group(1)
    f.step = "name"
    await show(update, d.t("add_name"), keyboard([button(d.t("btn_cancel"), cb.MENU)]))


async def receive_name(update: Update, context: Ctx, f: flow.Flow) -> None:
    d = deps(context)
    try:
        f.data["name"] = validate_record_name(update.effective_message.text or "")
    except ValidationError as exc:
        return await update.effective_message.reply_text(d.t("invalid_input", detail=str(exc)))
    f.step = "value"
    hint = d.t(f"add_value_{f.data['type'].lower()}")
    await update.effective_message.reply_text(hint, reply_markup=keyboard([button(d.t("btn_cancel"), cb.MENU)]))


async def receive_value(update: Update, context: Ctx, f: flow.Flow) -> None:
    d = deps(context)
    raw = update.effective_message.text or ""
    try:
        parse_value(RecordType(f.data["type"]), raw)
    except ValidationError as exc:
        return await update.effective_message.reply_text(d.t("invalid_input", detail=str(exc)))
    f.data["value"] = raw.strip()
    f.step = "ttl"
    row = [button(label, cb.ttl(seconds)) for seconds, label in TTL_PRESETS]
    await update.effective_message.reply_text(
        d.t("add_ttl"), reply_markup=keyboard(row, [button(d.t("btn_cancel"), cb.MENU)])
    )


async def _confirm_view(update: Update, context: Ctx, domain: str, f: flow.Flow) -> None:
    d = deps(context)
    f.step = "confirm"
    rec = build_record(f.data["type"], f.data["name"], f.data["value"], f.data["ttl"], f.data.get("cloud", False))
    cloud = _cloud_text(d, rec) if RecordType(f.data["type"]) in CLOUD_CAPABLE else "-"
    text = d.t(
        "add_confirm",
        name=rec["name"],
        domain=domain,
        type=rec["type"],
        value=truncate(f.data["value"], 300),
        ttl=rec["ttl"],
        cloud=cloud,
    )
    await show(
        update,
        text,
        keyboard([button(d.t("btn_create"), cb.ADD_CONFIRM), button(d.t("btn_cancel"), cb.MENU)]),
    )


@authorized
@domain_required
async def add_ttl(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    f = flow.current(context.user_data, ADD, "ttl")
    if not _valid(f, domain):
        return await expired(update, context)
    try:
        f.data["ttl"] = validate_ttl(int(context.match.group(1)))
    except ValidationError:
        return await expired(update, context)
    if RecordType(f.data["type"]) in CLOUD_CAPABLE:
        f.step = "cloud"
        await show(
            update,
            d.t("add_cloud"),
            keyboard(
                [
                    button(d.t("btn_cloud_yes"), cb.cloud_choice(True)),
                    button(d.t("btn_cloud_no"), cb.cloud_choice(False)),
                ],
                [button(d.t("btn_cancel"), cb.MENU)],
            ),
        )
    else:
        await _confirm_view(update, context, domain, f)


@authorized
@domain_required
async def add_cloud(update: Update, context: Ctx, domain: str) -> None:
    f = flow.current(context.user_data, ADD, "cloud")
    if not _valid(f, domain):
        return await expired(update, context)
    f.data["cloud"] = context.match.group(1) == "1"
    await _confirm_view(update, context, domain, f)


@authorized
@domain_required
async def add_confirm(update: Update, context: Ctx, domain: str) -> None:
    d = deps(context)
    f = flow.current(context.user_data, ADD, "confirm")
    if not _valid(f, domain):
        return await expired(update, context)
    flow.clear(context.user_data)
    try:
        payload = build_record(
            f.data["type"], f.data["name"], f.data["value"], f.data["ttl"], f.data.get("cloud", False)
        )
        await d.client.create_record(domain, payload)
    except ValidationError:
        return await expired(update, context)
    except ArvanError as exc:
        audit(
            update,
            "dns.create",
            "error",
            domain=domain,
            type=f.data["type"],
            name=f.data["name"],
            error=exc.public_message,
        )
        return await fail(update, context, exc, back=cb.records())
    audit(
        update,
        "dns.create",
        "ok",
        domain=domain,
        type=payload["type"],
        name=payload["name"],
        value=truncate(f.data["value"], 200),
        ttl=payload["ttl"],
        cloud=payload["cloud"],
    )
    await show(update, d.t("created"), keyboard([button(d.t("btn_back"), cb.records())]))
