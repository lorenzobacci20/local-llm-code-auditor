def mean(values: list[int]) -> float | None:
    """An empty window has no average."""
    if not values:
        return None
    return sum(values) / len(values)
