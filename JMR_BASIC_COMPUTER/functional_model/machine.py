"""The JMR BASIC Computer, assembled.

This module is the wiring diagram: it builds one of each engine, hands each one
the collaborators it is allowed to talk to, and offers the host front end four
entry points -- `boot`, `tick`, `type_line` and `screen_text`.

It deliberately contains no BASIC semantics.  If you find yourself adding an
`if token ==` here, it belongs in the microcode.
"""

from __future__ import annotations

from pathlib import Path

from . import memory_map as mm
from . import tokens as tk
from .console import Console
from .engines.array_engine import ArrayEngine
from .engines.expression_engine import ExpressionEngine
from .engines.flow_engine import FlowEngine
from .engines.graphics_engine import GraphicsEngine
from .engines.keyboard_engine import KeyboardEngine
from .engines.print_engine import PrintEngine
from .engines.storage_engine import HostFileBackend, StorageBackend, StorageEngine
from .engines.string_engine import StringEngine
from .engines.variable_engine import VariableEngine
from .engines.video_engine import VideoEngine
from .errors import BasicError, UNDEFINED_LINE
from .memory import Memory
from .microcode import build_microcode
from .program_memory import ProgramMemory
from .registers import Registers
from .sequencer import ProgramControlUnit, Status
from .token_stream import TokenStream
from .tokenizer import Tokenizer, detokenize
from .uart import Uart

BANNER = "JMR LEVEL II BASIC"


class Machine:
    def __init__(self, storage_backend: StorageBackend | None = None) -> None:
        # -- memory and registers -----------------------------------------
        self.memory = Memory()
        self.registers = Registers()
        self.stream = TokenStream(self.memory, self.registers)

        # -- microcode ROM and dispatch table ------------------------------
        self.microcode_rom, self.dispatch = build_microcode()

        # -- subsystems ----------------------------------------------------
        self.program = ProgramMemory(self.memory)
        self.tokenizer = Tokenizer()
        self.video = VideoEngine(self.memory)
        self.printer = PrintEngine(self.video)
        self.graphics = GraphicsEngine(self.video)
        self.variables = VariableEngine(self.memory)
        self.arrays = ArrayEngine(self.memory)
        self.strings = StringEngine(self.memory)
        self.expression = ExpressionEngine(
            self.memory,
            self.registers,
            self.stream,
            self.variables,
            self.strings,
            self.graphics,
        )
        self.flow = FlowEngine(
            self.memory, self.registers, self.stream, self.program, self.variables
        )
        self.keyboard = KeyboardEngine(self.memory)
        self.uart = Uart(self.memory)
        self.console = Console(self.memory, self.keyboard, self.printer, self.video)
        self.storage = StorageEngine(
            self.memory,
            storage_backend or HostFileBackend(Path(__file__).resolve().parent.parent / "storage"),
        )

        # -- processor -----------------------------------------------------
        self.pcu = ProgramControlUnit(self)
        # A running program is executed in slices so the host stays responsive
        # and BREAK works; None runs a statement sequence to completion.
        self.statement_limit: int | None = None
        self.break_requested = False

    # ---------------------------------------------------------------- boot

    def boot(self) -> None:
        self.video.clear()
        self.new_program()
        self.printer.print_line(BANNER)
        self.console.ready()
        self.console.prompt()

    def reset(self) -> None:
        self.console.reset()
        self.keyboard.clear()
        self.boot()

    # ---------------------------------------------------------- host input

    def receive(self, text: str) -> None:
        """Bytes from the host arrive at the UART, as they will on the board."""
        self.uart.receive(text)

    def type_line(self, text: str) -> None:
        """Type a line and let the machine settle (the test and script path)."""
        self.receive(text + "\r")
        self.run_until_idle()

    def tick(self) -> Status:
        """One pass of the host loop: move bytes, edit the line, run BASIC."""
        self.uart.poll(self.keyboard)
        self.console.poll()

        if self.pcu.status in (Status.WAITING_INPUT, Status.RUNNING):
            self._execute()
            return self.pcu.status

        line = self.console.take_line()
        if line is not None:
            self.execute_line(line)
        return self.pcu.status

    def run_until_idle(self, max_ticks: int = 100000) -> None:
        for _ in range(max_ticks):
            waiting = self.pcu.status is Status.WAITING_INPUT
            pending = (
                bool(self.uart.rx)
                or self.keyboard.key_available
                or self.console.has_line
                or self.pcu.status is Status.RUNNING
            )
            if not pending and not waiting:
                return
            before = (len(self.uart.rx), len(self.console.completed), self.pcu.status)
            self.tick()
            if waiting and (len(self.uart.rx), len(self.console.completed), self.pcu.status) == before:
                return  # still waiting for input that has not been typed yet

    # ------------------------------------------------------- line handling

    def execute_line(self, text: str) -> None:
        """Command Detector: a numbered line is filed, anything else runs now."""
        try:
            tokenized = self.tokenizer.tokenize(text)
        except BasicError as error:
            self._report(error)
            return

        if tokenized.is_program_line:
            try:
                self.program.store(tokenized.line_number, tokenized.token_bytes)
            except BasicError as error:
                self._report(error)
                return
            self.console.prompt()
            return

        if tokenized.is_empty:
            self.console.prompt()
            return

        self._load_direct_statement(tokenized.token_bytes)
        self._execute()

    def _load_direct_statement(self, token_bytes: bytes) -> None:
        """Build a one-line record in the direct statement buffer and enter it."""
        buffer = mm.DIRECT_STATEMENT_BUFFER
        self.memory.write_word(buffer, 0)
        self.memory.write(buffer + 2, len(token_bytes))
        self.memory.write_block(buffer + mm.LINE_HEADER_SIZE, token_bytes)
        self.registers.line_address = buffer
        self.registers.line_number = 0
        self.registers.token_pointer = buffer + mm.LINE_HEADER_SIZE
        self.registers.running = False
        self.registers.stalled = False
        self.memory.current_line = 0

    def _execute(self) -> None:
        try:
            status = self.pcu.run(self.statement_limit)
        except BasicError as error:
            self._report(error)
            return
        if status is Status.WAITING_INPUT:
            return
        if status is Status.RUNNING:
            # The slice ended with the program still going.
            if self.break_requested:
                self._break()
            return
        self.console.ready()
        self.console.prompt()

    def request_break(self) -> None:
        """The host's BREAK key; honoured at the end of the current slice."""
        self.break_requested = True

    def _break(self) -> None:
        self.break_requested = False
        self.registers.running = False
        self.registers.stalled = False
        self.pcu.status = Status.HALTED
        self.printer.print_line(f"BREAK IN {self.registers.line_number}")
        self.console.ready()
        self.console.prompt()

    def _report(self, error: BasicError) -> None:
        self.registers.running = False
        self.registers.stalled = False
        self.pcu.status = Status.HALTED
        self.printer.print_line(error.message(self.registers.line_number))
        self.console.ready()
        self.console.prompt()

    # ------------------------------------------- operations the microcode calls

    def new_program(self) -> None:
        self.program.clear()
        self.variables.clear()
        self.arrays.clear()
        self.strings.clear()
        self.flow.reset()
        self.expression.reset()
        self.registers.running = False

    def start_program(self, line_number: int = 0) -> None:
        """RUN: clear variables and enter the first line."""
        self.variables.clear()
        self.arrays.clear()
        self.strings.clear()
        self.flow.reset()
        self.expression.reset()

        if line_number:
            record = self.program.find(line_number)
            if record is None:
                raise BasicError(UNDEFINED_LINE, str(line_number))
        else:
            record = self.program.first_line()
        if record is None:
            self.registers.running = False
            return
        self.registers.running = True
        self.flow.enter_line(record.address)

    def list_program(self, first: int = 0, last: int = 0xFFFF) -> None:
        for record in self.program.lines():
            if first <= record.number <= last:
                text = detokenize(self.program.tokens_of(record))
                self.printer.print_line(f"{record.number} {text}")

    def save_program(self, name: str) -> None:
        image = self.memory.read_block(mm.PROGRAM_BASE, self.program.bytes_used)
        self.storage.save_image(name, image)

    def load_program(self, name: str) -> None:
        data = self.storage.load_image(name)
        if self.storage.is_program_image(data):
            image = self.storage.strip_magic(data)
            self.new_program()
            self.memory.write_block(mm.PROGRAM_BASE, image)
            self.memory.program_end = mm.PROGRAM_BASE + len(image)
            return
        # Not an image: it is source text, so it goes through the Tokenizer the
        # same way typing it would.
        self.new_program()
        for line in data.decode("ascii", "replace").splitlines():
            if not line.strip():
                continue
            tokenized = self.tokenizer.tokenize(line)
            if tokenized.is_program_line:
                self.program.store(tokenized.line_number, tokenized.token_bytes)

    # ------------------------------------------------------------ readback

    def screen_text(self, graphics_as: str = "hash") -> str:
        return self.video.screen_text(graphics_as)

    def screen_lines(self, graphics_as: str = "hash") -> list[str]:
        return self.video.text_lines(graphics_as)

    def program_text(self) -> list[str]:
        return [
            f"{record.number} {detokenize(self.program.tokens_of(record))}"
            for record in self.program.lines()
        ]

    def state(self) -> dict:
        """Everything a monitor or a test could want to look at."""
        return {
            "status": self.pcu.status,
            "registers": self.registers.snapshot(),
            "program_bytes": self.program.bytes_used,
            "variables": self.variables.items(),
            "for_depth": self.flow.for_stack.pointer,
            "gosub_depth": self.flow.gosub_stack.pointer,
        }


def dispatch_table_listing(machine: Machine) -> str:
    """Token -> microcode entry address, the diagram's DISPATCH TABLE."""
    rows = []
    for token in sorted(machine.dispatch):
        rows.append(f"{tk.SPELLING.get(token, hex(token)):<8} {token:#04x} -> {machine.dispatch[token]:#06x}")
    return "\n".join(rows)
