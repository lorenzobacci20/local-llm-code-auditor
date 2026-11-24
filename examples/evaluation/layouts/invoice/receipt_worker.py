from invoice_handler import handle
from receipt_mapper import receipt_view


def summarize(invoices: list[list[int]]) -> list[str]:
    return [receipt_view(handle(lines)) for lines in invoices]
