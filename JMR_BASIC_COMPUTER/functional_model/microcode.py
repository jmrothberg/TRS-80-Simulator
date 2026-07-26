"""Microcode ROM and the micro-instruction set.

Constitution, MICROCODE:

    The processor is microcoded.
    Each BASIC command dispatches into microcode.
    Microcode is stored in Block RAM.
    Microcode is part of the architecture.

Reading order for this file:

* `MicroOp` -- the micro-instruction set.  Each one is a single step the
  hardware can do in a few cycles: touch the token stream, run the Expression
  Engine, move a register, branch on the condition flag.
* `MicrocodeAssembler` -- assembles routines and records where each BASIC token
  enters, which *is* the dispatch table on the architecture diagram.
* `build_microcode()` -- the ROM contents: one routine per BASIC command.

Nothing here executes anything.  `sequencer.py` is the machine that runs it.

The routines are the readable form of the diagram's example:

    PRINT -> PRINT microcode -> evaluate expression -> convert to characters
          -> write to VRAM -> return
"""

from __future__ import annotations

from dataclasses import dataclass

from . import tokens as tk

#: Microcode lives at the top of System ROM.  Entry addresses print like the
#: "PRINT -> 0x012A" example on the architecture diagram.
MICROCODE_BASE = 0x0100


class MicroOp:
    """The micro-instruction set."""

    # -- sequencing --------------------------------------------------------
    NOP = "NOP"
    JUMP = "JUMP"  # arg: micro address
    BRANCH_IF = "BRANCH_IF"  # arg: micro address, taken when COND
    BRANCH_IF_NOT = "BRANCH_IF_NOT"  # arg: micro address, taken when not COND
    END_STMT = "END_STMT"  # done; a separator must follow
    NEXT_STATEMENT = "NEXT_STATEMENT"  # done; a new statement starts here
    HALT = "HALT"  # stop the program (END / STOP)

    # -- token stream ------------------------------------------------------
    MATCH = "MATCH"  # arg: token that must be present
    SKIP_TOKEN = "SKIP_TOKEN"
    SKIP_TO_EOL = "SKIP_TO_EOL"
    TEST_TOKEN = "TEST_TOKEN"  # arg: token -> COND
    TEST_STMT_END = "TEST_STMT_END"  # -> COND
    ACCEPT_THEN = "ACCEPT_THEN"  # consume an optional THEN / GOTO

    # -- values and registers ---------------------------------------------
    EVAL = "EVAL"  # Expression Engine -> ACC
    READ_LINE_NUMBER = "READ_LINE_NUMBER"  # a literal line number -> ACC
    LOAD_ACC = "LOAD_ACC"  # arg: constant -> ACC
    TEST_ACC = "TEST_ACC"  # COND = ACC is non-zero
    TEST_TEMP = "TEST_TEMP"  # COND = TMP is non-zero
    LOAD_TEMP = "LOAD_TEMP"  # arg: constant -> TMP
    SAVE_ACC = "SAVE_ACC"  # arg: scratch index
    LOAD_SCRATCH = "LOAD_SCRATCH"  # arg: scratch index, arg2: constant
    COPY_SCRATCH = "COPY_SCRATCH"  # arg: source index, arg2: destination index

    # -- variables ---------------------------------------------------------
    READ_VAR_NAME = "READ_VAR_NAME"  # consume a variable token -> NAME, ADDR
    CLEAR_NAME = "CLEAR_NAME"
    STORE_VAR = "STORE_VAR"  # [ADDR] = ACC

    # -- flow --------------------------------------------------------------
    GOTO_ACC = "GOTO_ACC"
    GOSUB_ACC = "GOSUB_ACC"
    DO_RETURN = "DO_RETURN"
    FOR_BEGIN = "FOR_BEGIN"  # COND = the body runs
    NEXT_ITERATION = "NEXT_ITERATION"  # COND = we looped back
    SKIP_TO_NEXT = "SKIP_TO_NEXT"
    READ_DATA = "READ_DATA"  # next DATA item -> ACC
    RESTORE_ACC = "RESTORE_ACC"

    # -- print -------------------------------------------------------------
    PRINT_AT = "PRINT_AT"  # optional "@ expr ," cursor move
    PRINT_VALUE = "PRINT_VALUE"  # ACC -> characters -> VRAM
    PRINT_SEP = "PRINT_SEP"  # "," or ";" -> COND and TMP
    PRINT_NL = "PRINT_NL"

    # -- input -------------------------------------------------------------
    INPUT_PROMPT = "INPUT_PROMPT"
    INPUT_LINE = "INPUT_LINE"  # stalls until the console has a line
    INPUT_FIELD = "INPUT_FIELD"  # next field of that line -> ACC

    # -- devices and system ------------------------------------------------
    CLS = "CLS"
    GFX_SET = "GFX_SET"  # scratch0 = x, scratch1 = y
    GFX_RESET = "GFX_RESET"
    POKE = "POKE"  # scratch0 = address, ACC = value
    DIM_ARRAY = "DIM_ARRAY"  # NAME + ACC -> Array Engine
    LIST = "LIST"  # scratch0 = first line, scratch1 = last line
    NEW = "NEW"
    RUN = "RUN"
    SAVE = "SAVE"  # ACC = file name
    LOAD = "LOAD"


@dataclass(frozen=True)
class MicroInstruction:
    op: str
    arg: int | str | None = None
    arg2: int | None = None
    comment: str = ""

    def __str__(self) -> str:  # pragma: no cover - listing aid
        parts = [self.op]
        if self.arg is not None:
            parts.append(self._format_arg())
        if self.arg2 is not None:
            parts.append(str(self.arg2))
        text = " ".join(parts)
        return f"{text:<36}; {self.comment}" if self.comment else text

    def _format_arg(self) -> str:
        if self.op in (MicroOp.JUMP, MicroOp.BRANCH_IF, MicroOp.BRANCH_IF_NOT):
            return f"{self.arg:#06x}" if isinstance(self.arg, int) else str(self.arg)
        if self.op in (MicroOp.MATCH, MicroOp.TEST_TOKEN):
            return token_name(self.arg)
        return str(self.arg)


#: Names for the structural tokens, which have no spelling in the language.
_STRUCTURAL_NAMES = {
    tk.T_EOS: "<end>",
    tk.T_INTEGER: "<integer>",
    tk.T_STRING: "<string>",
    tk.T_VARIABLE: "<variable>",
}


def token_name(opcode: int) -> str:
    if opcode in _STRUCTURAL_NAMES:
        return _STRUCTURAL_NAMES[opcode]
    return tk.SPELLING.get(opcode, hex(opcode))


class MicrocodeAssembler:
    """Assembles micro-instructions and builds the dispatch table."""

    def __init__(self, base: int = MICROCODE_BASE) -> None:
        self.base = base
        self.instructions: list[MicroInstruction] = []
        self.labels: dict[str, int] = {}
        self.dispatch: dict[int, int] = {}

    @property
    def address(self) -> int:
        return self.base + len(self.instructions)

    def entry(self, token: int, label: str | None = None) -> None:
        """Mark this address as the dispatch entry for a BASIC token."""
        if token in self.dispatch:
            raise ValueError(f"token {token:#04x} already has a dispatch entry")
        self.dispatch[token] = self.address
        if label:
            self.label(label)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate microcode label {name!r}")
        self.labels[name] = self.address

    def emit(self, op: str, arg=None, arg2=None, comment: str = "") -> None:
        self.instructions.append(MicroInstruction(op, arg, arg2, comment))

    def build(self) -> tuple[dict[int, MicroInstruction], dict[int, int]]:
        """Resolve labels and return (ROM, dispatch table)."""
        rom: dict[int, MicroInstruction] = {}
        for offset, instruction in enumerate(self.instructions):
            if instruction.op in (MicroOp.JUMP, MicroOp.BRANCH_IF, MicroOp.BRANCH_IF_NOT):
                target = instruction.arg
                if isinstance(target, str):
                    if target not in self.labels:
                        raise ValueError(f"undefined microcode label {target!r}")
                    instruction = MicroInstruction(
                        instruction.op, self.labels[target], instruction.arg2, instruction.comment
                    )
            rom[self.base + offset] = instruction
        return rom, dict(self.dispatch)


def build_microcode() -> tuple[dict[int, MicroInstruction], dict[int, int]]:
    """The microcode ROM image: one routine per BASIC command."""
    asm = MicrocodeAssembler()
    _let(asm)
    _print(asm)
    _input(asm)
    _if(asm)
    _goto(asm)
    _gosub(asm)
    _return(asm)
    _for(asm)
    _next(asm)
    _end(asm)
    _rem(asm)
    _read(asm)
    _data(asm)
    _restore(asm)
    _dim(asm)
    _cls(asm)
    _set(asm)
    _reset(asm)
    _poke(asm)
    _save(asm)
    _load(asm)
    _run(asm)
    _list(asm)
    _new(asm)
    return asm.build()


# --------------------------------------------------------------------------
# The routines
# --------------------------------------------------------------------------


def _let(asm: MicrocodeAssembler) -> None:
    """LET V = expr.  Entered with the variable token still at the pointer, so
    an implied LET (`A=1`) dispatches straight here."""
    asm.entry(tk.T_LET, "let")
    asm.emit(MicroOp.READ_VAR_NAME, comment="ADDR = variable slot")
    asm.emit(MicroOp.MATCH, tk.T_EQUAL)
    asm.emit(MicroOp.EVAL, comment="shared Expression Engine")
    asm.emit(MicroOp.STORE_VAR)
    asm.emit(MicroOp.END_STMT)


def _print(asm: MicrocodeAssembler) -> None:
    """PRINT [@ pos,] item [ ; | , item ] ..."""
    asm.entry(tk.T_PRINT, "print")
    asm.emit(MicroOp.LOAD_TEMP, 0, comment="TMP: no separator seen yet")
    asm.emit(MicroOp.PRINT_AT, comment="optional PRINT@ cursor move")
    asm.label("print_loop")
    asm.emit(MicroOp.TEST_STMT_END)
    asm.emit(MicroOp.BRANCH_IF, "print_end")
    asm.emit(MicroOp.EVAL, comment="evaluate the item")
    asm.emit(MicroOp.PRINT_VALUE, comment="convert to characters, write to VRAM")
    asm.emit(MicroOp.PRINT_SEP, comment="COND = a separator followed")
    asm.emit(MicroOp.BRANCH_IF, "print_loop")
    asm.label("print_end")
    asm.emit(MicroOp.TEST_TEMP, comment="did the list end with , or ; ?")
    asm.emit(MicroOp.BRANCH_IF, "print_done")
    asm.emit(MicroOp.PRINT_NL)
    asm.label("print_done")
    asm.emit(MicroOp.END_STMT)


def _input(asm: MicrocodeAssembler) -> None:
    """INPUT ["prompt";] var [, var] ..."""
    asm.entry(tk.T_INPUT, "input")
    asm.emit(MicroOp.INPUT_PROMPT, comment="optional literal prompt")
    asm.emit(MicroOp.INPUT_LINE, comment="stalls here until a line arrives")
    asm.label("input_loop")
    asm.emit(MicroOp.READ_VAR_NAME)
    asm.emit(MicroOp.INPUT_FIELD, comment="next field of the input line -> ACC")
    asm.emit(MicroOp.STORE_VAR)
    asm.emit(MicroOp.TEST_TOKEN, tk.T_COMMA)
    asm.emit(MicroOp.BRANCH_IF_NOT, "input_done")
    asm.emit(MicroOp.SKIP_TOKEN)
    asm.emit(MicroOp.JUMP, "input_loop")
    asm.label("input_done")
    asm.emit(MicroOp.END_STMT)


def _if(asm: MicrocodeAssembler) -> None:
    """IF expr THEN line | statements.  Level II has no ELSE: a false condition
    abandons the rest of the line."""
    asm.entry(tk.T_IF, "if")
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.TEST_ACC)
    asm.emit(MicroOp.BRANCH_IF, "if_true")
    asm.emit(MicroOp.SKIP_TO_EOL, comment="false: the line is over")
    asm.emit(MicroOp.END_STMT)
    asm.label("if_true")
    asm.emit(MicroOp.ACCEPT_THEN)
    asm.emit(MicroOp.TEST_TOKEN, tk.T_INTEGER, comment="THEN 100 is a GOTO")
    asm.emit(MicroOp.BRANCH_IF_NOT, "if_body")
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.GOTO_ACC)
    asm.emit(MicroOp.END_STMT)
    asm.label("if_body")
    asm.emit(MicroOp.NEXT_STATEMENT, comment="run the rest of the line")


def _goto(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_GOTO, "goto")
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.GOTO_ACC)
    asm.emit(MicroOp.END_STMT)


def _gosub(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_GOSUB, "gosub")
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.GOSUB_ACC, comment="push the return point, then branch")
    asm.emit(MicroOp.END_STMT)


def _return(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_RETURN, "return")
    asm.emit(MicroOp.DO_RETURN)
    asm.emit(MicroOp.END_STMT)


def _for(asm: MicrocodeAssembler) -> None:
    """FOR v = start TO limit [STEP n]"""
    asm.entry(tk.T_FOR, "for")
    asm.emit(MicroOp.READ_VAR_NAME, comment="control variable")
    asm.emit(MicroOp.MATCH, tk.T_EQUAL)
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.SAVE_ACC, 0, comment="start")
    asm.emit(MicroOp.MATCH, tk.T_TO)
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.SAVE_ACC, 1, comment="limit")
    asm.emit(MicroOp.LOAD_SCRATCH, 2, 1, comment="default STEP 1")
    asm.emit(MicroOp.TEST_TOKEN, tk.T_STEP)
    asm.emit(MicroOp.BRANCH_IF_NOT, "for_begin")
    asm.emit(MicroOp.SKIP_TOKEN)
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.SAVE_ACC, 2, comment="step")
    asm.label("for_begin")
    asm.emit(MicroOp.FOR_BEGIN, comment="push the frame; COND = body runs")
    asm.emit(MicroOp.BRANCH_IF, "for_enter")
    asm.emit(MicroOp.SKIP_TO_NEXT, comment="the loop is already finished")
    asm.label("for_enter")
    asm.emit(MicroOp.END_STMT)


def _next(asm: MicrocodeAssembler) -> None:
    """NEXT [v [, v] ...]"""
    asm.entry(tk.T_NEXT, "next")
    asm.label("next_item")
    asm.emit(MicroOp.CLEAR_NAME, comment="a bare NEXT closes the innermost loop")
    asm.emit(MicroOp.TEST_TOKEN, tk.T_VARIABLE)
    asm.emit(MicroOp.BRANCH_IF_NOT, "next_step")
    asm.emit(MicroOp.READ_VAR_NAME)
    asm.label("next_step")
    asm.emit(MicroOp.NEXT_ITERATION, comment="COND = looped back into the body")
    asm.emit(MicroOp.BRANCH_IF, "next_done")
    asm.emit(MicroOp.TEST_TOKEN, tk.T_COMMA, comment="NEXT I,J")
    asm.emit(MicroOp.BRANCH_IF_NOT, "next_done")
    asm.emit(MicroOp.SKIP_TOKEN)
    asm.emit(MicroOp.JUMP, "next_item")
    asm.label("next_done")
    asm.emit(MicroOp.END_STMT)


def _end(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_END, "end")
    asm.emit(MicroOp.HALT)
    asm.entry(tk.T_STOP, "stop")
    asm.emit(MicroOp.HALT)


def _rem(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_REM, "rem")
    asm.emit(MicroOp.SKIP_TO_EOL)
    asm.emit(MicroOp.END_STMT)


def _read(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_READ, "read")
    asm.label("read_loop")
    asm.emit(MicroOp.READ_VAR_NAME)
    asm.emit(MicroOp.READ_DATA)
    asm.emit(MicroOp.STORE_VAR)
    asm.emit(MicroOp.TEST_TOKEN, tk.T_COMMA)
    asm.emit(MicroOp.BRANCH_IF_NOT, "read_done")
    asm.emit(MicroOp.SKIP_TOKEN)
    asm.emit(MicroOp.JUMP, "read_loop")
    asm.label("read_done")
    asm.emit(MicroOp.END_STMT)


def _data(asm: MicrocodeAssembler) -> None:
    """DATA is not executed; the Flow Engine reads it where it lies."""
    asm.entry(tk.T_DATA, "data")
    asm.emit(MicroOp.SKIP_TO_EOL)
    asm.emit(MicroOp.END_STMT)


def _restore(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_RESTORE, "restore")
    asm.emit(MicroOp.LOAD_ACC, 0, comment="0 = rewind to the first DATA")
    asm.emit(MicroOp.TEST_STMT_END)
    asm.emit(MicroOp.BRANCH_IF, "restore_go")
    asm.emit(MicroOp.EVAL, comment="RESTORE 100")
    asm.label("restore_go")
    asm.emit(MicroOp.RESTORE_ACC)
    asm.emit(MicroOp.END_STMT)


def _dim(asm: MicrocodeAssembler) -> None:
    """DIM has its dispatch entry now; the Array Engine fills it in at step 18."""
    asm.entry(tk.T_DIM, "dim")
    asm.emit(MicroOp.READ_VAR_NAME)
    asm.emit(MicroOp.MATCH, tk.T_LPAREN)
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.MATCH, tk.T_RPAREN)
    asm.emit(MicroOp.DIM_ARRAY)
    asm.emit(MicroOp.END_STMT)


def _cls(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_CLS, "cls")
    asm.emit(MicroOp.CLS)
    asm.emit(MicroOp.END_STMT)


def _point_pair(asm: MicrocodeAssembler) -> None:
    """The shared "(x,y)" address decode used by SET and RESET."""
    asm.emit(MicroOp.MATCH, tk.T_LPAREN)
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.SAVE_ACC, 0, comment="x")
    asm.emit(MicroOp.MATCH, tk.T_COMMA)
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.SAVE_ACC, 1, comment="y")
    asm.emit(MicroOp.MATCH, tk.T_RPAREN)


def _set(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_SET, "set")
    _point_pair(asm)
    asm.emit(MicroOp.GFX_SET)
    asm.emit(MicroOp.END_STMT)


def _reset(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_RESET, "reset")
    _point_pair(asm)
    asm.emit(MicroOp.GFX_RESET)
    asm.emit(MicroOp.END_STMT)


def _poke(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_POKE, "poke")
    asm.emit(MicroOp.EVAL)
    asm.emit(MicroOp.SAVE_ACC, 0, comment="address")
    asm.emit(MicroOp.MATCH, tk.T_COMMA)
    asm.emit(MicroOp.EVAL, comment="value")
    asm.emit(MicroOp.POKE)
    asm.emit(MicroOp.END_STMT)


def _save(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_SAVE, "save")
    asm.emit(MicroOp.EVAL, comment="file name")
    asm.emit(MicroOp.SAVE)
    asm.emit(MicroOp.END_STMT)


def _load(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_LOAD, "load")
    asm.emit(MicroOp.EVAL, comment="file name")
    asm.emit(MicroOp.LOAD)
    asm.emit(MicroOp.END_STMT)


def _run(asm: MicrocodeAssembler) -> None:
    """RUN [line]"""
    asm.entry(tk.T_RUN, "run")
    asm.emit(MicroOp.LOAD_ACC, 0)
    asm.emit(MicroOp.TEST_STMT_END)
    asm.emit(MicroOp.BRANCH_IF, "run_go")
    asm.emit(MicroOp.EVAL)
    asm.label("run_go")
    asm.emit(MicroOp.RUN, comment="clear variables, branch to the first line")
    asm.emit(MicroOp.END_STMT)


def _list(asm: MicrocodeAssembler) -> None:
    """LIST | LIST n | LIST n- | LIST n-m | LIST -m"""
    asm.entry(tk.T_LIST, "list")
    asm.emit(MicroOp.LOAD_SCRATCH, 0, 0, comment="first line")
    asm.emit(MicroOp.LOAD_SCRATCH, 1, 0xFFFF, comment="last line")
    asm.emit(MicroOp.TEST_STMT_END)
    asm.emit(MicroOp.BRANCH_IF, "list_go")
    asm.emit(MicroOp.TEST_TOKEN, tk.T_MINUS)
    asm.emit(MicroOp.BRANCH_IF, "list_range")
    # A literal, not an expression: in "LIST 20-30" the dash is a range mark,
    # so the Expression Engine must not be allowed to read it as a subtraction.
    asm.emit(MicroOp.READ_LINE_NUMBER)
    asm.emit(MicroOp.SAVE_ACC, 0)
    asm.emit(MicroOp.COPY_SCRATCH, 0, 1, comment="LIST n lists one line")
    asm.emit(MicroOp.TEST_TOKEN, tk.T_MINUS)
    asm.emit(MicroOp.BRANCH_IF_NOT, "list_go")
    asm.label("list_range")
    asm.emit(MicroOp.SKIP_TOKEN, comment="the dash")
    asm.emit(MicroOp.LOAD_SCRATCH, 1, 0xFFFF)
    asm.emit(MicroOp.TEST_STMT_END)
    asm.emit(MicroOp.BRANCH_IF, "list_go")
    asm.emit(MicroOp.READ_LINE_NUMBER)
    asm.emit(MicroOp.SAVE_ACC, 1)
    asm.label("list_go")
    asm.emit(MicroOp.LIST)
    asm.emit(MicroOp.END_STMT)


def _new(asm: MicrocodeAssembler) -> None:
    asm.entry(tk.T_NEW, "new")
    asm.emit(MicroOp.NEW)
    asm.emit(MicroOp.END_STMT)


def listing(rom: dict[int, MicroInstruction], dispatch: dict[int, int]) -> str:
    """A human-readable dump of the ROM, with the dispatch entries marked."""
    entry_names = {address: tk.SPELLING.get(token, hex(token)) for token, address in dispatch.items()}
    out = []
    for address in sorted(rom):
        marker = f"{entry_names[address]}:" if address in entry_names else ""
        out.append(f"{address:#06x}  {marker:<10}{rom[address]}")
    return "\n".join(out)
