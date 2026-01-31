# TRS-80 Model I Level II BASIC Reference Guide

This document provides a complete reference for the BASIC language as implemented in this TRS-80 simulator, based on the 1978 Radio Shack TRS-80 Model I Level II BASIC interpreter.

## Table of Contents
- [Overview](#overview)
- [Immediate Mode Commands](#immediate-mode-commands)
- [Language Limitations](#language-limitations)
- [Variable Types](#variable-types)
- [Program Structure](#program-structure)
- [Commands](#commands)
- [Mathematical Functions](#mathematical-functions)
- [String Functions](#string-functions)
- [System Functions](#system-functions)
- [Graphics Commands](#graphics-commands)
- [Memory and I/O](#memory-and-io)
- [Operators](#operators)
- [Syntax Rules](#syntax-rules)
- [Memory Map](#memory-map)
- [Examples](#examples)

## Overview

This TRS-80 BASIC simulator implements the authentic Level II BASIC interpreter from 1978. It includes all the limitations, quirks, and exact behavior of the original system.

**Screen Specifications:**
- Text: 64 columns × 16 rows
- Graphics: 128 × 48 pixels
- Coordinates are 1-based (1,1 to 128,48 for graphics)

**Simulator Features:**
- Authentic immediate mode on the green screen
- Modern text editor for program editing
- Full synchronization between both editing modes
- Debug window with variable inspection
- LLM Assistant support

## Immediate Mode Commands

The simulator supports authentic TRS-80 immediate mode where you can type commands directly on the green screen when no program is running. The prompt `>` indicates immediate mode is active.

### System Commands (Immediate Mode Only)

```basic
RUN
```
- Execute the current program from the beginning

```basic
LIST [line_number]
LIST [start_line-end_line]
```
- Display program listing
- `LIST` - shows entire program
- `LIST 100` - shows line 100
- `LIST 10-50` - shows lines 10 through 50

```basic
NEW
```
- Clear program memory and all variables
- Prompts for confirmation

```basic
CLEAR
```
- Clear all variables but keep program

```basic
CONT
```
- Continue execution after STOP command

```basic
LOAD
```
- Load program from file (opens file dialog)

```basic
SAVE
```
- Save program to file (opens file dialog)

```basic
DELETE line_number
DELETE start_line-end_line
```
- Remove program lines
- `DELETE 50` - removes line 50
- `DELETE 100-200` - removes lines 100 through 200

```basic
CLS
```
- Clear the screen

### Direct Program Entry

You can enter program lines directly in immediate mode:
```basic
>10 PRINT "HELLO"
>20 GOTO 10
>RUN
```

### Immediate Statement Execution

Execute statements without line numbers for immediate results:
```basic
>PRINT 2+2
4
>A=10: PRINT A*5
50
>PRINT "HELLO " + "WORLD"
HELLO WORLD
```

## Language Limitations

### Critical Restrictions
- **Line Numbers Required**: All executable statements must have line numbers
- **Variable Names**: Single letter or letter + single digit only (A, B1, X$, NAME$ not allowed)
- **No Multidimensional Arrays**: Only single-dimension arrays supported
- **No Local Variables**: All variables are global
- **No Subroutine Parameters**: GOSUB routines cannot accept parameters
- **No User-Defined Functions**: Only built-in functions available
- **Limited String Handling**: Basic string operations only
- **Case Insensitive**: All keywords automatically converted to uppercase

### Memory Constraints
- Arrays must be dimensioned with DIM before use
- Array indices start at 0, but BASIC convention uses 1-based indexing
- String variables limited by available memory
- Maximum line number: 65529

## Variable Types

### Numeric Variables
```basic
10 LET A = 5          ' Integer
20 LET B1 = 3.14      ' Floating point
30 LET X = -10        ' Negative numbers
40 A = 25             ' LET is optional
```

### String Variables
```basic
10 LET A$ = "HELLO"   ' String variable ($ required)
20 LET B$ = ""        ' Empty string
30 LET C$ = A$ + B$   ' String concatenation
```

### Arrays
```basic
10 DIM A(10)          ' Numeric array (0-10, 11 elements)
20 DIM B$(5)          ' String array (0-5, 6 elements)
30 LET A(1) = 100     ' Assign array element
40 LET B$(0) = "TEST" ' String array element
```

## Program Structure

### Line Numbers
- Required for all executable statements
- Typically increment by 10 (10, 20, 30...)
- Can use decimal numbers (10.5, 20.1) for insertions
- Executed in numerical order

### Multiple Statements
```basic
10 LET A = 5: LET B = 10: PRINT A + B
20 IF A > B THEN PRINT "A BIGGER": GOTO 50
```

## Commands

### Basic I/O
```basic
PRINT [expression[,;expression...]]
```
- Output text and numbers
- `;` - no space between items
- `,` - tab to next print zone (16-character columns)
- Trailing `;` or `,` suppresses newline

```basic
PRINT@ position, expression
```
- Print at specific screen position (0-1023)
- Position = row * 64 + column

```basic
INPUT [prompt;] variable
INPUT ["prompt"; ] variable
```
- Get user input
- Optional prompt string with semicolon

### Program Control
```basic
GOTO line_number
```
- Unconditional jump to line number

```basic
IF condition THEN statement [ELSE statement]
```
- Conditional execution
- ELSE clause optional

```basic
FOR variable = start TO end [STEP increment]
NEXT [variable]
```
- Loop structure
- Default STEP is 1
- Variable name optional in NEXT

```basic
ON expression GOTO line1, line2, line3...
```
- Computed GOTO based on expression value (1, 2, 3...)

```basic
GOSUB line_number
RETURN
```
- Subroutine call and return
- Uses internal stack for nesting

### Data Handling
```basic
DIM variable(size)
```
- Declare array with specified size
- Creates size+1 elements (0 to size)

```basic
DATA value1, value2, value3...
READ variable1, variable2...
RESTORE
```
- Store and retrieve constant data
- RESTORE resets data pointer to beginning

### Program Flow
```basic
END
```
- Terminate program execution

```basic
STOP
```
- Pause program (can be continued)

```basic
REM comment
```
- Comment line (ignored during execution)

```basic
CLS
```
- Clear screen and home cursor

## Mathematical Functions

### Basic Math
```basic
ABS(x)          ' Absolute value
INT(x)          ' Integer part (truncate toward zero)
FIX(x)          ' Truncate to integer
SGN(x)          ' Sign: -1, 0, or 1
SQR(x)          ' Square root
```

### Trigonometric
```basic
SIN(x)          ' Sine (radians)
COS(x)          ' Cosine (radians)  
TAN(x)          ' Tangent (radians)
```

### Exponential/Logarithmic
```basic
EXP(x)          ' e raised to x power
LOG(x)          ' Natural logarithm
```

### Random Numbers
```basic
RND             ' Random 0.0 to 0.999999
RND(n)          ' Random integer 0 to n-1
```

## String Functions

### String Manipulation
```basic
LEN(string$)                    ' Length of string
LEFT$(string$, n)               ' Leftmost n characters
RIGHT$(string$, n)              ' Rightmost n characters
MID$(string$, start[, length])  ' Substring (1-based indexing)
```

### Conversion Functions
```basic
STR$(number)                    ' Convert number to string
VAL(string$)                    ' Convert string to number
CHR$(ascii_code)                ' ASCII code to character
ASC(string$)                    ' First character to ASCII code
```

### String Utilities
```basic
STRING$(count, character)       ' Repeat character count times
INSTR([start,] string$, find$)  ' Find substring position (1-based)
```

## System Functions

### Memory Access
```basic
PEEK(address)                   ' Read memory byte
POKE address, value             ' Write memory byte
```

### Keyboard Input
```basic
INKEY$                          ' Get key press (non-blocking)
```
- Returns empty string if no key pressed
- Returns single character if key available

### Graphics Query
```basic
POINT(x, y)                     ' Check pixel state (0 or 1)
```
- Returns 1 if pixel is on, 0 if off
- Coordinates are 1-based (1,1 to 128,48)

## Graphics Commands

### Pixel Control
```basic
SET(x, y)                       ' Turn pixel on
RESET(x, y)                     ' Turn pixel off
```
- Coordinates: x=1 to 128, y=1 to 48
- (1,1) is top-left corner

## Memory and I/O

### Tape Operations
```basic
PRINT#-1, expression            ' Write to tape file
INPUT#-1, variable              ' Read from tape file
```

### Memory Locations
- **14400**: Keyboard input buffer
- **15360-16383**: Screen memory (64×16 characters)

## Operators

### Arithmetic
```basic
+               ' Addition
-               ' Subtraction  
*               ' Multiplication
/               ' Division
^               ' Exponentiation
MOD             ' Modulo (remainder)
```

### Comparison
```basic
=               ' Equal
<>              ' Not equal
<               ' Less than
>               ' Greater than
<=              ' Less than or equal
>=              ' Greater than or equal
```

### Logical
```basic
AND             ' Logical AND
OR              ' Logical OR
NOT             ' Logical NOT
```

### String
```basic
+               ' String concatenation
```

## Syntax Rules

### General Rules
1. **Line Numbers**: Required for all executable statements
2. **Keywords**: Automatically converted to uppercase
3. **Multiple Statements**: Separate with colon (:)
4. **String Literals**: Enclosed in double quotes
5. **Comments**: Use REM keyword
6. **Variable Names**: Single letter or letter+digit only

### PRINT Statement Rules
```basic
PRINT "TEXT"                    ' Print with newline
PRINT "TEXT";                   ' Print without newline
PRINT A; B; C                   ' Print with no spaces
PRINT A, B, C                   ' Print in tab columns
PRINT A; "TEXT"; B              ' Mixed expressions
```

### Variable Assignment
```basic
LET A = 5                       ' Explicit assignment
A = 5                           ' Implicit assignment (LET optional)
```

### Array Usage
```basic
DIM A(10)                       ' Must dimension before use
A(0) = 5                        ' Valid index: 0 to 10
A(11) = 5                       ' Error: out of bounds
```

## Memory Map

### Important Addresses
| Address | Purpose |
|---------|---------|
| 14400 | Keyboard input buffer |
| 15360-15423 | Screen row 0 (columns 0-63) |
| 15424-15487 | Screen row 1 (columns 0-63) |
| ... | ... |
| 16320-16383 | Screen row 15 (columns 0-63) |

### Screen Memory Layout
- Each character position = 15360 + (row * 64) + column
- Row 0-15, Column 0-63
- ASCII values stored directly

## Examples

### Basic Program Structure
```basic
10 REM HELLO WORLD PROGRAM
20 CLS
30 PRINT "HELLO, WORLD!"
40 END
```

### Input and Variables
```basic
10 CLS
20 PRINT "ENTER YOUR NAME: ";
30 INPUT N$
40 PRINT "HELLO, "; N$; "!"
50 END
```

### Loops and Arrays
```basic
10 DIM A(10)
20 FOR I = 1 TO 10
30 A(I) = I * 2
40 NEXT I
50 FOR I = 1 TO 10
60 PRINT A(I);
70 NEXT I
80 END
```

### Graphics Example
```basic
10 CLS
20 FOR X = 1 TO 128
30 FOR Y = 1 TO 48
40 IF X MOD 8 = 0 THEN SET(X, Y)
50 NEXT Y
60 NEXT X
70 END
```

### Subroutines
```basic
10 GOSUB 1000
20 PRINT "BACK FROM SUBROUTINE"
30 END
1000 PRINT "IN SUBROUTINE"
1010 RETURN
```

### String Manipulation
```basic
10 A$ = "HELLO"
20 B$ = "WORLD"
30 C$ = A$ + " " + B$
40 PRINT C$
50 PRINT "LENGTH: "; LEN(C$)
60 PRINT "FIRST 5: "; LEFT$(C$, 5)
70 END
```

### Game Loop Example
```basic
10 REM SIMPLE GAME LOOP
20 CLS
30 LET S = 64                   ' Player position
40 LET K = PEEK(14400)          ' Check keyboard
50 IF K = 65 THEN S = S - 1     ' A key = move left
60 IF K = 83 THEN S = S + 1     ' S key = move right
70 POKE 15360 + S, 42           ' Draw player (*)
80 GOTO 40                      ' Game loop
```

This reference covers the complete TRS-80 Model I Level II BASIC language as implemented in this simulator. All examples are tested and verified to work correctly. 