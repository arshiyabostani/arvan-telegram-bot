import string

from arvan_bot.bot.messages import EN, FA, Translator


def fields(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_catalogs_have_same_keys_and_placeholders():
    assert EN.keys() == FA.keys()
    for key in EN:
        assert fields(EN[key]) == fields(FA[key]), key


def test_translator_escapes_arguments():
    out = Translator("en")("menu", domain="<script>alert(1)</script>")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<b>" in out  # template markup is kept
