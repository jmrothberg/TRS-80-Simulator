# Ollama Integration for TRS-80 Simulator (Standard Ollama)

This guide covers setting up **standard Ollama** (CPU/CUDA/AMD GPU/Apple Silicon) for the TRS-80 BASIC Simulator. For Hailo-10H hardware acceleration, see `HAILO_SETUP_README.md`.

## Standard Ollama vs Hailo-ollama

| Feature | Standard Ollama | Hailo-ollama |
|---------|----------------|--------------|
| **Hardware** | CPU/NVIDIA/AMD GPU/Apple Silicon | Hailo-10H AI Accelerator |
| **Performance** | Fast (GPU) to slow (CPU) | Hardware-optimized |
| **Power Usage** | Variable | Lower (efficient edge AI) |
| **Setup Complexity** | Simple | Requires Hailo hardware |
| **Platform** | Any computer | Raspberry Pi 5 + Hailo-10H |
| **Models** | Any Ollama model | Pre-compiled Hailo models only |

**Use Standard Ollama if:**
- You don't have Hailo-10H hardware
- You're on a different platform (macOS, Windows, etc.)
- You want maximum model flexibility
- You have CUDA/AMD GPU available for acceleration

**Use Hailo-ollama if:**
- You have Raspberry Pi 5 + Hailo-10H
- You want the fastest possible inference
- You prioritize power efficiency

## Installation

### 1. Install Ollama
Visit [https://ollama.ai/](https://ollama.ai/) and download Ollama for your operating system.

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Download Models
After installing Ollama, download some models:

```bash
# Popular models for coding assistance
ollama pull llama2
ollama pull codellama
ollama pull mistral
ollama pull phi
```

### 4. Start Ollama Service
Make sure Ollama is running:
```bash
ollama serve
```

## Usage

1. Start the TRS-80 Simulator:
   ```bash
   python TRS80_Sept_24_25.py  # Use this version for Hailo support
   ```

2. Click "Assistant: ON" to open the LLM support window

3. **Select your backend:**
   - **"O"** = Standard Ollama (CPU/CUDA/AMD GPU/Apple Silicon)
   - **"H"** = Hailo-ollama (GPU acceleration, if available)

4. Choose your preferred model from the dropdown (models must be downloaded first)

5. Adjust temperature and max length as needed

6. Type your BASIC programming questions and click "Send to LLM"

## Features

- **Local Processing**: All inference happens locally, no internet required after setup
- **Multiple Models**: Support for any Ollama-compatible model
- **Streaming**: Real-time response generation
- **BASIC Code Extraction**: Automatically extracts BASIC code blocks from responses
- **Transfer to Simulator**: One-click transfer of generated code to the simulator

## Troubleshooting

### Regular Ollama Issues

**Ollama Not Found**
- Ensure Ollama is installed and running (`ollama serve`)
- Check that the service is available at `http://localhost:11434`

**No Models Available**
- Download models using `ollama pull <model_name>`
- Verify models are installed with `ollama list`

**Connection Issues**
- Restart Ollama service
- Check firewall settings
- Verify port 11434 is not blocked

### Hailo-ollama Issues

**Hailo Server Not Running**
- Start the server: `~/.local/bin/hailo-ollama`
- Check port 8000 is available
- Ensure Hailo-10H hardware is connected

**Models Not Available**
- Models download automatically when selected
- Check `HAILO_SETUP_README.md` for setup instructions

**Hardware Not Detected**
- Verify Hailo-10H card is properly seated
- Run `lspci | grep Hailo` to check detection
- See `check_hailo.py` for diagnostics

## Model Recommendations

### For Standard Ollama (CPU/CUDA/AMD GPU/Apple Silicon):
For TRS-80 BASIC programming:
- **codellama**: Excellent for code generation
- **mistral**: Good general-purpose model
- **llama2**: Reliable for explanations and help
- **phi**: Lightweight option for simpler tasks

### For Hailo-ollama (GPU):
Pre-compiled models optimized for Hailo-10H:
- **qwen2.5:1.5b**: General purpose, fastest
- **qwen2.5-coder:1.5b**: Code generation optimized
- **qwen2:1.5b**: General purpose
- **llama3.2:1b**: Meta's Llama model
- **deepseek_r1:1.5b**: Reasoning focused

## API Reference

The Ollama integration uses the standard Ollama API:
- Endpoint: `http://localhost:11434/api/generate`
- Models list: `http://localhost:11434/api/tags`

Temperature and max tokens are configurable through the UI sliders. 