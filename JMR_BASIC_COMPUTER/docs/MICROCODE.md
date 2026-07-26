# Microcode

> The processor is microcoded. The programmer never sees this.
> Each BASIC command dispatches into microcode. Microcode is part of the
> architecture. — the Constitution

Print the whole ROM, with the dispatch table above it:

```bash
python3 run_jmr.py --microcode
```

## How a statement runs

The Program Control Unit fetches a token, looks it up in the dispatch table to
get a micro address, and hands control to the Micro Sequencer. The sequencer
executes micro-instructions until one of them says the statement is over.

```
token 0x81 (PRINT)
   -> dispatch table -> 0x0105
   -> micro-instructions at 0x0105 onward
   -> END_STMT
   -> back to the PCU
```

Everything a statement does is in its routine. The PCU does not know what PRINT
means, and neither does the Print Engine — the Print Engine knows how to turn a
number into characters, and the microcode is what decides that PRINT should ask
it to.

## Registers the microcode operates on

| Register | Use |
|---|---|
| `ACC` | the value the Expression Engine produced |
| `ADDR` | a variable slot address |
| `TMP` | a one-bit flag (PRINT uses it for "a separator followed") |
| `COND` | set by the `TEST_*` operations, read by the branches |
| `NAME0/NAME1` | the variable a statement is working on |
| `scratch[0..3]` | operands held across steps (`FOR` start/limit/step, `SET` x/y) |
| `micro_pc` | the micro-instruction pointer |

Plus the PCU's own line address and Token Pointer, which the flow operations
write.

## The micro-instruction set

**Sequencing**

| Op | Effect |
|---|---|
| `NOP` | nothing |
| `JUMP a` | micro_pc = a |
| `BRANCH_IF a` | micro_pc = a when COND |
| `BRANCH_IF_NOT a` | micro_pc = a when not COND |
| `END_STMT` | statement over; a separator or end of line must follow |
| `NEXT_STATEMENT` | statement over; a new one starts at the pointer |
| `HALT` | stop the program |

**Token stream**

| Op | Effect |
|---|---|
| `MATCH t` | consume token `t` or raise ?SN |
| `SKIP_TOKEN` | step over one token, whatever its width |
| `SKIP_TO_EOL` | abandon the rest of the line |
| `TEST_TOKEN t` | COND = the next token is `t` |
| `TEST_STMT_END` | COND = at `:` or end of line |
| `ACCEPT_THEN` | consume an optional `THEN` or `GOTO` |

**Values**

| Op | Effect |
|---|---|
| `EVAL` | run the Expression Engine -> ACC |
| `READ_LINE_NUMBER` | consume a literal line number -> ACC |
| `LOAD_ACC n` | ACC = n |
| `TEST_ACC` | COND = ACC is non-zero |
| `LOAD_TEMP n` / `TEST_TEMP` | write / test TMP |
| `SAVE_ACC i` | scratch[i] = ACC |
| `LOAD_SCRATCH i,n` | scratch[i] = n |
| `COPY_SCRATCH i,j` | scratch[j] = scratch[i] |

**Variables**: `READ_VAR_NAME`, `CLEAR_NAME`, `STORE_VAR`.

**Flow**: `GOTO_ACC`, `GOSUB_ACC`, `DO_RETURN`, `FOR_BEGIN`, `NEXT_ITERATION`,
`SKIP_TO_NEXT`, `READ_DATA`, `RESTORE_ACC`.

**Print**: `PRINT_AT`, `PRINT_VALUE`, `PRINT_SEP`, `PRINT_NL`.

**Input**: `INPUT_PROMPT`, `INPUT_LINE`, `INPUT_FIELD`.

**Devices**: `CLS`, `GFX_SET`, `GFX_RESET`, `POKE`, `DIM_ARRAY`, `LIST`, `NEW`,
`RUN`, `SAVE`, `LOAD`.

## Reading a routine

`FOR I=1 TO 10 STEP 2`:

```
READ_VAR_NAME              control variable -> NAME, ADDR
MATCH =
EVAL
SAVE_ACC 0                 start
MATCH TO
EVAL
SAVE_ACC 1                 limit
LOAD_SCRATCH 2 1           default STEP 1
TEST_TOKEN STEP
BRANCH_IF_NOT for_begin
SKIP_TOKEN
EVAL
SAVE_ACC 2                 step
for_begin:
FOR_BEGIN                  push the frame; COND = the body runs
BRANCH_IF for_enter
SKIP_TO_NEXT               the loop is already finished
for_enter:
END_STMT
```

`FOR_BEGIN` returns false for `FOR I=1 TO 0`, because a Level II loop is tested
at the top; `SKIP_TO_NEXT` then scans forward for the matching `NEXT`, counting
nesting as it goes.

## Stalling

`INPUT_LINE` raises a stall when the Console has no finished line. The sequencer
puts the micro_pc back on that instruction and reports `WAITING_INPUT`; when a
line arrives the machine resumes at exactly the same micro-instruction. Nothing
is unwound and no Python exception escapes to the host.

`INPUT_FIELD` uses the same mechanism for `?REDO`: it resets the micro_pc and
the Token Pointer to the start of the statement, so the whole `INPUT` runs
again, prompt and all — which is what a Level II machine does.

## Writing a new statement

1. Add the opcode to `tokens.py` and to `STATEMENT_TOKENS`.
2. Add a routine in `microcode.py` with `asm.entry(TOKEN)` at the top and a
   terminator on every path.
3. If it needs a step no existing micro-operation performs, add one to `MicroOp`
   and implement `_op_<name>` in `sequencer.py`.
4. Add a test. `test_microcode.py` will already be checking that your token has
   a dispatch entry, that every reachable path terminates, and that every
   micro-operation you used exists.

What does *not* happen: no new `if` in the PCU, no BASIC knowledge in an engine.
