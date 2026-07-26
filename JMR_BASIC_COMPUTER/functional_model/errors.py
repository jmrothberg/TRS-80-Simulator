"""BASIC error codes.

The machine reports errors the way a Level II machine does:

    ?SN ERROR            (direct mode)
    ?UL ERROR IN 100     (while a program is running)

Every engine raises `BasicError`; the Program Control Unit catches it, asks the
Print Engine to display it, and stops the program.  No engine ever prints an
error itself.
"""

from __future__ import annotations


class BasicError(Exception):
    """An error the BASIC programmer is meant to see."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail

    def message(self, line_number: int = 0) -> str:
        text = f"?{self.code} ERROR"
        if line_number:
            text += f" IN {line_number}"
        return text


# Level II error codes used by this milestone.
SYNTAX = "SN"  # syntax error
UNDEFINED_LINE = "UL"  # undefined line number
TYPE_MISMATCH = "TM"  # string where a number belongs, or vice versa
OVERFLOW = "OV"  # outside the 16-bit signed range
DIVIDE_BY_ZERO = "/0"
NEXT_WITHOUT_FOR = "NF"
RETURN_WITHOUT_GOSUB = "RG"
OUT_OF_DATA = "OD"
ILLEGAL_FUNCTION_CALL = "FC"  # argument out of range
OUT_OF_MEMORY = "OM"
CANT_CONTINUE = "CN"
DIRECT_STATEMENT = "ID"  # illegal direct / illegal in a program
FILE_NOT_FOUND = "FF"  # storage engine


def syntax_error(detail: str = "") -> BasicError:
    return BasicError(SYNTAX, detail)
