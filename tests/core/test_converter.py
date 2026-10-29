"""Convertisseur : décomposition en contenants, saisie libre."""

from __future__ import annotations

import pytest

from syncron_core.converter import (
    CHEST,
    DOUBLE_CHEST,
    LINE,
    STACK,
    QuantityError,
    containers_needed,
    decompose,
    express,
    parse_quantity,
)


def test_unit_sizes_match_nationsglory():
    assert [u.size() for u in (STACK, LINE, CHEST, DOUBLE_CHEST)] == [64, 576, 1728, 3456]
    assert [u.size(16) for u in (STACK, LINE, CHEST, DOUBLE_CHEST)] == [16, 144, 432, 864]


@pytest.mark.parametrize(
    ("quantity", "stack_size", "text"),
    [
        (5000, 64, "1 double coffre + 2 lignes + 6 stacks + 8 objets seuls"),
        (3456, 64, "1 double coffre"),
        (1728 + 64, 64, "1 coffre + 1 stack"),
        (63, 64, "63 objets seuls"),
        (0, 64, "0 objet seul"),
        (100, 16, "6 stacks + 4 objets seuls"),
        (60, 1, "1 double coffre + 6 stacks"),
        (8 * 3456, 64, "8 doubles coffres"),
    ],
)
def test_decompose(quantity, stack_size, text):
    breakdown = decompose(quantity, stack_size)
    assert breakdown.text() == text
    total = sum(unit.size(stack_size) * count for unit, count in breakdown.parts) + breakdown.remainder
    assert total == quantity


def test_euclidean_division_with_chosen_units():
    assert decompose(648).text() == "1 ligne + 1 stack + 8 objets seuls"
    assert decompose(648, units=(STACK,)).text() == "10 stacks + 8 objets seuls"
    assert decompose(5000, units=(CHEST, STACK)).text() == "2 coffres + 24 stacks + 8 objets seuls"
    assert decompose(1, units=(LINE,)).text() == "1 objet seul"


def test_slots_express_and_containers():
    assert decompose(5000).slots == 79
    assert express(1728, DOUBLE_CHEST) == 0.5
    assert containers_needed(5000, DOUBLE_CHEST) == 2 and containers_needed(3456, DOUBLE_CHEST) == 1
    assert containers_needed(0, CHEST) == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5000", 5000),
        ("5 000", 5000),
        ("5 000", 5000),
        ("2,5k", 2500),
        ("1M", 1_000_000),
        ("3 coffres + 12", 3 * 1728 + 12),
        ("1 dc 4 stacks", 3456 + 256),
        ("2 doubles coffres", 6912),
        ("1 ligne", 576),
        ("1,5 stack", 96),
        ("2 Lignes + 1 Coffre", 2 * 576 + 1728),
    ],
)
def test_parse_quantity(text, expected):
    assert parse_quantity(text) == expected


def test_parse_quantity_follows_stack_size():
    assert parse_quantity("2 stacks", stack_size=16) == 32


@pytest.mark.parametrize("text", ["", "  ", "10 billes", "coffre", "1,3 stack", "abc 12"])
def test_parse_quantity_rejects(text):
    with pytest.raises(QuantityError):
        parse_quantity(text)
