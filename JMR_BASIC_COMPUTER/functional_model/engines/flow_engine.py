"""Flow Engine: IF / GOTO / GOSUB / RETURN / FOR / NEXT / READ / RESTORE.

Everything that changes what the Program Control Unit executes next lives here,
and it does so by writing the PCU's registers -- no engine reaches into the
sequencer's private state.

Two stacks in the documented Stack Area:

    GOSUB return stack   [line addr][token ptr]
    FOR stack            [slot addr][limit][step][resume line][resume ptr][name]

Both are frames of fixed width so that the hardware can index them with a
counter.  The FOR loop is tested at the FOR statement, as Level II does, so
`FOR I=1 TO 0` never enters the body.
"""

from __future__ import annotations

from .. import memory_map as mm
from .. import tokens as tk
from ..errors import (
    BasicError,
    NEXT_WITHOUT_FOR,
    OUT_OF_DATA,
    RETURN_WITHOUT_GOSUB,
    UNDEFINED_LINE,
    syntax_error,
)
from ..memory import Memory, MemoryStack
from ..program_memory import ProgramMemory
from ..registers import Registers
from ..token_stream import TokenStream
from ..values import Value
from .variable_engine import VariableEngine

# FOR frame layout
FOR_SLOT = 0
FOR_LIMIT = 2
FOR_STEP = 4
FOR_RESUME_LINE = 6
FOR_RESUME_POINTER = 8
FOR_NAME0 = 10
FOR_NAME1 = 11

#: DATA pointer values that are not an address.
DATA_NOT_STARTED = 0x0000
DATA_EXHAUSTED = 0xFFFF


class FlowEngine:
    def __init__(
        self,
        memory: Memory,
        registers: Registers,
        stream: TokenStream,
        program: ProgramMemory,
        variables: VariableEngine,
    ) -> None:
        self.memory = memory
        self.registers = registers
        self.stream = stream
        self.program = program
        self.variables = variables
        self.gosub_stack = MemoryStack(
            memory,
            mm.GOSUB_STACK_BASE,
            mm.GOSUB_FRAME_SIZE,
            mm.GOSUB_STACK_DEPTH,
            "GOSUB stack",
        )
        self.for_stack = MemoryStack(
            memory, mm.FOR_STACK_BASE, mm.FOR_FRAME_SIZE, mm.FOR_STACK_DEPTH, "FOR stack"
        )

    def reset(self) -> None:
        """RUN: clear both stacks and the DATA pointer."""
        self.gosub_stack.reset()
        self.for_stack.reset()
        self.restore(0)

    # -- branching ---------------------------------------------------------

    def goto_line(self, line_number: int) -> None:
        record = self.program.find(line_number)
        if record is None:
            raise BasicError(UNDEFINED_LINE, str(line_number))
        self.enter_line(record.address)

    def enter_line(self, line_address: int) -> None:
        record = self.program.record_at(line_address)
        self.registers.line_address = record.address
        self.registers.line_number = record.number
        self.registers.token_pointer = record.tokens_address
        self.memory.current_line = record.number

    def gosub(self, line_number: int) -> None:
        frame = self.gosub_stack.push_frame()
        self.memory.write_word(frame, self.registers.line_address)
        self.memory.write_word(frame + 2, self.registers.token_pointer)
        self.goto_line(line_number)

    def do_return(self) -> None:
        if self.gosub_stack.empty:
            raise BasicError(RETURN_WITHOUT_GOSUB)
        frame = self.gosub_stack.pop_frame()
        line_address = self.memory.read_word(frame)
        pointer = self.memory.read_word(frame + 2)
        self._resume_at(line_address, pointer)

    # -- FOR / NEXT --------------------------------------------------------

    def for_begin(
        self, name0: int, name1: int, start: int, limit: int, step: int
    ) -> bool:
        """Start a loop.  Returns False when the body must be skipped entirely."""
        slot = self.variables.address_of(name0, name1)
        self.variables.write_at(slot, start)

        # Re-entering a loop with the same control variable replaces its frame,
        # which is how `GOTO` out of a loop and back in stays bounded.
        self._drop_frame_for(slot)

        if self._loop_finished(start, limit, step):
            return False

        frame = self.for_stack.push_frame()
        self.memory.write_word(frame + FOR_SLOT, slot)
        self.memory.write_signed_word(frame + FOR_LIMIT, limit)
        self.memory.write_signed_word(frame + FOR_STEP, step)
        self.memory.write_word(frame + FOR_RESUME_LINE, self.registers.line_address)
        self.memory.write_word(frame + FOR_RESUME_POINTER, self.registers.token_pointer)
        self.memory.write(frame + FOR_NAME0, name0)
        self.memory.write(frame + FOR_NAME1, name1)
        return True

    def next_iteration(self, name0: int = 0, name1: int = 0) -> None:
        """NEXT: step the control variable and either loop or fall through."""
        frame = self._frame_for_next(name0, name1)
        slot = self.memory.read_word(frame + FOR_SLOT)
        limit = self.memory.read_signed_word(frame + FOR_LIMIT)
        step = self.memory.read_signed_word(frame + FOR_STEP)

        value = self.variables.read_at(slot) + step
        self.variables.write_at(slot, value)

        if self._loop_finished(value, limit, step):
            self.for_stack.pop_frame()
            return

        self._resume_at(
            self.memory.read_word(frame + FOR_RESUME_LINE),
            self.memory.read_word(frame + FOR_RESUME_POINTER),
        )

    def skip_past_matching_next(self) -> None:
        """A loop whose body is skipped: scan forward for its NEXT."""
        depth = 0
        while True:
            if self.stream.at_end():
                if not self._advance_to_next_line():
                    raise BasicError(NEXT_WITHOUT_FOR, "FOR without NEXT")
                continue
            opcode = self.stream.peek()
            if opcode == tk.T_FOR:
                depth += 1
                self.stream.skip_token()
            elif opcode == tk.T_NEXT:
                self.stream.skip_token()
                # One NEXT can close several loops: `NEXT J,I`.  Step through
                # the list one variable at a time so we stop on ours and leave
                # the pointer just past it.
                while True:
                    if self.stream.peek() == tk.T_VARIABLE:
                        self.stream.skip_token()
                    if depth == 0:
                        return
                    depth -= 1
                    if not self.stream.accept(tk.T_COMMA):
                        break
            else:
                self.stream.skip_token()

    @staticmethod
    def _loop_finished(value: int, limit: int, step: int) -> bool:
        return value > limit if step >= 0 else value < limit

    def _frame_for_next(self, name0: int, name1: int) -> int:
        if self.for_stack.empty:
            raise BasicError(NEXT_WITHOUT_FOR)
        if name0 == 0:
            return self.for_stack.top_frame()
        # `NEXT J` when J is not innermost closes the loops in between.
        while not self.for_stack.empty:
            frame = self.for_stack.top_frame()
            if (
                self.memory.read(frame + FOR_NAME0) == name0
                and self.memory.read(frame + FOR_NAME1) == name1
            ):
                return frame
            self.for_stack.pop_frame()
        raise BasicError(NEXT_WITHOUT_FOR, chr(name0))

    def _drop_frame_for(self, slot: int) -> None:
        index = self.for_stack.pointer - 1
        while index >= 0:
            frame = self.for_stack.frame_address(index)
            if self.memory.read_word(frame + FOR_SLOT) == slot:
                self.for_stack.pointer = index
                return
            index -= 1

    # -- READ / DATA / RESTORE --------------------------------------------

    def restore(self, line_number: int = 0) -> None:
        """RESTORE: rewind the DATA pointer to the start, or to a line."""
        if line_number:
            record = self.program.find(line_number)
            if record is None:
                raise BasicError(UNDEFINED_LINE, str(line_number))
            self.memory.write_word(mm.SYSVAR_DATA_LINE, record.address)
            self.memory.write_word(mm.SYSVAR_DATA_POINTER, record.tokens_address)
        else:
            self.memory.write_word(mm.SYSVAR_DATA_LINE, 0)
            self.memory.write_word(mm.SYSVAR_DATA_POINTER, 0)

    def read_data(self) -> Value:
        """Take the next DATA item.  The DATA pointer is a system variable."""
        pointer = self.memory.read_word(mm.SYSVAR_DATA_POINTER)
        if pointer == DATA_EXHAUSTED:
            raise BasicError(OUT_OF_DATA)
        if pointer == DATA_NOT_STARTED:
            pointer = self._find_data_statement(mm.PROGRAM_BASE)
        value, pointer = self._read_data_item(pointer)
        self.memory.write_word(mm.SYSVAR_DATA_POINTER, pointer)
        return value

    def _find_data_statement(self, from_line_address: int) -> int:
        """Address of the first item of the next DATA statement at or after a line."""
        address = from_line_address
        while address < self.memory.program_end:
            record = self.program.record_at(address)
            scan = record.tokens_address
            saved = self.registers.token_pointer
            self.registers.token_pointer = scan
            try:
                while not self.stream.at_end():
                    if self.stream.peek() == tk.T_DATA:
                        self.stream.skip_token()
                        found = self.registers.token_pointer
                        self.memory.write_word(mm.SYSVAR_DATA_LINE, record.address)
                        return found
                    self.stream.skip_token()
            finally:
                self.registers.token_pointer = saved
            address = record.next_address
        raise BasicError(OUT_OF_DATA)

    def _read_data_item(self, pointer: int) -> tuple[Value, int]:
        saved = self.registers.token_pointer
        self.registers.token_pointer = pointer
        try:
            negate = self.stream.accept(tk.T_MINUS)
            opcode = self.stream.peek()
            if opcode == tk.T_INTEGER:
                number = self.stream.read_integer()
                value = Value.of_integer(-number if negate else number)
            elif opcode == tk.T_STRING:
                if negate:
                    raise syntax_error("bad DATA item")
                value = Value.of_string(self.stream.read_string())
            else:
                raise syntax_error("bad DATA item")

            if self.stream.accept(tk.T_COMMA):
                return value, self.registers.token_pointer
            # This DATA statement is exhausted; find the next one.
            line_address = self.memory.read_word(mm.SYSVAR_DATA_LINE)
            record = self.program.record_at(line_address)
            try:
                return value, self._find_data_statement(record.next_address)
            except BasicError:
                return value, DATA_EXHAUSTED  # the next READ reports ?OD
        finally:
            self.registers.token_pointer = saved

    # -- helpers -----------------------------------------------------------

    def _resume_at(self, line_address: int, pointer: int) -> None:
        self.registers.line_address = line_address
        self.registers.token_pointer = pointer
        if line_address >= mm.PROGRAM_BASE and line_address < mm.PROGRAM_TOP:
            self.registers.line_number = self.memory.read_word(line_address)
        else:
            self.registers.line_number = 0
        self.memory.current_line = self.registers.line_number

    def _advance_to_next_line(self) -> bool:
        record = self.program.record_at(self.registers.line_address)
        following = self.program.line_after(record)
        if following is None:
            return False
        self.enter_line(following.address)
        return True
