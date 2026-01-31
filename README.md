# TRS-80 BASIC Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A feature-rich simulator that recreates the TRS-80 Model I/III BASIC environment with modern enhancements, including AI-powered code assistance using Claude, OpenAI, Ollama, or local transformers.

![TRS-80 Simulator Screenshot](https://via.placeholder.com/800x400?text=TRS-80+Simulator)

## Features

### Core Functionality
- **Authentic TRS-80 BASIC Environment**: Faithful recreation of the TRS-80 Model I/III BASIC interpreter
- **Real-time Execution**: Interactive program execution with pause, step, and continue capabilities
- **Graphics Support**: Full implementation of TRS-80's 128x48 graphics mode
- **Tape Emulation**: Virtual cassette tape for data storage and retrieval
- **Dynamic Scaling**: Support for 1x and 2x display scaling

### AI Assistant Integration
- **Multiple LLM Providers**: Choose from Claude (Anthropic), GPT (OpenAI), Ollama (local), or HuggingFace Transformers
- **Code Generation**: AI helps write TRS-80 BASIC programs from natural language descriptions
- **Debugging Assistance**: Context-aware help for fixing bugs in your BASIC code
- **Learning Tool**: Get explanations of vintage BASIC programming concepts

### User Interface
- **Split Display**: Classic green-on-black display with modern input area
- **Debug Window**: Real-time variable inspection and execution tracking
- **Multiple Windows**: Debug, variables, and AI assistant in separate windows
- **Interactive Controls**: Run, Stop, Step, Reset, and other control buttons

## Installation

### Prerequisites

- Python 3.11+ (recommended for PyInstaller compatibility)
- tkinter (usually included with Python)

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jmrothberg/TRS-80-Simulator.git
   cd TRS-80-Simulator
   ```

2. **Install dependencies:**
   ```bash
   pip install -r TRS_80_requirements.txt
   ```

3. **Run the simulator:**
   ```bash
   python TRS80_July_9_25.py
   ```

## AI Assistant Setup

The simulator includes an AI assistant that can help write and debug TRS-80 BASIC code. You can use any of these LLM providers:

### Option 1: Claude (Anthropic) - Recommended for Code

Best for generating accurate TRS-80 BASIC code.

1. Get an API key from [Anthropic Console](https://console.anthropic.com/)
2. Set the environment variable:
   ```bash
   # macOS/Linux
   export ANTHROPIC_API_KEY=your_key_here
   
   # Windows
   set ANTHROPIC_API_KEY=your_key_here
   ```
3. Select "C" (Claude) in the assistant window

### Option 2: OpenAI (GPT-4, GPT-3.5)

Alternative cloud-based option.

1. Get an API key from [OpenAI Platform](https://platform.openai.com/api-keys)
2. Set the environment variable:
   ```bash
   # macOS/Linux
   export OPENAI_API_KEY=your_key_here
   
   # Windows
   set OPENAI_API_KEY=your_key_here
   ```
3. Install the OpenAI package:
   ```bash
   pip install openai
   ```
4. Select "G" (GPT) in the assistant window

### Option 3: Ollama (Free Local LLMs) - No API Key Required

Run AI models locally on your machine for free.

1. Install Ollama from [ollama.ai](https://ollama.ai/)
2. Download a model:
   ```bash
   ollama pull llama2
   # or for coding:
   ollama pull codellama
   ```
3. Start Ollama (runs automatically on macOS/Windows)
4. Select "O" (Ollama) in the assistant window

### Option 4: Local Transformers

Use HuggingFace models for offline, private operation.

1. Install dependencies:
   ```bash
   pip install torch transformers
   ```
2. Download models to your local directory (default: `/Users/username/Models_Transformer` on macOS)
3. Select "T" (Transformer) in the assistant window

### Environment Variables Template

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
# Edit .env with your API keys
```

## Usage

### Basic Operations

1. Type your BASIC program in the input area
2. Click "Run" to execute
3. Use "Stop" to pause execution
4. Use "Step" to execute one line at a time
5. Use "Reset" to clear all variables and program state

### Using the AI Assistant

1. Open the AI Assistant window (automatically opens with the simulator)
2. Select your LLM provider (C=Claude, G=GPT, O=Ollama, T=Transformer)
3. Choose a model from the dropdown
4. Type your request (e.g., "Write a simple guessing game")
5. Click "Send" to get AI-generated code
6. Click "Transfer" to copy the code to the TRS-80 input area

### Supported BASIC Commands

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

### Hello World
```basic
10 PRINT "HELLO, WORLD!"
20 END
```

### Counting Loop
```basic
10 FOR I = 1 TO 10
20 PRINT I * I
30 NEXT I
```

### Simple Graphics
```basic
10 CLS
20 FOR X = 1 TO 128
30 SET(X, 24)
40 NEXT X
50 END
```

### Number Guessing Game
```basic
10 CLS
20 N = INT(RND * 100) + 1
30 PRINT "GUESS A NUMBER 1-100"
40 INPUT G
50 IF G = N THEN 90
60 IF G < N THEN PRINT "TOO LOW"
70 IF G > N THEN PRINT "TOO HIGH"
80 GOTO 40
90 PRINT "CORRECT!"
100 END
```

## File Structure

```
TRS-80-Simulator/
├── TRS80_July_9_25.py      # Main simulator application
├── TRS80LLMSupport.py      # AI assistant integration module
├── TRS_80_requirements.txt # Python dependencies
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore rules
├── README.md               # This file
└── *.bas                   # Example BASIC programs
```

## Building Executables

### macOS
```bash
pip install pyinstaller
pyinstaller --onefile --windowed TRS80_July_9_25.py
```

### Windows
```bash
pip install pyinstaller
pyinstaller --onefile --windowed TRS80_July_9_25.py
```

Note: Use Python 3.11.x for best PyInstaller compatibility.

## Troubleshooting

### "ANTHROPIC_API_KEY not set" error
Make sure you've exported the environment variable in your current terminal session, or add it to your shell profile (~/.zshrc, ~/.bashrc).

### Ollama models not showing
1. Ensure Ollama is running: `ollama serve`
2. Check if models are installed: `ollama list`
3. Pull a model if needed: `ollama pull llama2`

### Graphics not displaying correctly
- Use the "2X" button to scale the display for high-DPI screens
- Ensure your Python has tkinter properly installed

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Author

**Jonathan M. Rothberg** - [@jmrothberg](https://github.com/jmrothberg)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by the original TRS-80 Model I/III by Tandy/Radio Shack
- BASIC language specification from the TRS-80 technical reference manual
- Thanks to the vintage computing community for keeping these systems alive
