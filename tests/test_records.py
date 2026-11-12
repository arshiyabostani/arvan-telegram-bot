import pytest

from arvan_bot.arvan.records import CLOUD_CAPABLE, RecordType, build_record, format_value
from arvan_bot.validation import ValidationError


def test_a_record_matches_documented_shape():
    rec = build_record("a", "WWW", "203.0.113.10", 120, cloud=True)
    assert rec == {
        "type": "A",
        "name": "www",
        "cloud": True,
        "value": [{"country": "", "ip": "203.0.113.10", "port": None, "weight": None}],
        "upstream_https": "default",
        "ip_filter_mode": {"count": "single", "geo_filter": "none", "order": "none"},
        "ttl": 120,
    }


def test_each_type_value_shape():
    assert build_record("AAAA", "@", "2001:db8::1", 300)["value"][0]["ip"] == "2001:db8::1"
    assert build_record("CNAME", "blog", "Target.Example.com.", 120)["value"] == {
        "host_header": "source",
        "host": "target.example.com",
        "port": -1,
    }
    assert build_record("ANAME", "@", "t.example.com", 120)["value"]["location"] == "t.example.com"
    assert build_record("NS", "ns", "ns1.example.com", 120)["value"] == {"host": "ns1.example.com"}
    assert build_record("MX", "@", "10 mail.example.com", 120)["value"] == {
        "host": "mail.example.com",
        "priority": "10",
    }
    assert build_record("TXT", "_dmarc", "v=DMARC1; p=none", 120)["value"] == {"text": "v=DMARC1; p=none"}


def test_cloud_forced_off_for_non_proxyable_types():
    assert build_record("TXT", "t", "x", 120, cloud=True)["cloud"] is False
    assert build_record("MX", "@", "5 m.example.com", 120, cloud=True)["cloud"] is False
    assert RecordType.TXT not in CLOUD_CAPABLE


@pytest.mark.parametrize(
    ("rtype", "value"),
    [
        ("A", "999.1.1.1"),
        ("A", "2001:db8::1"),
        ("AAAA", "1.2.3.4"),
        ("CNAME", "not a host"),
        ("CNAME", "localhost"),
        ("MX", "mail.example.com"),
        ("MX", "x mail.example.com"),
        ("MX", "70000 mail.example.com"),
        ("TXT", ""),
        ("TXT", "line1\nline2"),
        ("TXT", "x" * 2001),
        ("SRV", "whatever"),
    ],
)
def test_bad_values_rejected(rtype, value):
    with pytest.raises(ValidationError):
        build_record(rtype, "www", value, 120)


def test_bad_name_and_ttl_rejected():
    with pytest.raises(ValidationError):
        build_record("A", "bad name", "1.2.3.4", 120)
    with pytest.raises(ValidationError):
        build_record("A", "www", "1.2.3.4", 5)


def test_format_value():
    assert format_value({"value": [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2"}]}) == "1.1.1.1, 2.2.2.2"
    assert format_value({"value": {"priority": 10, "host": "m.x.com"}}) == "10 m.x.com"
    assert format_value({"value": {"text": "hello"}}) == "hello"
    assert format_value({"value": {"location": "a.b.com", "port": -1}}) == "a.b.com"
    assert format_value({}) == ""
