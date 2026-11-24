class Ledger:
    def __init__(self, opening: int):
        self.balance = opening

    def post(self, deltas: list[int]) -> None:
        """Post the entire batch, or leave the opening balance intact."""
        closing = self.balance
        for delta in deltas:
            closing += delta
            if closing < 0:
                raise ValueError("negative balance")
        self.balance = closing
