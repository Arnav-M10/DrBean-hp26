"""Public scientific errors; callers supply workflow/request identifiers separately."""

from __future__ import annotations


class AdapterError(ValueError):
    """A stable reason and safe, field-specific message without private input data."""

    def __init__(
        self,
        code: str,
        message: str,
        field_paths: tuple[str, ...] = (),
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field_paths = tuple(field_paths)
        self.retryable = retryable

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "field_paths": list(self.field_paths),
            "retryable": self.retryable,
        }
