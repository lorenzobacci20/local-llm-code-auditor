def export_row(open_output, row: str) -> None:
    """Write one row and close our output stream, including on failure."""
    stream = open_output()
    stream.write(row)
    stream.close()
