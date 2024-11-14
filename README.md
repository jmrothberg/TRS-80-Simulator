# TRS-80 BASIC Simulator

A feature-rich simulator that recreates the TRS-80 Model I/III BASIC environment with modern enhancements. This simulator provides a nostalgic yet powerful platform for learning and experimenting with BASIC programming.

![TRS-80 Simulator Screenshot](screenshot.png) <!-- You'll need to add this -->

## Features

### Core Functionality
- **Authentic TRS-80 BASIC Environment**: Faithful recreation of the TRS-80 Model I/III BASIC interpreter
- **Real-time Execution**: Interactive program execution with pause, step, and continue capabilities
- **Graphics Support**: Full implementation of TRS-80's 128x48 graphics mode
- **Tape Emulation**: Virtual cassette tape for data storage and retrieval
- **Dynamic Scaling**: Support for 1x and 2x display scaling

### Enhanced Development Features
- **Integrated Debug Window**: Real-time variable inspection and execution tracking
- **AI Assistant Integration**: Built-in AI companion for programming help
- **Syntax Highlighting**: Automatic BASIC keyword capitalization
- **Modern Text Editing**: Cut, copy, paste functionality with right-click menu
- **File Operations**: Save and load BASIC programs

### User Interface
- **Split Display**: Classic green-on-black display with modern input area
- **Multiple Windows**: Debug, variables, and AI assistant in separate windows
- **Interactive Controls**: Run, Stop, Step, Reset, and other control buttons
- **Context Menus**: Right-click menus for common operations

## Installation

1. Ensure Python 3.x is installed on your system
2. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/trs80-simulator.git
   ```
3. Install required dependencies:
   ```bash
   pip install tkinter
   ```
4. Run the simulator:
   ```bash
   python TRS80_Sept_5_2x.py
   ```

## Usage

### Basic Operations
1. Type your BASIC program in the input area
2. Click "Run" to execute
3. Use "Stop" to pause execution
4. Use "Step" to execute one line at a time
5. Use "Reset" to clear all variables and program state

### Program Development
- Use line numbers for each program line (e.g., `10 PRINT "HELLO"`)
- Save programs using the "Save" button (.bas extension)
- Load existing programs using the "Load" button
- Use the debug window to track program execution
- Monitor variables in real-time with the variables window

### Supported Commands

#### Input/Output
- `PRINT` - Display text or expressions
- `PRINT@` - Position-specific output
- `INPUT` - User input
- `CLS` - Clear screen

#### Variables and Data
- `LET` - Variable assignment
- `DIM` - Array declaration
- `DATA` - Define data values
- `READ` - Read from DATA statements
- `RESTORE` - Reset DATA pointer

#### Control Flow
- `GOTO` - Unconditional jump
- `IF-THEN-ELSE` - Conditional execution
- `FOR-NEXT` - Loop construction
- `GOSUB-RETURN` - Subroutine calls
- `ON-GOTO` - Computed GOTO

#### Graphics
- `SET(x,y)` - Turn on pixel
- `RESET(x,y)` - Turn off pixel
- `POINT(x,y)` - Read pixel state

#### String Functions
- `LEFT$`, `RIGHT$`, `MID$` - String manipulation
- `STR$`, `VAL` - Type conversion
- `LEN`, `ASC`, `CHR$` - String operations

#### Mathematical Functions
- `ABS`, `INT`, `SGN` - Numeric operations
- `SIN`, `COS`, `TAN` - Trigonometry
- `RND` - Random numbers
- `SQR`, `LOG`, `EXP` - Mathematical functions

#### Memory Operations
- `PEEK` - Read memory
- `POKE` - Write to memory

#### Tape Operations
- `PRINT#-1` - Write to tape
- `INPUT#-1` - Read from tape

## Example Programs
