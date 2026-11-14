import ast
import math
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_LITERAL_ERRORS = (ValueError, TypeError, SyntaxError, MemoryError, RecursionError)

_DATE_FORMATS = (
    "%d %b, %Y", 
    "%b %d, %Y", 
    "%d %B, %Y", 
    "%B %d, %Y", 
    "%b %Y",   
    "%B %Y",
    "%Y", 
)

_CENT = Decimal("0.01")


def _literal(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return ast.literal_eval(value.strip())
    except _LITERAL_ERRORS:
        return None


def parse_list(value):
    parsed = _literal(value)
    if not isinstance(parsed, list):
        return []
    names = (item.strip() for item in parsed if isinstance(item, str))
    return list(dict.fromkeys(name for name in names if name))


def parse_tags(value):
    parsed = _literal(value)
    if not isinstance(parsed, dict):
        return {}
    tags = {}
    for name, votes in parsed.items():
        if not isinstance(name, str) or not name.strip():
            continue
        if isinstance(votes, bool) or not isinstance(votes, (int, float)):
            continue
        if not math.isfinite(votes) or votes < 0:
            continue
        tags[name.strip()] = int(votes)
    return tags


def parse_release_date(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_price(value):
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        text = str(value)
    else:
        return None
    try:
        price = Decimal(text)
        if not price.is_finite() or price < 0: 
            return None
        return price.quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def parse_int(value, default=0):
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, (str, float)):
        text = str(value).strip()
        try:
            number = int(text)
        except ValueError:
            try:
                as_float = float(text)
            except ValueError:
                return default
            if not math.isfinite(as_float):
                return default
            number = int(as_float)
    else:
        return default
    return number if number >= 0 else default