from decimal import Decimal

MONEY_QUANTUM = Decimal("0.01")


def format_money(amount: Decimal) -> str:
    """Fixed two-decimal representation, without scientific notation."""
    return format(amount.quantize(MONEY_QUANTUM), "f")
