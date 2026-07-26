"""Expression Engine.

Constitution, SHARED ENGINES:

    PRINT / LET / IF / FOR all share one Expression Engine.

Nothing else in the machine evaluates anything.  A microcode routine that needs
a value executes the EVAL micro-operation and reads the accumulator.

The evaluator is a shunting-yard machine with two stacks that live in the
documented Stack Area rather than in Python lists:

    operand stack   [kind][value lo][value hi]      at EXPR_OPERAND_STACK_BASE
    operator stack  [token][argument count]         at EXPR_OPERATOR_STACK_BASE

That is deliberate.  A recursive-descent parser is shorter to write in Python
and impossible to build out of the hardware we are heading for; this shape is a
state machine plus two Block RAMs and ports directly.

Operand kinds:
    'I'  16-bit signed integer
    'L'  string literal, value is its address in the token stream
    'S'  string in String Space, value is its address there
"""

from __future__ import annotations

from .. import memory_map as mm
from .. import tokens as tk
from ..errors import (
    BasicError,
    DIVIDE_BY_ZERO,
    ILLEGAL_FUNCTION_CALL,
    OVERFLOW,
    syntax_error,
)
from ..memory import Memory, MemoryStack
from ..registers import Registers
from ..token_stream import TokenStream
from ..values import Value
from .graphics_engine import GraphicsEngine
from .string_engine import StringEngine
from .variable_engine import VariableEngine, check_range

KIND_INTEGER = ord("I")
KIND_LITERAL = ord("L")
KIND_STRING = ord("S")

TRUE = -1  # Level II: a true comparison is -1, false is 0
FALSE = 0


class ExpressionEngine:
    def __init__(
        self,
        memory: Memory,
        registers: Registers,
        stream: TokenStream,
        variables: VariableEngine,
        strings: StringEngine,
        graphics: GraphicsEngine,
    ) -> None:
        self.memory = memory
        self.registers = registers
        self.stream = stream
        self.variables = variables
        self.strings = strings
        self.graphics = graphics
        self.operands = MemoryStack(
            memory,
            mm.EXPR_OPERAND_STACK_BASE,
            mm.EXPR_OPERAND_SLOT_SIZE,
            mm.EXPR_OPERAND_DEPTH,
            "expression operand stack",
        )
        self.operators = MemoryStack(
            memory,
            mm.EXPR_OPERATOR_STACK_BASE,
            mm.EXPR_OPERATOR_SLOT_SIZE,
            mm.EXPR_OPERATOR_DEPTH,
            "expression operator stack",
        )

    # -- public interface --------------------------------------------------

    def evaluate(self) -> Value:
        """Evaluate the expression at the token pointer and consume it."""
        operand_floor = self.operands.pointer
        operator_floor = self.operators.pointer
        try:
            self._parse(operand_floor, operator_floor)
            if self.operands.pointer != operand_floor + 1:
                raise syntax_error("malformed expression")
            return self._pop_operand()
        finally:
            self.operands.pointer = operand_floor
            self.operators.pointer = operator_floor

    def evaluate_integer(self) -> int:
        return self.evaluate().require_integer()

    def reset(self) -> None:
        self.operands.reset()
        self.operators.reset()

    # -- the shunting-yard state machine -----------------------------------

    def _parse(self, operand_floor: int, operator_floor: int) -> None:
        expect_operand = True
        depth = 0

        while True:
            opcode = self.stream.peek()

            if expect_operand:
                if opcode == tk.T_MINUS:
                    self.stream.next_token()
                    self._push_operator(tk.T_NEGATE)
                    continue
                if opcode == tk.T_PLUS:
                    self.stream.next_token()  # unary plus does nothing
                    continue
                if opcode == tk.T_NOT:
                    self.stream.next_token()
                    self._push_operator(tk.T_NOT)
                    continue
                if opcode == tk.T_LPAREN:
                    self.stream.next_token()
                    self._push_operator(tk.T_LPAREN)
                    depth += 1
                    continue
                if opcode in tk.FUNCTION_TOKENS:
                    self.stream.next_token()
                    self.stream.expect(tk.T_LPAREN)
                    self._push_operator(opcode, argument_count=1)
                    depth += 1
                    continue
                self._push_primary()
                expect_operand = False
                continue

            if opcode in tk.BINARY_OPERATORS:
                precedence, right_associative = tk.BINARY_OPERATORS[opcode]
                self._reduce_while(operator_floor, precedence, right_associative)
                self.stream.next_token()
                self._push_operator(opcode)
                expect_operand = True
                continue

            if opcode == tk.T_COMMA and depth and self._open_is_function(operator_floor):
                self._reduce_to_open(operator_floor)
                address = self.operators.top_frame()
                self.memory.write(address + 1, self.memory.read(address + 1) + 1)
                self.stream.next_token()
                expect_operand = True
                continue

            if opcode == tk.T_RPAREN and depth:
                self._reduce_to_open(operator_floor)
                address = self.operators.pop_frame()
                open_token = self.memory.read(address)
                argument_count = self.memory.read(address + 1)
                self.stream.next_token()
                depth -= 1
                if open_token != tk.T_LPAREN:
                    self._apply_function(open_token, argument_count)
                continue

            break  # anything else belongs to the statement, not the expression

        if expect_operand:
            raise syntax_error("expression ends with an operator")
        self._reduce_to_floor(operator_floor)

    def _push_primary(self) -> None:
        opcode = self.stream.peek()
        if opcode == tk.T_INTEGER:
            self._push_integer(self.stream.read_integer())
            return
        if opcode == tk.T_STRING:
            address = self.stream.pointer + 1  # the length byte
            self.stream.read_string()
            self._push_slot(KIND_LITERAL, address)
            return
        if opcode == tk.T_VARIABLE:
            name0, name1 = self.stream.read_variable_name()
            self._push_integer(self.variables.read(name0, name1))
            return
        raise syntax_error("a value was expected")

    # -- reduction ---------------------------------------------------------

    def _reduce_while(self, floor: int, precedence: int, right_associative: bool) -> None:
        while self.operators.pointer > floor:
            address = self.operators.top_frame()
            token = self.memory.read(address)
            if self._is_open(token):
                return
            stacked = self._precedence(token)
            if stacked > precedence or (stacked == precedence and not right_associative):
                self.operators.pop_frame()
                self._apply(token)
            else:
                return

    def _reduce_to_open(self, floor: int) -> None:
        while self.operators.pointer > floor:
            address = self.operators.top_frame()
            token = self.memory.read(address)
            if self._is_open(token):
                return
            self.operators.pop_frame()
            self._apply(token)
        raise syntax_error("unbalanced parentheses")

    def _reduce_to_floor(self, floor: int) -> None:
        while self.operators.pointer > floor:
            address = self.operators.pop_frame()
            token = self.memory.read(address)
            if self._is_open(token):
                raise syntax_error("unbalanced parentheses")
            self._apply(token)

    def _open_is_function(self, floor: int) -> bool:
        index = self.operators.pointer - 1
        while index >= floor:
            token = self.memory.read(self.operators.frame_address(index))
            if self._is_open(token):
                return token != tk.T_LPAREN
            index -= 1
        return False

    @staticmethod
    def _is_open(token: int) -> bool:
        return token == tk.T_LPAREN or token in tk.FUNCTION_TOKENS

    @staticmethod
    def _precedence(token: int) -> int:
        if token in tk.UNARY_OPERATORS:
            return tk.UNARY_OPERATORS[token]
        return tk.BINARY_OPERATORS[token][0]

    # -- operator application ---------------------------------------------

    def _apply(self, token: int) -> None:
        if token in tk.UNARY_OPERATORS:
            value = self._pop_integer()
            if token == tk.T_NEGATE:
                self._push_integer(-value)
            else:  # NOT is a bitwise complement, as on a Level II machine
                self._push_integer(~value)
            return

        right = self._pop_integer()
        left = self._pop_integer()

        if token == tk.T_PLUS:
            self._push_integer(left + right)
        elif token == tk.T_MINUS:
            self._push_integer(left - right)
        elif token == tk.T_STAR:
            self._push_integer(left * right)
        elif token == tk.T_SLASH:
            if right == 0:
                raise BasicError(DIVIDE_BY_ZERO, "division by zero")
            # Stage 1 is integer BASIC: divide and truncate toward zero.
            quotient = abs(left) // abs(right)
            self._push_integer(-quotient if (left < 0) != (right < 0) else quotient)
        elif token == tk.T_CARET:
            self._push_integer(self._power(left, right))
        elif token == tk.T_AND:
            self._push_integer(self._to_signed(self._to_word(left) & self._to_word(right)))
        elif token == tk.T_OR:
            self._push_integer(self._to_signed(self._to_word(left) | self._to_word(right)))
        else:
            self._push_integer(TRUE if self._compare(token, left, right) else FALSE)

    @staticmethod
    def _compare(token: int, left: int, right: int) -> bool:
        if token == tk.T_EQUAL:
            return left == right
        if token == tk.T_NOT_EQUAL:
            return left != right
        if token == tk.T_LESS:
            return left < right
        if token == tk.T_GREATER:
            return left > right
        if token == tk.T_LESS_EQUAL:
            return left <= right
        if token == tk.T_GREATER_EQUAL:
            return left >= right
        raise syntax_error("unknown operator")

    @staticmethod
    def _power(base: int, exponent: int) -> int:
        if exponent < 0:
            # Stage 1 has no fractions, so only +-1 has an integer answer here.
            if base == 1:
                return 1
            if base == -1:
                return -1 if exponent % 2 else 1
            raise BasicError(ILLEGAL_FUNCTION_CALL, "negative exponent needs floating point")
        result = 1
        for _ in range(exponent):
            result *= base
            if abs(result) > 0x7FFFFFFF:  # stop runaway growth before ?OV
                raise BasicError(OVERFLOW, "exponent overflow")
        return result

    def _apply_function(self, token: int, argument_count: int) -> None:
        expected = tk.FUNCTION_TOKENS[token]
        if argument_count != expected:
            raise syntax_error(f"{tk.SPELLING.get(token)} takes {expected} argument(s)")

        if token == tk.T_POINT:
            y = self._pop_integer()
            x = self._pop_integer()
            self._push_integer(self.graphics.point(x, y))
            return

        argument = self._pop_integer()
        if token == tk.T_PEEK:
            self._push_integer(self.memory.read(argument & 0xFFFF))
        elif token == tk.T_ABS:
            self._push_integer(abs(argument))
        elif token == tk.T_INT:
            self._push_integer(argument)  # already an integer in stage 1
        elif token == tk.T_SGN:
            self._push_integer((argument > 0) - (argument < 0))
        elif token == tk.T_RND:
            self._push_integer(self._random(argument))
        else:  # pragma: no cover - table and dispatch cannot disagree
            raise syntax_error("unknown function")

    def _random(self, limit: int) -> int:
        """RND(n) -> 1..n.  RND(0) needs floating point, so it is ?FC here."""
        if limit <= 0:
            raise BasicError(ILLEGAL_FUNCTION_CALL, "RND(0) needs floating point")
        state = self.memory.read(mm.IO_RNG_LO) | (self.memory.read(mm.IO_RNG_HI) << 8)
        if state == 0:
            state = 0xACE1
        # 16-bit xorshift: three shifts and three XORs in hardware.
        state ^= (state << 7) & 0xFFFF
        state ^= state >> 9
        state ^= (state << 8) & 0xFFFF
        self.memory.write(mm.IO_RNG_LO, state & 0xFF)
        self.memory.write(mm.IO_RNG_HI, state >> 8)
        return state % limit + 1

    # -- operand stack -----------------------------------------------------

    def _push_slot(self, kind: int, word: int) -> None:
        address = self.operands.push_frame()
        self.memory.write(address, kind)
        self.memory.write_word(address + 1, word & 0xFFFF)

    def _push_integer(self, value: int) -> None:
        self._push_slot(KIND_INTEGER, check_range(value) & 0xFFFF)

    def _push_operator(self, token: int, argument_count: int = 0) -> None:
        address = self.operators.push_frame()
        self.memory.write(address, token)
        self.memory.write(address + 1, argument_count)

    def _pop_operand(self) -> Value:
        address = self.operands.pop_frame()
        kind = self.memory.read(address)
        word = self.memory.read_word(address + 1)
        if kind == KIND_INTEGER:
            return Value.of_integer(self._to_signed(word))
        if kind == KIND_LITERAL:
            length = self.memory.read(word)
            text = self.memory.read_block(word + 1, length).decode("ascii", "replace")
            return Value.of_string(text)
        return Value.of_string(self.strings.load(word))

    def _pop_integer(self) -> int:
        return self._pop_operand().require_integer()

    @staticmethod
    def _to_word(value: int) -> int:
        return value & 0xFFFF

    @staticmethod
    def _to_signed(word: int) -> int:
        return word - 0x10000 if word & 0x8000 else word
