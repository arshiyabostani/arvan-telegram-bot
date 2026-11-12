import pytest

from arvan_bot.validation import (
    ValidationError,
    validate_domain,
    validate_purge_urls,
    validate_record_id,
    validate_record_name,
    validate_ttl,
)

UUID = "1a700f5a-acef-4786-9192-4960dcf18449"


@pytest.mark.parametrize("value", ["example.com", "Sub.Example.IR.", "xn--p1ai.xn--p1ai", "3.2.1.in-addr.arpa"])
def test_domain_ok(value):
    assert validate_domain(value) == value.lower().rstrip(".")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "localhost",
        "a..b.com",
        "-a.com",
        "a.com/../x",
        "a.com?x=1",
        "a b.com",
        "exa_mple.com",
        "a.c",
        "x" * 64 + ".com",
    ],
)
def test_domain_rejected(value):
    with pytest.raises(ValidationError):
        validate_domain(value)


def test_record_id():
    assert validate_record_id(UUID.upper()) == UUID
    for bad in ["", "../etc", UUID + "/x", UUID[:-1], "1" * 36]:
        with pytest.raises(ValidationError):
            validate_record_id(bad)


@pytest.mark.parametrize("value", ["@", "www", "*", "*.dev", "_dmarc", "a.b.c", "WWW."])
def test_record_name_ok(value):
    validate_record_name(value)


@pytest.mark.parametrize("value", ["", "a/b", "a b", "-a", "a-", "..", "a.*", "a" * 64, "a;b", "a\nb"])
def test_record_name_rejected(value):
    with pytest.raises(ValidationError):
        validate_record_name(value)


def test_ttl_bounds():
    assert validate_ttl(120) == 120
    for bad in (0, 119, 432_001):
        with pytest.raises(ValidationError):
            validate_ttl(bad)


class TestPurgeUrls:
    def test_accepts_domain_and_subdomains(self):
        raw = "https://example.com/a.css, http://cdn.example.com/b.js\nhttps://example.com/a.css"
        assert validate_purge_urls(raw, "example.com") == [
            "https://example.com/a.css",
            "http://cdn.example.com/b.js",
        ]

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.com/",
            "https://example.com.evil.com/",
            "https://notexample.com/",
            "https://user:pw@example.com/",
            "ftp://example.com/",
            "/just/a/path",
            "https://example.com:badport/",
            "javascript:alert(1)",
        ],
    )
    def test_rejects_foreign_or_malformed(self, url):
        with pytest.raises(ValidationError):
            validate_purge_urls(url, "example.com")

    def test_empty_and_too_many(self):
        with pytest.raises(ValidationError):
            validate_purge_urls("  \n ", "example.com")
        many = "\n".join(f"https://example.com/{i}" for i in range(5))
        with pytest.raises(ValidationError):
            validate_purge_urls(many, "example.com", max_urls=4)
