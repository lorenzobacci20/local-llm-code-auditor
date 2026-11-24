def net_amount(subtotal: int) -> int:
    """Grant one unit of credit on subtotals of at least 100."""
    return subtotal - 1 if subtotal >= 100 else subtotal
