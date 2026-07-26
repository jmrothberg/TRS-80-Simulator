"""Tokenizer engine.

The TOKENIZER block of the architecture diagram, in the order the diagram shows
it:

    Lexical Analyzer -> Keyword Recognizer -> Number Parser
                     -> String Parser      -> Token Encoder

The tokenizer turns one line of source text into the byte stream the processor
executes.  It runs once, when a line is typed; after that the machine only ever
sees tokens.  Detokenizing (for LIST) is the same table read backwards, so both
directions live here.

Keyword recognition is greedy, exactly as it is on a Level II machine: the
longest keyword spelling that matches at the current position wins, even in the
middle of a name.  `FORT=1` really does tokenize as `FOR T=1`.  That is
authentic behavior and is kept deliberately.
"""

from __future__ import annotations

from . import tokens as tk
from .errors import BasicError, SYNTAX, syntax_error

#: Keyword spellings, longest first, so "<=" beats "<" and "PRINT" beats "P".
_SPELLINGS_BY_LENGTH = sorted(tk.KEYWORDS, key=len, reverse=True)

INT16_MIN = -32768
INT16_MAX = 32767


class TokenizedLine:
    """The tokenizer's output for one source line."""

    def __init__(self, line_number: int | None, token_bytes: bytes) -> None:
        self.line_number = line_number  # None = direct statement
        self.token_bytes = token_bytes  # always terminated by T_EOS

    @property
    def is_program_line(self) -> bool:
        return self.line_number is not None

    @property
    def is_empty(self) -> bool:
        """A line number with nothing after it, i.e. a delete request."""
        return self.token_bytes == bytes([tk.T_EOS])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        body = " ".join(f"{b:02X}" for b in self.token_bytes)
        return f"<TokenizedLine {self.line_number} [{body}]>"


class Tokenizer:
    """Source text in, token stream out."""

    def tokenize(self, source: str) -> TokenizedLine:
        text = source.rstrip("\r\n")
        position = 0
        length = len(text)

        # -- line number ---------------------------------------------------
        while position < length and text[position] == " ":
            position += 1
        line_number = None
        if position < length and text[position].isdigit():
            digits = ""
            while position < length and text[position].isdigit():
                digits += text[position]
                position += 1
            line_number = int(digits)
            if line_number > 0xFFFF:
                raise syntax_error("line number too large")

        out = bytearray()

        while position < length:
            char = text[position]

            # -- Lexical Analyzer: whitespace is not significant -----------
            if char == " ":
                position += 1
                continue

            # -- String Parser --------------------------------------------
            if char == '"':
                position = self._parse_string(text, position, out)
                continue

            # -- Keyword Recognizer ---------------------------------------
            keyword = self._recognize_keyword(text, position)
            if keyword is not None:
                spelling, opcode = keyword
                position += len(spelling)
                out.append(opcode)
                if opcode == tk.T_REM:
                    # The rest of the line is comment text, stored verbatim.
                    self._encode_string(out, text[position:])
                    position = length
                continue

            # -- Number Parser --------------------------------------------
            if char.isdigit():
                position = self._parse_number(text, position, out)
                continue

            # -- Variable reference ---------------------------------------
            if char.isalpha():
                position = self._parse_variable(text, position, out)
                continue

            raise syntax_error(f"unexpected character {char!r}")

        out.append(tk.T_EOS)
        return TokenizedLine(line_number, bytes(out))

    # -- sub-units ---------------------------------------------------------

    def _recognize_keyword(self, text: str, position: int) -> tuple[str, int] | None:
        upper = text.upper()
        for spelling in _SPELLINGS_BY_LENGTH:
            if upper.startswith(spelling, position):
                return spelling, tk.KEYWORDS[spelling]
        return None

    def _parse_number(self, text: str, position: int, out: bytearray) -> int:
        digits = ""
        while position < len(text) and text[position].isdigit():
            digits += text[position]
            position += 1
        if position < len(text) and text[position] in ".Ee":
            # Stage 1 is 16-bit signed integer BASIC (Constitution, FLOATING
            # POINT).  A real literal is a syntax error until stage 3.
            raise BasicError(SYNTAX, "floating point is not implemented yet")
        value = int(digits)
        # Literals up to 65535 are accepted so that hardware addresses can be
        # written the natural way (`POKE 45056,42`).  Anything above 32767 is
        # stored as its 16-bit pattern and therefore reads back negative until
        # the floating point milestone widens the value.
        if value > 0xFFFF:
            raise BasicError("OV", "integer constant out of range")
        self._encode_integer(out, value)
        return position

    def _parse_string(self, text: str, position: int, out: bytearray) -> int:
        position += 1  # opening quote
        body = ""
        while position < len(text) and text[position] != '"':
            body += text[position]
            position += 1
        if position < len(text):
            position += 1  # closing quote; an unterminated string ends the line
        self._encode_string(out, body)
        return position

    def _parse_variable(self, text: str, position: int, out: bytearray) -> int:
        name = ""
        while position < len(text) and (text[position].isalnum()):
            name += text[position].upper()
            position += 1
            # A keyword may start inside a name; stop so it is recognized.
            if self._recognize_keyword(text, position) is not None:
                break
        if position < len(text) and text[position] == "$":
            # String variables arrive with the String Engine (implementation
            # order step 17).  Until then this is a syntax error, not a silent
            # reinterpretation.
            raise BasicError(SYNTAX, "string variables are not implemented yet")
        self._encode_variable(out, name)
        return position

    # -- Token Encoder -----------------------------------------------------

    @staticmethod
    def _encode_integer(out: bytearray, value: int) -> None:
        out.append(tk.T_INTEGER)
        word = value & 0xFFFF
        out.append(word & 0xFF)
        out.append(word >> 8)

    @staticmethod
    def _encode_string(out: bytearray, body: str) -> None:
        data = body.encode("ascii", "replace")[:255]
        out.append(tk.T_STRING)
        out.append(len(data))
        out.extend(data)

    @staticmethod
    def _encode_variable(out: bytearray, name: str) -> None:
        first = ord(name[0])
        second = ord(name[1]) if len(name) > 1 else 0
        out.append(tk.T_VARIABLE)
        out.append(first)
        out.append(second)


def detokenize(token_bytes: bytes) -> str:
    """Rebuild source text from a token stream (used by LIST).

    A space is inserted only where two tokens would otherwise run together into
    something that reads as one word.
    """
    out = ""
    index = 0
    while index < len(token_bytes):
        opcode = token_bytes[index]
        if opcode == tk.T_EOS:
            break
        if opcode == tk.T_INTEGER:
            value = token_bytes[index + 1] | (token_bytes[index + 2] << 8)
            if value & 0x8000:
                value -= 0x10000
            piece = str(value)
            index += 3
        elif opcode == tk.T_STRING:
            count = token_bytes[index + 1]
            body = token_bytes[index + 2 : index + 2 + count].decode("ascii", "replace")
            index += 2 + count
            # REM keeps its text bare; every other string literal is quoted.
            piece = body if out.rstrip().endswith("REM") else f'"{body}"'
        elif opcode == tk.T_VARIABLE:
            name = chr(token_bytes[index + 1])
            if token_bytes[index + 2]:
                name += chr(token_bytes[index + 2])
            piece = name
            index += 3
        else:
            piece = tk.SPELLING.get(opcode, "?")
            index += 1
        if out and _runs_together(out[-1], piece[0]):
            out += " "
        out += piece
    return out


def _runs_together(previous: str, following: str) -> bool:
    return previous.isalnum() and following.isalnum()
