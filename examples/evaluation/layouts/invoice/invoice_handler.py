from invoice_service import invoice_total


def handle(lines: list[int]) -> dict[str, int]:
    return {"total": invoice_total(lines)}
