class Stock:
    def __init__(self, units: int):
        self.units = units

    async def reserve(self, issue_receipt):
        """Issue one receipt per unit; other tasks may reserve during receipt delivery."""
        if self.units <= 0:
            return False
        await issue_receipt()
        self.units -= 1
        return True
