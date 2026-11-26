"""Decimal display rounding matching Intl halfExpand without changing evidence."""

from decimal import ROUND_HALF_UP, Decimal


def format_decimal(value: float | int, *, signed: bool = False, grouped: bool = False) -> str:
    number = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not number:
        number = abs(number)
    return format(number, ("+" if signed else "") + ("," if grouped else "") + ".2f")
