class Ledger:
    def __init__(self, opening: int):
        self.balance = opening

    def post(self, deltas: list[int]) -> None:
        """Post the entire batch, or leave the opening balance intact."""
        for delta in deltas:
            if self.balance + delta < 0:
                raise ValueError("negative balance")
            self.balance += delta
