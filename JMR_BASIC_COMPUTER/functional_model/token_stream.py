"""Reading the token stream through the Token Pointer register.

Every engine that consumes tokens -- the sequencer, the microcode, the
Expression Engine -- does it through this one object, so there is exactly one
piece of logic that knows how wide each token is.  It holds no state of its
own: the position is the Token Pointer register in `Registers`.
"""

from __future__ import annotations

from . import tokens as tk
from .errors import BasicError, SYNTAX, syntax_error
from .memory import Memory
from .registers import Registers


class TokenStream:
    def __init__(self, memory: Memory, registers: Registers) -> None:
        self.memory = memory
        self.registers = registers

    # -- position ----------------------------------------------------------

    @property
    def pointer(self) -> int:
        return self.registers.token_pointer

    @pointer.setter
    def pointer(self, address: int) -> None:
        self.registers.token_pointer = address

    # -- inspection --------------------------------------------------------

    def peek(self) -> int:
        return self.memory.read(self.pointer)

    def at_end(self) -> bool:
        return self.peek() == tk.T_EOS

    def at_statement_end(self) -> bool:
        """End of line, or a colon separating statements."""
        return self.peek() in (tk.T_EOS, tk.T_COLON)

    # -- consumption -------------------------------------------------------

    def next_token(self) -> int:
        opcode = self.memory.read(self.pointer)
        self.pointer += 1
        return opcode

    def accept(self, opcode: int) -> bool:
        if self.peek() == opcode:
            self.pointer += 1
            return True
        return False

    def expect(self, opcode: int) -> None:
        if not self.accept(opcode):
            raise syntax_error(f"expected {tk.SPELLING.get(opcode, hex(opcode))}")

    def read_integer(self) -> int:
        """Consume an integer literal token (the T_INTEGER byte is at pointer)."""
        if self.next_token() != tk.T_INTEGER:
            raise syntax_error("a number was expected")
        value = self.memory.read_signed_word(self.pointer)
        self.pointer += 2
        return value

    def read_variable_name(self) -> tuple[int, int]:
        """Consume a variable reference token and return its two name bytes."""
        if self.next_token() != tk.T_VARIABLE:
            raise syntax_error("a variable was expected")
        name0 = self.memory.read(self.pointer)
        name1 = self.memory.read(self.pointer + 1)
        self.pointer += 2
        return name0, name1

    def read_string(self) -> str:
        """Consume a string literal token."""
        if self.next_token() != tk.T_STRING:
            raise BasicError(SYNTAX, "a string was expected")
        length = self.memory.read(self.pointer)
        text = self.memory.read_block(self.pointer + 1, length).decode("ascii", "replace")
        self.pointer += 1 + length
        return text

    def skip_token(self) -> None:
        """Step over the token at the pointer, whatever its width."""
        opcode = self.memory.read(self.pointer)
        operand = self.memory.read(self.pointer + 1) if opcode == tk.T_STRING else 0
        self.pointer += tk.token_length(opcode, operand)

    def skip_to_end_of_line(self) -> None:
        while not self.at_end():
            self.skip_token()

    def skip_to_statement_end(self) -> None:
        while not self.at_statement_end():
            self.skip_token()
