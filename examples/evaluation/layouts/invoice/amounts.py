def subtotal(lines: list[int]) -> int:
    if any(amount < 0 for amount in lines):
        raise ValueError("line amounts must be non-negative")
    return sum(lines)
