# TRS-80 Model I BASIC Simulator
Jonathan M. Rothberg updated January 21st 2026

A faithful recreation of the 1978 Radio Shack TRS-80 Model I computer with Level II BASIC, featuring authentic immediate mode interaction and modern conveniences including Hailo-10H AI accelerator support.

## Features

### Authentic TRS-80 Experience
- **Green phosphor display** - 64×16 text, 128×48 graphics
- **Immediate mode** - Type commands directly on the screen like the original
- **Blinking block cursor** - Authentic cursor behavior (disappears during program execution)
- **Level II BASIC** - Complete implementation of the original interpreter
- **Memory limitations** - Single-letter variables, line numbers required
- **BREAK key support** - Stop infinite loops like the original

### Modern Enhancements
- **Dual editing modes** - Use either the green screen or modern text editor
- **Full synchronization** - Changes in either mode instantly reflect in the other
- **Debug window** - Watch variables and program execution
- **LLM Assistant** - AI-powered help for programming (Ollama or Hailo-10H)
- **Hailo-10H GPU acceleration** - Hardware-accelerated AI models on Raspberry Pi
- **File operations** - Save/load programs with modern file dialogs
- **2X display scaling** - Make the screen easier to read (legacy versions)
- **Emergency recovery** - Auto-fix stuck states

## Quick Start

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/TRS_80_SIM.git
cd TRS_80_SIM
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. **For Hailo-10H support on Raspberry Pi:**
```bash
# Follow the Hailo setup guide
cat HAILO_SETUP_README.md
```

4. Run the simulator:
```bash
# For Raspberry Pi with Hailo support:
python TRS80_Sept_24_25.py

# For legacy 2x scaling version:
python TRS80_Sept_7_2x.py
```

### Basic Usage

When the simulator starts, you'll see:
```
READY
>
```

The `>` prompt indicates immediate mode. You can:

1. **Type a program directly**:
```basic
>10 PRINT "HELLO WORLD"
>20 GOTO 10
>RUN
```

2. **Execute immediate commands**:
```basic
>PRINT 2+2
4
>CLS
```

3. **Use the text editor** below the green screen for easier editing

## Keyboard Shortcuts

### Essential Keys
- **ESC** or **Ctrl+C** - BREAK (stop running program, like original TRS-80)
- **Ctrl+R** - Emergency reset to immediate mode (if screen gets stuck)

### Other Shortcuts
- **Right-click** on green screen - Copy screen contents
- **Right-click** in text editor - Cut/Copy/Paste menu
- **Click green screen** - Auto-recover immediate mode if needed
- **2X button** - Toggle display scaling

## Immediate Mode Commands

Commands you can type at the `>` prompt:

| Command | Description | Examples |
|---------|-------------|----------|
| `RUN` | Execute the program | `RUN` |
| `LIST` | Display program | `LIST`<br>`LIST 100`<br>`LIST 10-50` |
| `NEW` | Clear program and variables | `NEW` |
| `CLEAR` | Clear variables only | `CLEAR` |
| `CONT` | Continue after STOP | `CONT` |
| `LOAD` | Load program from file | `LOAD` |
| `SAVE` | Save program to file | `SAVE` |
| `DELETE` | Remove program lines | `DELETE 50`<br>`DELETE 100-200` |
| `CLS` | Clear screen | `CLS` |

You can also:
- Enter program lines: `>10 PRINT "HELLO"`
- Execute immediate statements: `>PRINT TIME$`
- Do calculations: `>PRINT SQR(16)`

## Programming in BASIC

### Simple Program Example
```basic
10 REM GUESS THE NUMBER
20 CLS
30 LET N = INT(RND(10)) + 1
40 PRINT "I'M THINKING OF A NUMBER FROM 1 TO 10"
50 INPUT "YOUR GUESS"; G
60 IF G = N THEN PRINT "CORRECT!": END
70 IF G < N THEN PRINT "TOO LOW"
80 IF G > N THEN PRINT "TOO HIGH"
90 GOTO 50
```

### Graphics Example
```basic
10 CLS
20 FOR X = 1 TO 128 STEP 4
30 FOR Y = 1 TO 48 STEP 4
40 SET(X, Y)
50 NEXT Y
60 NEXT X
70 END
```

### Breaking Out of Infinite Loops
If your program gets stuck in a loop:
```basic
10 PRINT "STUCK"
20 GOTO 10
```
Press **ESC** or **Ctrl+C** to break out:
```
STUCK
STUCK
[Press ESC]
BREAK IN 10
>
```

## GUI Controls

- **Run** - Execute the program
- **Stop/Cont** - Pause/continue execution
- **Step** - Execute one line at a time
- **Reset** - Clear all variables
- **List** - Display program on green screen
- **Clear** - Clear the green screen
- **Save/Load** - File operations
- **Debug** - Toggle debug window
- **Assistant** - Toggle LLM helper
- **Help** - View command reference

## Hailo-10H AI Acceleration

The simulator supports hardware-accelerated AI models using the Hailo-10H AI accelerator on Raspberry Pi 5. This provides significant performance improvements over CPU-only inference.

### Supported Models
- **qwen2.5:1.5b** - General purpose, fastest
- **qwen2.5-coder:1.5b** - Code generation optimized
- **qwen2:1.5b** - General purpose
- **llama3.2:1b** - Meta's Llama model
- **deepseek_r1:1.5b** - Reasoning focused

### Setup Requirements
- Raspberry Pi 5 with PCIe interface
- Hailo-10H AI accelerator card
- HailoRT drivers and runtime installed
- hailo-ollama server running on port 8000

### Usage
1. Start the hailo-ollama server: `~/.local/bin/hailo-ollama`
2. In the simulator, click **Assistant** button
3. Select **"H"** (Hailo) radio button
4. Choose a model from the dropdown
5. Models marked `[DL]` will download automatically on first use

### Performance Benefits
- **Hardware-optimized inference** on specialized AI accelerator
- **Low power consumption** - efficient edge AI processing
- **Real-time responses** for interactive programming help
- **Pre-compiled models** optimized for Hailo architecture

## Technical Details

### Screen Memory
- Text screen: 15360-16383 (64×16 characters)
- Graphics: 128×48 pixels via SET/RESET commands
- Keyboard buffer: Address 14400

### Variable Limitations
- Names: Single letter (A-Z) or letter+digit (A0-Z9)
- Strings: Must end with $ (A$, B1$)
- Arrays: Single dimension only, use DIM first

### Special Features
- `INKEY$` - Non-blocking keyboard input
- `PEEK/POKE` - Direct memory access
- `PRINT@` - Position-based printing
- Tape operations via `PRINT#-1` and `INPUT#-1`
- Authentic cursor behavior (hidden during program execution)

## Troubleshooting

### Common Issues

1. **Can't type in green screen**
   - Click on the green screen to give it focus
   - Press **Ctrl+R** for emergency reset to immediate mode

2. **Program stuck in infinite loop**
   - Press **ESC** or **Ctrl+C** to break out

3. **"No module named tkinter"**
   - Install: `sudo apt-get install python3-tk` (Linux)
   - macOS/Windows: Usually included with Python

4. **LLM Assistant not working**
   - **For standard Ollama (CPU/CUDA/AMD/Apple Silicon):** See `OLLAMA_SETUP.md`
   - **For Hailo-10H acceleration:** See `HAILO_SETUP_README.md`
   - Ensure the appropriate server is running:
     - Standard Ollama: `ollama serve` (port 11434)
     - Hailo-ollama: `~/.local/bin/hailo-ollama` (port 8000)

5. **Lost cursor or prompt**
   - Click the green screen (auto-recovery)
   - Press **Ctrl+R** (emergency reset)

## Examples Included

The repository includes several example programs:
- `Hello_world.bas` - Classic first program
- `Invaders.bas` - Space Invaders game
- `complex_test_suite.bas` - Feature demonstrations
- `Example.bas` - Various BASIC examples

## Building Executables

To create standalone executables:

### macOS
```bash
pyinstaller TRS_Mac.spec
```

### Raspberry Pi
```bash
pyinstaller TRS_PI.spec
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test thoroughly with the included test programs
4. Submit a pull request

## License

This project recreates the TRS-80 Model I computer for educational and historical preservation purposes. TRS-80 is a trademark of Tandy Corporation.

## Acknowledgments

- Original TRS-80 design by Steve Leininger and Don French at Tandy Corporation
- Level II BASIC by Microsoft
- Modern implementation by Jonathan Rothberg

## Resources

- [TRS80_BASIC_REFERENCE.md](TRS80_BASIC_REFERENCE.md) - Complete BASIC language reference
- [OLLAMA_SETUP.md](OLLAMA_SETUP.md) - Standard Ollama setup guide (CPU/CUDA/AMD/Apple Silicon)
- [HAILO_SETUP_README.md](HAILO_SETUP_README.md) - Hailo-10H setup for Raspberry Pi
- [TRS-80 Model I Wikipedia](https://en.wikipedia.org/wiki/TRS-80)

---

*Experience computing history with authentic TRS-80 BASIC programming!* 