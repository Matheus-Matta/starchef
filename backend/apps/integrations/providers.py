class FiscalProvider:
    """Future NFC-e/NF-e provider contract. MVP intentionally does not issue fiscal documents."""

    def issue(self, invoice):
        raise NotImplementedError

    def cancel(self, invoice, reason):
        raise NotImplementedError

    def status(self, invoice):
        raise NotImplementedError

