import json

import httpx
import pytest

from arvan_bot.arvan import (
    ArvanAPIError,
    ArvanAuthError,
    ArvanClient,
    ArvanNetworkError,
    ArvanNotFoundError,
    DomainNotAllowedError,
    ReadOnlyError,
)
from arvan_bot.validation import ValidationError

RID = "1a700f5a-acef-4786-9192-4960dcf18449"


class Recorder:
    def __init__(self, *responses):
        self.requests: list[httpx.Request] = []
        self._responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def make(rec, **kw):
    async def no_sleep(_):
        return None

    return ArvanClient("KEY-123456789012345", transport=httpx.MockTransport(rec), sleep=no_sleep, **kw)


def ok(data=None, **extra):
    return httpx.Response(200, json={"data": data if data is not None else {}, **extra})


async def test_headers_and_paths():
    rec = Recorder(ok([{"domain": "example.com"}]))
    client = make(rec)
    assert [d["domain"] for d in await client.list_domains()] == ["example.com"]
    req = rec.requests[0]
    assert req.headers["authorization"] == "Apikey KEY-123456789012345"
    assert req.url.path == "/cdn/4.0/domains"
    assert req.url.scheme == "https"


async def test_requires_https_base_url():
    with pytest.raises(ValueError):
        ArvanClient("k" * 20, base_url="http://napi.arvancloud.ir")


async def test_purge_bodies_match_docs():
    rec = Recorder(httpx.Response(200, json={"message": "done"}))
    client = make(rec)
    await client.purge_all("example.com")
    await client.purge_urls("example.com", ["https://example.com/a"])
    assert json.loads(rec.requests[0].content) == {"purge": "all"}
    assert json.loads(rec.requests[1].content) == {"purge": "individual", "purge_urls": ["https://example.com/a"]}
    assert rec.requests[1].url.path == "/cdn/4.0/domains/example.com/caching/purge"


async def test_purge_urls_foreign_host_blocked_in_client_too():
    client = make(Recorder(ok()))
    with pytest.raises(ValidationError):
        await client.purge_urls("example.com", ["https://evil.com/x"])


async def test_cloud_body():
    rec = Recorder(ok())
    await make(rec).set_cloud("example.com", RID, True)
    req = rec.requests[0]
    assert req.method == "PUT" and req.url.path.endswith(f"/dns-records/{RID}/cloud")
    assert json.loads(req.content) == {"cloud": True}


async def test_path_injection_blocked():
    rec = Recorder(ok())
    client = make(rec)
    for bad in ("../../x", "example.com/../../y", "a.com?x=1"):
        with pytest.raises(ValidationError):
            await client.get_domain(bad)
    with pytest.raises(ValidationError):
        await client.get_record("example.com", "../" + RID)
    assert rec.requests == []


async def test_read_only_blocks_every_mutation_before_any_request():
    rec = Recorder(ok())
    client = make(rec, read_only=True)
    with pytest.raises(ReadOnlyError):
        await client.create_record("example.com", {})
    with pytest.raises(ReadOnlyError):
        await client.delete_record("example.com", RID)
    with pytest.raises(ReadOnlyError):
        await client.set_cloud("example.com", RID, False)
    with pytest.raises(ReadOnlyError):
        await client.purge_all("example.com")
    with pytest.raises(ReadOnlyError):
        await client.purge_urls("example.com", ["https://example.com/"])
    assert rec.requests == []
    await client.list_records("example.com")  # reads still work


async def test_domain_allowlist():
    rec = Recorder(ok([{"domain": "a.com"}, {"domain": "b.com"}]))
    client = make(rec, allowed_domains={"a.com"})
    assert [d["domain"] for d in await client.list_domains()] == ["a.com"]
    with pytest.raises(DomainNotAllowedError):
        await client.list_records("b.com")
    with pytest.raises(DomainNotAllowedError):
        await client.purge_all("b.com")
    assert len(rec.requests) == 1


async def test_get_retries_then_succeeds():
    rec = Recorder(httpx.Response(503), httpx.ConnectError("boom"), ok([{"domain": "x.com"}]))
    assert len(await make(rec).list_domains()) == 1
    assert len(rec.requests) == 3


async def test_get_gives_up_after_retries():
    rec = Recorder(httpx.ConnectError("boom"))
    with pytest.raises(ArvanNetworkError):
        await make(rec).list_domains()
    assert len(rec.requests) == 3


async def test_mutations_are_never_retried():
    rec = Recorder(httpx.Response(503, json={"message": "unavailable"}))
    client = make(rec)
    with pytest.raises(ArvanAPIError):
        await client.purge_all("example.com")
    assert len(rec.requests) == 1
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(ArvanNetworkError):
        await make(rec).delete_record("example.com", RID)
    assert len(rec.requests) == 1


async def test_error_mapping_and_no_body_leak():
    secret_body = {"message": "bad", "debug": "internal-stack-trace", "errors": {"name": ["The name is invalid."]}}
    client = make(Recorder(httpx.Response(422, json=secret_body)))
    with pytest.raises(ArvanAPIError) as exc:
        await client.get_domain("example.com")
    assert "internal-stack-trace" not in exc.value.public_message
    assert "name: The name is invalid." in exc.value.public_message

    with pytest.raises(ArvanAuthError):
        await make(Recorder(httpx.Response(401, text="<html>secret</html>"))).get_domain("example.com")
    with pytest.raises(ArvanNotFoundError):
        await make(Recorder(httpx.Response(404, json={"message": "Not found"}))).get_domain("example.com")


async def test_error_detail_is_sanitised_and_bounded():
    body = {"message": "line1\nline2\x00" + "x" * 1000}
    with pytest.raises(ArvanAPIError) as exc:
        await make(Recorder(httpx.Response(400, json=body))).get_domain("example.com")
    msg = exc.value.public_message
    assert "\n" not in msg and "\x00" not in msg and len(msg) < 260


async def test_redirects_are_not_followed():
    rec = Recorder(httpx.Response(302, headers={"location": "https://evil.example/"}))
    with pytest.raises(ArvanAPIError):
        await make(rec).get_domain("example.com")
    assert len(rec.requests) == 1


async def test_pagination_stops_on_repeated_pages():
    page = [{"id": str(i), "domain": f"d{i}.com"} for i in range(100)]
    rec = Recorder(ok(page))  # API ignores `page` and keeps returning the same data
    result = await make(rec).list_domains()
    assert len(result) == 100 and len(rec.requests) == 2


async def test_pagination_follows_meta():
    p1 = ok([{"id": str(i), "name": "r"} for i in range(100)], meta={"last_page": 2})
    p2 = ok([{"id": str(100 + i), "name": "r"} for i in range(5)], meta={"last_page": 2})
    rec = Recorder(p1, p2)
    assert len(await make(rec).list_records("example.com")) == 105
