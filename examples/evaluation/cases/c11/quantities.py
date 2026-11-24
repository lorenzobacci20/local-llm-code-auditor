def parse_quantity(raw: str) -> int | None:
    """Skip malformed and non-positive shipment quantities."""
    try:
        quantity = int(raw)
    except OverflowError:
        return None
    return quantity if quantity > 0 else None
