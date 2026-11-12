import logging
from types import SimpleNamespace

from arvan_bot.bot.auth import RateLimiter, authorized, is_authorized
from arvan_bot.bot.context import DEPS_KEY
from arvan_bot.logging_setup import RedactingFormatter

TOKEN = "123456789:" + "A" * 35


def record(msg, exc_info=None):
    return logging.LogRecord("x", logging.INFO, __file__, 1, msg, (), exc_info)


def test_redacts_known_secrets_and_token_shapes():
    f = RedactingFormatter(["super-secret-key"], fmt="%(message)s")
    out = f.format(
        record(f"url https://api.telegram.org/bot{TOKEN}/getMe key=super-secret-key other 987654321:{'B' * 35}")
    )
    assert TOKEN not in out and "super-secret-key" not in out and "987654321:" not in out
    assert out.count("***") == 3


def test_redacts_inside_tracebacks():
    f = RedactingFormatter(["hunter2hunter2"], fmt="%(message)s")
    try:
        raise RuntimeError("failed with hunter2hunter2")
    except RuntimeError:
        import sys

        out = f.format(record("boom", exc_info=sys.exc_info()))
    assert "hunter2hunter2" not in out


def test_rate_limiter_sliding_window():
    now = [0.0]
    rl = RateLimiter(max_calls=3, period=10, clock=lambda: now[0])
    assert [rl.allow(1) for _ in range(4)] == [True, True, True, False]
    assert rl.allow(2) is True  # separate budget per user
    now[0] = 10.0
    assert rl.allow(1) is True


def make_update(user_id=42, chat_type="private"):
    q = SimpleNamespace(answered=[])

    async def answer(text=None, **_):
        q.answered.append(text)

    q.answer = answer
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type=chat_type),
        callback_query=q,
        effective_message=None,
    )


def make_context(allowed=frozenset({42}), limit=100):
    d = SimpleNamespace(
        settings=SimpleNamespace(allowed_user_ids=frozenset(allowed)),
        limiter=RateLimiter(max_calls=limit),
        t=lambda key, **_: key,
    )
    return SimpleNamespace(bot_data={DEPS_KEY: d})


async def test_authorized_decorator():
    calls = []

    @authorized
    async def handler(update, context):
        calls.append(update.effective_user.id)
        return "ran"

    ctx = make_context()
    assert await handler(make_update(42), ctx) == "ran"
    assert await handler(make_update(7), ctx) is None  # not on the allowlist
    assert await handler(make_update(42, "group"), ctx) is None  # not a private chat
    assert await handler(make_update(42, "supergroup"), ctx) is None
    assert calls == [42]


async def test_unauthorized_gets_no_reply_text():
    @authorized
    async def handler(update, context):  # pragma: no cover
        raise AssertionError

    upd = make_update(7)
    await handler(upd, make_context())
    assert upd.callback_query.answered == [None]  # callback dismissed silently


async def test_rate_limit_notifies_and_blocks():
    @authorized
    async def handler(update, context):
        return "ran"

    ctx = make_context(limit=1)
    assert await handler(make_update(), ctx) == "ran"
    upd = make_update()
    assert await handler(upd, ctx) is None
    assert upd.callback_query.answered == ["rate_limited"]


def test_is_authorized_requires_user_and_chat():
    assert not is_authorized(SimpleNamespace(effective_user=None, effective_chat=None), frozenset({1}))
