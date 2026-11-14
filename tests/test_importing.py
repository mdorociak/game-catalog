from datetime import date
from decimal import Decimal

import pytest

from catalog.importing import (
    parse_int,
    parse_list,
    parse_price,
    parse_release_date,
    parse_tags,
)

NAN = float("nan")
JUNK = ["", "   ", None, NAN, "nan", "not a literal", "__import__('os')", "[" * 10_000]


# -- parse_list ---------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("['Action', 'Indie']", ["Action", "Indie"]),
    ("[]", []),
    (" ['RPG'] ", ["RPG"]),
    ("[' Action ', '', 'Action', 3, None]", ["Action"]),
])
def test_parse_list(value, expected):
    assert parse_list(value) == expected


@pytest.mark.parametrize("value", JUNK + ["not a list", "{'a': 1}", "'Action'", "('Action',)"])
def test_parse_list_junk_gives_empty_list(value):
    assert parse_list(value) == []


# -- parse_tags ---------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("{'FPS': 300, 'Action': 200}", {"FPS": 300, "Action": 200}),
    ("{}", {}),
    ("{'FPS': 300.0}", {"FPS": 300}),
    ("{'Action': 5504, \"1990's\": 1246}", {"Action": 5504, "1990's": 1246}),
    ("{'FPS': 300, 'Bad': 'x', 'Neg': -1, 'Bool': True, 1: 5, '': 3}", {"FPS": 300}),
])
def test_parse_tags(value, expected):
    assert parse_tags(value) == expected


@pytest.mark.parametrize("value", JUNK + ["{broken", "['FPS']", "{'FPS'}"])
def test_parse_tags_junk_gives_empty_dict(value):
    assert parse_tags(value) == {}


# -- parse_release_date -------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("1 Nov, 2000", date(2000, 11, 1)),
    ("Nov 1, 2000", date(2000, 11, 1)),
    (" 1 Nov, 2000 ", date(2000, 11, 1)),
    ("17 Sep, 2020", date(2020, 9, 17)),
    ("November 1, 2000", date(2000, 11, 1)),
    ("Mar 2019", date(2019, 3, 1)),
    ("2019", date(2019, 1, 1)),
])
def test_parse_release_date(value, expected):
    assert parse_release_date(value) == expected


@pytest.mark.parametrize("value", JUNK + ["Coming soon", "Q3 2025", "31 Feb, 2020", "To be announced"])
def test_parse_release_date_junk_gives_none(value):
    assert parse_release_date(value) is None


# -- parse_price --------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("7.19", "7.19"),
    (7.19, "7.19"),
    ("24.5", "24.50"),
    ("0", "0.00"),
    (0.0, "0.00"),
    (0, "0.00"),
    (" 9.99 ", "9.99"),
    ("7.195", "7.20"),
])
def test_parse_price(value, expected):
    result = parse_price(value)
    assert isinstance(result, Decimal)
    assert str(result) == expected


@pytest.mark.parametrize("value", JUNK + ["free", "Free to Play", float("inf"), "-1", -5.0, True])
def test_parse_price_unknown_gives_none(value):
    assert parse_price(value) is None


def test_free_and_unknown_price_are_different():
    assert parse_price("0") == Decimal("0")
    assert parse_price("") is None


# -- parse_int ----------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("123", 123), ("123.0", 123), (123.0, 123), (7, 7), (" 18 ", 18),
    ("", 0), (None, 0), (NAN, 0), ("abc", 0), ("-3", 0), (True, 0), ("inf", 0),
])
def test_parse_int(value, expected):
    assert parse_int(value) == expected


def test_parse_int_custom_default():
    assert parse_int("", default=None) is None