def decision(role: str | None) -> str:
    """Only reviewers can approve an entry. Ignore case and outer whitespace."""
    normalized = (role or "").strip().casefold()
    return "approved" if normalized == "reviewer" else "pending"
