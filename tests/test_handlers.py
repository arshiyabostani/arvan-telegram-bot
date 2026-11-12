"""End-to-end tests of the Telegram handlers against an in-memory fake Arvan API.

The real handler routing table is used (taken from ``build_application``), only
Telegram I/O and the HTTP transport are faked.
"""

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from arvan_bot.arvan import ArvanClient
from arvan_bot.bot import callbacks as cb
from arvan_bot.bot import flow
from arvan_bot.bot.app import build_application
from arvan_bot.bot.context import DEPS_KEY
from arvan_bot.config import Settings

TOKEN = "123456789:" + "A" * 35
KEY = "11111111-2222-3333-4444-555555555555"
R1 = "aaaaaaaa-0000-4000-8000-000000000001"


class FakeArvan:
    def __init__(self):
        self.records = {
            R1: {
                "id": R1,
                "type": "A",
                "name": "<b>www</b>",
                "ttl": 120,
                "cloud": False,
                "value": [{"ip": "198.51.100.7"}],
            },
        }
        self.purges: list[dict] = []
        self.calls: list[tuple[str, str]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        self.calls.append((method, path))
        base = "/cdn/4.0/domains"
        if path == base:
            return httpx.Response(200, json={"data": [{"domain": "example.com"}, {"domain": "other.org"}]})
        if path == f"{base}/example.com":
            return httpx.Response(200, json={"data": {"domain": "example.com", "status": "active", "plan_level": 1}})
        recs = f"{base}/example.com/dns-records"
        if path == recs and method == "GET":
            return httpx.Response(200, json={"data": list(self.records.values())})
        if path == recs and method == "POST":
            body = json.loads(req.content)
            rid = f"bbbbbbbb-0000-4000-8000-{len(self.records):012d}"
            self.records[rid] = {"id": rid, **body}
            return httpx.Response(201, json={"data": self.records[rid]})
        m = re.fullmatch(rf"{recs}/([0-9a-f-]{{36}})(/cloud)?", path)
        if m and m.group(1) in self.records:
            rec = self.records[m.group(1)]
            if m.group(2) and method == "PUT":
                rec["cloud"] = json.loads(req.content)["cloud"]
                return httpx.Response(200, json={"data": rec})
            if method == "GET":
                return httpx.Response(200, json={"data": rec})
            if method == "DELETE":
                del self.records[m.group(1)]
                return httpx.Response(200, json={"message": "deleted"})
        if path == f"{base}/example.com/caching/purge" and method == "POST":
            self.purges.append(json.loads(req.content))
            return httpx.Response(200, json={"message": "ok"})
        return httpx.Response(404, json={"message": "Not found"})

    def mutations(self):
        return [c for c in self.calls if c[0] != "GET"]


class Session:
    """A fake Telegram chat with one user."""

    def __init__(self, *, user_id=42, read_only=False):
        settings = Settings(
            telegram_token=TOKEN,
            arvan_api_key=KEY,
            allowed_user_ids=frozenset({42}),
            language="en",
            read_only=read_only,
        )
        self.app = build_application(settings)
        self.api = FakeArvan()
        deps = self.app.bot_data[DEPS_KEY]
        deps.client = ArvanClient(KEY, read_only=read_only, transport=httpx.MockTransport(self.api))
        self.user_id = user_id
        self.user_data: dict = {}
        self.text = None
        self.markup = None

    # -- fake Telegram I/O
    def _capture(self, text, reply_markup=None, **_):
        self.text, self.markup = text, reply_markup

    def _update(self, *, data=None, text=None):
        msg = SimpleNamespace(text=text, reply_text=AsyncMock(side_effect=self._capture))
        query = None
        if data is not None:
            query = SimpleNamespace(
                data=data, answer=AsyncMock(), message=msg, edit_message_text=AsyncMock(side_effect=self._capture)
            )
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=self.user_id),
            effective_chat=SimpleNamespace(type="private"),
            callback_query=query,
            effective_message=msg,
        )

    def _ctx(self, match=None):
        return SimpleNamespace(user_data=self.user_data, bot_data=self.app.bot_data, match=match)

    # -- user actions
    async def command(self, name):
        for h in self.app.handlers[0]:
            if isinstance(h, CommandHandler) and name in h.commands:
                return await h.callback(self._update(text=f"/{name}"), self._ctx())
        raise AssertionError(f"no command {name}")

    async def press(self, data):
        for h in self.app.handlers[0]:
            if isinstance(h, CallbackQueryHandler) and (m := h.pattern.match(data)):
                return await h.callback(self._update(data=data), self._ctx(m))
        raise AssertionError(f"no handler matches {data!r}")

    async def send(self, text):
        for h in self.app.handlers[0]:
            if isinstance(h, MessageHandler):
                return await h.callback(self._update(text=text), self._ctx())
        raise AssertionError("no text handler")

    def buttons(self):
        if self.markup is None:
            return []
        return [(b.text, b.callback_data) for row in self.markup.inline_keyboard for b in row]

    def data(self):
        return [d for _, d in self.buttons()]

    async def open_domain(self):
        await self.command("start")
        await self.press(cb.domain(0))  # example.com (sorted)


@pytest.fixture
def s():
    return Session()


async def test_start_lists_domains_and_opens_menu(s):
    await s.command("start")
    assert [t for t, _ in s.buttons()] == ["example.com", "other.org"]
    await s.press(cb.domain(0))
    assert "example.com" in s.text
    assert {cb.ADD, cb.PURGE_ALL, cb.PURGE_URLS, cb.INFO, cb.records()} <= set(s.data())


async def test_every_callback_the_ui_emits_is_accepted_by_a_pattern(s):
    """Guards against UI/pattern drift (e.g. callback data longer than 64 bytes)."""
    await s.open_domain()
    await s.press(cb.records())
    for _, data in s.buttons():
        assert len(data.encode()) <= 64
        assert any(isinstance(h, CallbackQueryHandler) and h.pattern.match(data) for h in s.app.handlers[0]), data


async def test_record_list_escapes_html_from_the_api(s):
    await s.open_domain()
    await s.press(cb.record(R1))
    assert "<b>www</b>" not in s.text and "&lt;b&gt;www&lt;/b&gt;" in s.text


async def test_add_record_flow_end_to_end(s):
    await s.open_domain()
    await s.press(cb.ADD)
    await s.press(cb.rtype("A"))
    await s.send("WWW2")
    await s.send("203.0.113.10")
    await s.press(cb.ttl(300))
    await s.press(cb.cloud_choice(True))
    assert "203.0.113.10" in s.text and "www2" in s.text
    assert not s.api.mutations()  # nothing sent before explicit confirmation
    await s.press(cb.ADD_CONFIRM)
    (rec,) = [r for r in s.api.records.values() if r["name"] == "www2"]
    assert rec["type"] == "A" and rec["ttl"] == 300 and rec["cloud"] is True
    assert rec["value"][0]["ip"] == "203.0.113.10"
    assert flow.current(s.user_data) is None


async def test_add_flow_rejects_bad_input_and_stays_on_step(s):
    await s.open_domain()
    await s.press(cb.ADD)
    await s.press(cb.rtype("A"))
    await s.send("bad name!")
    assert "Invalid input" in s.text
    await s.send("www")
    await s.send("999.1.1.1")
    assert "Invalid input" in s.text
    assert flow.current(s.user_data).step == "value"
    assert not s.api.mutations()


async def test_add_confirm_cannot_be_replayed(s):
    await s.open_domain()
    await s.press(cb.ADD)
    await s.press(cb.rtype("TXT"))
    await s.send("_dmarc")
    await s.send("v=DMARC1; p=none")
    await s.press(cb.ttl(120))  # TXT is not proxyable: goes straight to confirmation
    await s.press(cb.ADD_CONFIRM)
    n = len(s.api.mutations())
    await s.press(cb.ADD_CONFIRM)  # stale button
    assert len(s.api.mutations()) == n and "expired" in s.text


async def test_out_of_order_flow_buttons_are_rejected(s):
    await s.open_domain()
    await s.press(cb.ttl(300))  # no flow at all
    assert "expired" in s.text
    await s.press(cb.ADD)
    await s.press(cb.ADD_CONFIRM)  # flow is at step "type"
    assert "expired" in s.text and not s.api.mutations()


async def test_toggle_cloud(s):
    await s.open_domain()
    await s.press(cb.record(R1))
    assert cb.cloud(R1, True) in s.data()
    await s.press(cb.cloud(R1, True))
    assert s.api.records[R1]["cloud"] is True
    assert cb.cloud(R1, False) in s.data()  # button flipped after refresh


async def test_delete_needs_fresh_confirmation(s):
    await s.open_domain()
    await s.press(cb.delete_confirm(R1))  # forged/stale: never asked
    assert R1 in s.api.records and "expired" in s.text

    await s.press(cb.delete(R1))
    assert R1 in s.api.records
    s.user_data["flow"].expires_at = 0  # let the confirmation lapse
    await s.press(cb.delete_confirm(R1))
    assert R1 in s.api.records and "expired" in s.text

    await s.press(cb.delete(R1))
    await s.press(cb.delete_confirm(R1))
    assert R1 not in s.api.records
    await s.press(cb.delete_confirm(R1))  # replay
    assert [c for c in s.api.mutations() if c[0] == "DELETE"] == [
        ("DELETE", f"/cdn/4.0/domains/example.com/dns-records/{R1}")
    ]


async def test_delete_confirmation_is_bound_to_the_record(s):
    other = "cccccccc-0000-4000-8000-000000000002"
    s.api.records[other] = {"id": other, "type": "TXT", "name": "x", "ttl": 120, "value": {"text": "t"}}
    await s.open_domain()
    await s.press(cb.delete(R1))
    await s.press(cb.delete_confirm(other))  # confirmation was for R1, not this one
    assert other in s.api.records and R1 in s.api.records


async def test_purge_all_requires_confirmation_and_cannot_replay(s):
    await s.open_domain()
    await s.press(cb.PURGE_ALL_CONFIRM)
    assert not s.api.purges
    await s.press(cb.PURGE_ALL)
    assert not s.api.purges
    await s.press(cb.PURGE_ALL_CONFIRM)
    assert s.api.purges == [{"purge": "all"}]
    await s.press(cb.PURGE_ALL_CONFIRM)
    assert len(s.api.purges) == 1


async def test_purge_urls_rejects_foreign_hosts(s):
    await s.open_domain()
    await s.press(cb.PURGE_URLS)
    await s.send("https://evil.com/x")
    assert "Invalid input" in s.text and not s.api.purges
    await s.send("https://example.com/a.css https://cdn.example.com/b.js")
    assert s.api.purges == [
        {"purge": "individual", "purge_urls": ["https://example.com/a.css", "https://cdn.example.com/b.js"]}
    ]
    assert flow.current(s.user_data) is None


async def test_navigation_cancels_pending_flow(s):
    await s.open_domain()
    await s.press(cb.ADD)
    await s.press(cb.MENU)
    assert flow.current(s.user_data) is None
    await s.send("www")  # text after cancelling is not treated as input
    assert "/start" in s.text


async def test_cancel_command(s):
    await s.open_domain()
    await s.press(cb.PURGE_URLS)
    await s.command("cancel")
    assert flow.current(s.user_data) is None


async def test_actions_without_a_selected_domain(s):
    await s.press(cb.records())
    assert "expired" in s.text
    await s.press(cb.PURGE_ALL_CONFIRM)
    assert not s.api.purges and not s.api.calls


async def test_read_only_mode():
    s = Session(read_only=True)
    await s.open_domain()
    assert cb.ADD not in s.data() and cb.PURGE_ALL not in s.data()
    await s.press(cb.record(R1))
    assert cb.delete(R1) not in s.data() and cb.cloud(R1, True) not in s.data()
    for data in (cb.ADD, cb.PURGE_ALL, cb.PURGE_URLS, cb.delete(R1)):  # forged taps
        await s.press(data)
        assert "read-only" in s.text
    await s.press(cb.cloud(R1, True))
    assert "read-only" in s.text
    assert s.api.records[R1]["cloud"] is False
    assert not s.api.mutations()


async def test_unauthorized_user_is_ignored_completely():
    s = Session(user_id=999)
    await s.command("start")
    await s.press(cb.domain(0))
    await s.send("anything")
    assert s.text is None and s.api.calls == []


async def test_api_failure_is_reported_without_crashing(s):
    deps = s.app.bot_data[DEPS_KEY]
    deps.client = ArvanClient(
        KEY, transport=httpx.MockTransport(lambda r: httpx.Response(500, json={"message": "boom"})), max_retries=0
    )
    await s.command("start")
    assert "Arvan API error" in s.text and "boom" in s.text
