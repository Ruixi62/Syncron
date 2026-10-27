from __future__ import annotations

import pytest

from syncron_core.duration import DurationError, format_duration, parse_duration
from syncron_core.text import ceil_div, format_quantity, normalize, prettify_id


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        (0, 0),
        (45, 45),
        ("instant", 0),
        ("Instantané", 0),
        ("30s", 30),
        ("5m", 300),
        ("5 min", 300),
        ("2h", 7200),
        ("1h30", 5400),
        ("1h 30m", 5400),
        ("2h15m10s", 8110),
        ("1j", 86400),
        ("1j2", 93600),
        ("90", 90),
    ],
)
def test_parse_duration(value, seconds):
    assert parse_duration(value) == seconds


@pytest.mark.parametrize("value", [-1, "abc", "1h x", "10s 5", True, 1.5, None, ""])
def test_parse_duration_rejects(value):
    with pytest.raises(DurationError):
        parse_duration(value)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "Instantané"),
        (45, "45 s"),
        (90, "1 min 30 s"),
        (5400, "1 h 30 min"),
        (8110, "2 h 15 min 10 s"),
        (93_600, "1 j 2 h"),
    ],
)
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text


def test_format_duration_compact():
    assert format_duration(8110, compact=True) == "2 h 15 min"


def test_text_helpers():
    assert normalize("  Lingot_d'Étain ") == "lingot d'etain"
    assert prettify_id("circuit_avance") == "Circuit avance"
    assert format_quantity(1234567) == "1 234 567"
    assert [ceil_div(n, 4) for n in (1, 4, 5, 8, 9)] == [1, 1, 2, 2, 3]
