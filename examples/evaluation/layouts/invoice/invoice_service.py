from amounts import subtotal
from rounding import net_amount


def invoice_total(lines: list[int]) -> int:
    """Return the sum of valid lines, less a one-unit credit on totals of at least 100."""
    return net_amount(subtotal(lines))
