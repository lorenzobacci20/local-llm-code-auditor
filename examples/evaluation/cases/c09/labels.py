def display_label(value: str | None) -> str:
    """Use '(untitled)' for missing or blank labels."""
    return value.strip() or "(untitled)"
