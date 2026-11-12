"""Short-lived, server-side state for multi-step actions.

Confirmation buttons stay in the chat forever, so a stale "Yes, delete" must not
work on its own. Destructive actions only run when a matching, unexpired flow
exists in the user's session. A user has at most one flow at a time.
"""

from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

FLOW_KEY = "flow"


@dataclass
class Flow:
    kind: str
    step: str
    expires_at: float
    data: dict[str, Any] = field(default_factory=dict)


def begin(
    user_data: MutableMapping[str, Any],
    kind: str,
    step: str,
    *,
    ttl: float = 300.0,
    clock: Callable[[], float] = time.monotonic,
    **data: Any,
) -> Flow:
    flow = Flow(kind, step, clock() + ttl, dict(data))
    user_data[FLOW_KEY] = flow
    return flow


def current(
    user_data: MutableMapping[str, Any],
    kind: str | None = None,
    step: str | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> Flow | None:
    flow: Flow | None = user_data.get(FLOW_KEY)
    if flow is None:
        return None
    if clock() >= flow.expires_at:
        user_data.pop(FLOW_KEY, None)
        return None
    if (kind is not None and flow.kind != kind) or (step is not None and flow.step != step):
        return None
    return flow


def clear(user_data: MutableMapping[str, Any]) -> None:
    user_data.pop(FLOW_KEY, None)
