"""Exceptions raised by the Arvan client.

``public_message`` is the only text that may be shown to a Telegram user. It
never contains raw response bodies, headers or credentials.
"""

from __future__ import annotations


class ArvanError(Exception):
    def __init__(self, public_message: str) -> None:
        super().__init__(public_message)
        self.public_message = public_message


class PolicyError(ArvanError):
    """The request was refused locally, before anything was sent."""


class ReadOnlyError(PolicyError):
    def __init__(self) -> None:
        super().__init__("read-only mode is enabled")


class DomainNotAllowedError(PolicyError):
    def __init__(self) -> None:
        super().__init__("domain is not allowed")


class ArvanNetworkError(ArvanError):
    pass


class ArvanAPIError(ArvanError):
    def __init__(self, status: int, public_message: str) -> None:
        super().__init__(public_message)
        self.status = status


class ArvanAuthError(ArvanAPIError):
    pass


class ArvanNotFoundError(ArvanAPIError):
    pass


class ArvanRateLimitError(ArvanAPIError):
    pass
