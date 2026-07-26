"""Program Control Unit and Micro Sequencer.

This is the PROGRAM CONTROL UNIT box on the architecture diagram:

    Program Counter (line #)
    Token Pointer (within line)
    Fetch / Decode Sequencer
    Microcode Control

and the INSTRUCTION FLOW strip underneath it:

    1. fetch next token   2. decode token   3. load microcode
    4. execute microcode  5. complete statement

`MicroSequencer` is step 4: it reads micro-instructions from the ROM and drives
the engines.  `ProgramControlUnit` is steps 1, 2, 3 and 5.

Neither of them knows what PRINT does.  That knowledge is in the microcode.
"""

from __future__ import annotations

from enum import Enum

from . import memory_map as mm
from . import tokens as tk
from .errors import BasicError, syntax_error
from .microcode import MicroInstruction, MicroOp
from .values import Value


class Outcome(Enum):
    """How a statement finished."""

    CONTINUE = "continue"  # a separator or end of line must follow
    CONTINUE_HERE = "continue_here"  # the next statement starts at the pointer
    HALT = "halt"  # END / STOP / fell off the end
    STALL = "stall"  # waiting for the console (INPUT)


class Status(Enum):
    """What the processor is doing between statements."""

    IDLE = "idle"
    RUNNING = "running"
    HALTED = "halted"
    WAITING_INPUT = "waiting_input"
    ERROR = "error"


class InputStall(Exception):
    """Raised by INPUT_LINE when the console has no line ready."""


class InputRedo(Exception):
    """Raised by INPUT_FIELD when the typed line does not fit the variables."""


class MicroSequencer:
    """Executes micro-instructions against the engines."""

    def __init__(self, machine) -> None:
        self.machine = machine
        self.registers = machine.registers
        self.rom = machine.microcode_rom
        self.handlers = {
            name: getattr(self, "_op_" + name.lower())
            for name in vars(MicroOp)
            if not name.startswith("_") and isinstance(getattr(MicroOp, name), str)
        }

    # -- running -----------------------------------------------------------

    def start(self, entry_address: int) -> Outcome:
        self.registers.micro_pc = entry_address
        self.registers.statement_entry = entry_address
        self.registers.statement_pointer = self.registers.token_pointer
        self.registers.branched = False
        return self.resume()

    def resume(self) -> Outcome:
        while True:
            address = self.registers.micro_pc
            instruction = self.rom[address]
            self.registers.micro_pc = address + 1
            try:
                outcome = self.handlers[instruction.op](instruction)
            except InputStall:
                self.registers.micro_pc = address  # re-execute on resume
                return Outcome.STALL
            except InputRedo:
                # Level II re-asks the whole INPUT statement.
                self.registers.micro_pc = self.registers.statement_entry
                self.registers.token_pointer = self.registers.statement_pointer
                return Outcome.STALL
            if outcome is not None:
                return outcome

    # -- convenience -------------------------------------------------------

    @property
    def stream(self):
        return self.machine.stream

    # -- sequencing --------------------------------------------------------

    def _op_nop(self, instruction: MicroInstruction) -> None:
        return None

    def _op_jump(self, instruction: MicroInstruction) -> None:
        self.registers.micro_pc = instruction.arg
        return None

    def _op_branch_if(self, instruction: MicroInstruction) -> None:
        if self.registers.condition:
            self.registers.micro_pc = instruction.arg
        return None

    def _op_branch_if_not(self, instruction: MicroInstruction) -> None:
        if not self.registers.condition:
            self.registers.micro_pc = instruction.arg
        return None

    def _op_end_stmt(self, instruction: MicroInstruction) -> Outcome:
        return Outcome.CONTINUE_HERE if self.registers.branched else Outcome.CONTINUE

    def _op_next_statement(self, instruction: MicroInstruction) -> Outcome:
        return Outcome.CONTINUE_HERE

    def _op_halt(self, instruction: MicroInstruction) -> Outcome:
        self.registers.running = False
        return Outcome.HALT

    # -- token stream ------------------------------------------------------

    def _op_match(self, instruction: MicroInstruction) -> None:
        self.stream.expect(instruction.arg)
        return None

    def _op_skip_token(self, instruction: MicroInstruction) -> None:
        self.stream.skip_token()
        return None

    def _op_skip_to_eol(self, instruction: MicroInstruction) -> None:
        self.stream.skip_to_end_of_line()
        return None

    def _op_test_token(self, instruction: MicroInstruction) -> None:
        self.registers.condition = self.stream.peek() == instruction.arg
        return None

    def _op_test_stmt_end(self, instruction: MicroInstruction) -> None:
        self.registers.condition = self.stream.at_statement_end()
        return None

    def _op_accept_then(self, instruction: MicroInstruction) -> None:
        if not self.stream.accept(tk.T_THEN):
            self.stream.accept(tk.T_GOTO)
        return None

    # -- values and registers ---------------------------------------------

    def _op_eval(self, instruction: MicroInstruction) -> None:
        self.registers.accumulator = self.machine.expression.evaluate()
        return None

    def _op_read_line_number(self, instruction: MicroInstruction) -> None:
        self.registers.accumulator = Value.of_integer(self.stream.read_integer() & 0xFFFF)
        return None

    def _op_load_acc(self, instruction: MicroInstruction) -> None:
        self.registers.accumulator = Value.of_integer(instruction.arg)
        return None

    def _op_test_acc(self, instruction: MicroInstruction) -> None:
        self.registers.condition = self.registers.accumulator.truthy
        return None

    def _op_test_temp(self, instruction: MicroInstruction) -> None:
        self.registers.condition = self.registers.temporary != 0
        return None

    def _op_load_temp(self, instruction: MicroInstruction) -> None:
        self.registers.temporary = instruction.arg
        return None

    def _op_save_acc(self, instruction: MicroInstruction) -> None:
        self.registers.scratch[instruction.arg] = self.registers.accumulator.require_integer()
        return None

    def _op_load_scratch(self, instruction: MicroInstruction) -> None:
        self.registers.scratch[instruction.arg] = instruction.arg2
        return None

    def _op_copy_scratch(self, instruction: MicroInstruction) -> None:
        self.registers.scratch[instruction.arg2] = self.registers.scratch[instruction.arg]
        return None

    # -- variables ---------------------------------------------------------

    def _op_read_var_name(self, instruction: MicroInstruction) -> None:
        name0, name1 = self.stream.read_variable_name()
        self.registers.name0 = name0
        self.registers.name1 = name1
        self.registers.address = self.machine.variables.address_of(name0, name1)
        return None

    def _op_clear_name(self, instruction: MicroInstruction) -> None:
        self.registers.name0 = 0
        self.registers.name1 = 0
        return None

    def _op_store_var(self, instruction: MicroInstruction) -> None:
        value = self.registers.accumulator.require_integer()
        self.machine.variables.write_at(self.registers.address, value)
        return None

    # -- flow --------------------------------------------------------------

    def _op_goto_acc(self, instruction: MicroInstruction) -> None:
        self.machine.flow.goto_line(self.registers.accumulator.require_integer())
        self.registers.branched = True
        return None

    def _op_gosub_acc(self, instruction: MicroInstruction) -> None:
        self.machine.flow.gosub(self.registers.accumulator.require_integer())
        self.registers.branched = True
        return None

    def _op_do_return(self, instruction: MicroInstruction) -> None:
        # RETURN lands just after the GOSUB statement, so a separator follows
        # and this is not a branch as far as the PCU is concerned.
        self.machine.flow.do_return()
        return None

    def _op_for_begin(self, instruction: MicroInstruction) -> None:
        registers = self.registers
        self.registers.condition = self.machine.flow.for_begin(
            registers.name0,
            registers.name1,
            registers.scratch[0],
            registers.scratch[1],
            registers.scratch[2],
        )
        return None

    def _op_next_iteration(self, instruction: MicroInstruction) -> None:
        before = (self.registers.line_address, self.registers.token_pointer)
        self.machine.flow.next_iteration(self.registers.name0, self.registers.name1)
        after = (self.registers.line_address, self.registers.token_pointer)
        self.registers.condition = before != after
        return None

    def _op_skip_to_next(self, instruction: MicroInstruction) -> None:
        self.machine.flow.skip_past_matching_next()
        return None

    def _op_read_data(self, instruction: MicroInstruction) -> None:
        self.registers.accumulator = self.machine.flow.read_data()
        return None

    def _op_restore_acc(self, instruction: MicroInstruction) -> None:
        self.machine.flow.restore(self.registers.accumulator.require_integer())
        return None

    # -- print -------------------------------------------------------------

    def _op_print_at(self, instruction: MicroInstruction) -> None:
        if self.stream.accept(tk.T_AT):
            position = self.machine.expression.evaluate_integer()
            self.machine.printer.print_at(position)
            if not self.stream.accept(tk.T_COMMA):
                self.stream.accept(tk.T_SEMICOLON)
        return None

    def _op_print_value(self, instruction: MicroInstruction) -> None:
        value = self.registers.accumulator
        if value.is_string:
            self.machine.printer.print_string(value.text)
        else:
            self.machine.printer.print_number(value.integer)
        return None

    def _op_print_sep(self, instruction: MicroInstruction) -> None:
        if self.stream.accept(tk.T_COMMA):
            self.machine.printer.next_zone()
            self.registers.temporary = 1
        elif self.stream.accept(tk.T_SEMICOLON):
            self.registers.temporary = 1
        else:
            self.registers.temporary = 0
        self.registers.condition = self.registers.temporary != 0
        return None

    def _op_print_nl(self, instruction: MicroInstruction) -> None:
        self.machine.printer.newline()
        return None

    # -- input -------------------------------------------------------------

    def _op_input_prompt(self, instruction: MicroInstruction) -> None:
        if self.stream.peek() == tk.T_STRING:
            self.machine.printer.put_text(self.stream.read_string())
            if not self.stream.accept(tk.T_SEMICOLON):
                self.stream.accept(tk.T_COMMA)
        self.machine.printer.put_text("? ")
        return None

    def _op_input_line(self, instruction: MicroInstruction) -> None:
        line = self.machine.console.take_input_line()
        if line is None:
            raise InputStall
        data = line.encode("ascii", "replace")[: mm.INPUT_LINE_BUFFER_SIZE - 1]
        self.machine.memory.write_block(mm.INPUT_LINE_BUFFER, data + b"\0")
        self.machine.memory.write_word(mm.SYSVAR_INPUT_FIELD, mm.INPUT_LINE_BUFFER)
        return None

    def _op_input_field(self, instruction: MicroInstruction) -> None:
        memory = self.machine.memory
        pointer = memory.read_word(mm.SYSVAR_INPUT_FIELD)
        field = ""
        while True:
            char = memory.read(pointer)
            if char in (0, ord(",")):
                if char:
                    pointer += 1
                break
            field += chr(char)
            pointer += 1
        memory.write_word(mm.SYSVAR_INPUT_FIELD, pointer)

        text = field.strip()
        if text in ("", "-", "+"):
            value = 0
        elif text.lstrip("+-").isdigit():
            value = int(text)
        else:
            self.machine.printer.print_line("?REDO")
            raise InputRedo
        self.registers.accumulator = Value.of_integer(value)
        return None

    # -- devices and system ------------------------------------------------

    def _op_cls(self, instruction: MicroInstruction) -> None:
        self.machine.video.clear()
        return None

    def _op_gfx_set(self, instruction: MicroInstruction) -> None:
        self.machine.graphics.set(self.registers.scratch[0], self.registers.scratch[1])
        return None

    def _op_gfx_reset(self, instruction: MicroInstruction) -> None:
        self.machine.graphics.reset(self.registers.scratch[0], self.registers.scratch[1])
        return None

    def _op_poke(self, instruction: MicroInstruction) -> None:
        address = self.registers.scratch[0] & 0xFFFF
        self.machine.memory.write(address, self.registers.accumulator.require_integer() & 0xFF)
        return None

    def _op_dim_array(self, instruction: MicroInstruction) -> None:
        self.machine.arrays.dimension(
            self.registers.name0,
            self.registers.name1,
            [self.registers.accumulator.require_integer()],
        )
        return None

    def _op_list(self, instruction: MicroInstruction) -> None:
        self.machine.list_program(self.registers.scratch[0], self.registers.scratch[1])
        return None

    def _op_new(self, instruction: MicroInstruction) -> None:
        self.machine.new_program()
        return None

    def _op_run(self, instruction: MicroInstruction) -> None:
        self.machine.start_program(self.registers.accumulator.require_integer())
        self.registers.branched = True
        return None

    def _op_save(self, instruction: MicroInstruction) -> None:
        self.machine.save_program(self.registers.accumulator.require_string())
        return None

    def _op_load(self, instruction: MicroInstruction) -> None:
        self.machine.load_program(self.registers.accumulator.require_string())
        return None


class ProgramControlUnit:
    """Fetch, decode, dispatch, complete."""

    def __init__(self, machine) -> None:
        self.machine = machine
        self.registers = machine.registers
        self.sequencer = MicroSequencer(machine)
        self.status = Status.IDLE

    @property
    def stream(self):
        return self.machine.stream

    # -- one statement -----------------------------------------------------

    def step(self) -> Status:
        registers = self.registers
        if registers.stalled:
            registers.stalled = False
            outcome = self.sequencer.resume()
        else:
            if not self._locate_statement():
                self.status = Status.HALTED
                return self.status
            outcome = self.sequencer.start(self._decode())

        if outcome is Outcome.STALL:
            registers.stalled = True
            self.status = Status.WAITING_INPUT
            return self.status
        if outcome is Outcome.HALT:
            self.status = Status.HALTED
            return self.status
        if outcome is Outcome.CONTINUE and not self.stream.at_statement_end():
            raise syntax_error("extra characters after a statement")
        self.status = Status.RUNNING
        return self.status

    def run(self, statement_limit: int | None = None) -> Status:
        """Execute statements until the machine stops or needs the console."""
        executed = 0
        while True:
            status = self.step()
            if status in (Status.HALTED, Status.WAITING_INPUT, Status.ERROR):
                return status
            executed += 1
            if statement_limit is not None and executed >= statement_limit:
                self.status = Status.RUNNING
                return self.status

    # -- 1. fetch ----------------------------------------------------------

    def _locate_statement(self) -> bool:
        """Position the token pointer on the next statement to execute."""
        stream = self.stream
        while True:
            if stream.peek() == tk.T_COLON:
                stream.next_token()
                continue
            if not stream.at_end():
                return True
            # End of the line record.
            if not self.registers.running:
                return False  # the direct statement is finished
            record = self.machine.program.record_at(self.registers.line_address)
            following = self.machine.program.line_after(record)
            if following is None:
                self.registers.running = False
                return False
            self.machine.flow.enter_line(following.address)

    # -- 2. decode / 3. load microcode -------------------------------------

    def _decode(self) -> int:
        stream = self.stream
        opcode = stream.peek()
        if opcode == tk.T_VARIABLE:
            # An implied LET: the variable token stays for the LET microcode.
            return self.machine.dispatch[tk.T_LET]
        if opcode in self.machine.dispatch:
            stream.next_token()
            return self.machine.dispatch[opcode]
        raise syntax_error(f"{tk.SPELLING.get(opcode, hex(opcode))} cannot start a statement")
