from datetime import date

from estimate_maestro.identifiers import effort_identifier, new_identifier, slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Squidex Environment Tiers") == "squidex-environment-tiers"


def test_slugify_strips_punctuation_and_collapses_separators():
    assert slugify("Markdown  in .docx!") == "markdown-in-docx"


def test_effort_identifier_prefixes_the_creation_date():
    identifier = effort_identifier(date(2026, 8, 24), "Squidex Environment Tiers")

    assert identifier == "2026-08-24-squidex-environment-tiers"


def test_new_identifier_uses_the_supplied_source():
    assert new_identifier("iv", source=lambda: "0f3a1122") == "iv-0f3a1122"
