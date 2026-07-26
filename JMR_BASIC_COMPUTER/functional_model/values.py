"""The value a BASIC expression produces.

Stage 1 is 16-bit signed integer BASIC, plus string literals so that
`PRINT "HELLO"` works.  A value carries its kind because the machine has to be
able to say ?TM ERROR, and because the floating point milestone adds a third
kind here rather than changing every engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import BasicError, TYPE_MISMATCH

KIND_INTEGER = "I"
KIND_STRING = "S"


@dataclass(frozen=True)
class Value:
    kind: str
    integer: int = 0
    text: str = ""

    @staticmethod
    def of_integer(value: int) -> "Value":
        return Value(KIND_INTEGER, integer=value)

    @staticmethod
    def of_string(text: str) -> "Value":
        return Value(KIND_STRING, text=text)

    @property
    def is_integer(self) -> bool:
        return self.kind == KIND_INTEGER

    @property
    def is_string(self) -> bool:
        return self.kind == KIND_STRING

    def require_integer(self) -> int:
        if self.kind != KIND_INTEGER:
            raise BasicError(TYPE_MISMATCH, "a number was expected")
        return self.integer

    def require_string(self) -> str:
        if self.kind != KIND_STRING:
            raise BasicError(TYPE_MISMATCH, "a string was expected")
        return self.text

    @property
    def truthy(self) -> bool:
        """Level II: any non-zero value is true."""
        return self.require_integer() != 0
