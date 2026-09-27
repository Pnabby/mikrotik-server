class ServiceError(Exception):
    """A safe application error that can be translated at the HTTP boundary."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        error_code: str | None = None,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        self.field_errors = field_errors or {}
