class ServiceError(Exception):
    """A safe application error that can be translated at the HTTP boundary."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
