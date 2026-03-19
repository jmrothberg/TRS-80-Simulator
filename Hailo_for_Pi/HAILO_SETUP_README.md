# Hailo-10 LLM Setup Guide for Raspberry Pi 5

This guide explains how to set up and run LLMs on a Hailo-10 AI accelerator using hailo-ollama.

## What You Need

1. **Raspberry Pi 5** with Hailo-10 (AI HAT+ or M.2 module)
2. **Raspberry Pi OS** (Bookworm or later)
3. **Hailo Developer Account** - Register at https://hailo.ai/developer-zone/

## Files Required from Hailo Developer Zone

> ⚠️ These files require login to download from https://hailo.ai/developer-zone/software-downloads/

| File | Size | Purpose |
|------|------|---------|
| `hailort_5.2.0_arm64.deb` | 5 MB | HailoRT runtime + CLI tools |
| `hailort-pcie-driver_5.2.0_all.deb` | 28 MB | PCIe kernel driver (DKMS) |
| `hailort-5.2.0-cp311-cp311-linux_aarch64.whl` | 7.5 MB | Python bindings |
| `hailo_gen_ai_model_zoo_5.2.0_arm64.deb` | 693 KB | hailo-ollama server (pre-built) |

All these files are included in this folder for convenience.

## Quick Install (Copy These Commands)

```bash
# Install all Hailo packages
sudo dpkg -i hailort_5.2.0_arm64.deb
sudo dpkg -i hailort-pcie-driver_5.2.0_all.deb
sudo dpkg -i hailo_gen_ai_model_zoo_5.2.0_arm64.deb
pip install hailort-5.2.0-cp311-cp311-linux_aarch64.whl

# Reboot to load kernel driver
sudo reboot

# After reboot - test it works
python check_hailo.py

# Start the LLM server and chat!
hailo-ollama &
python hailo_llm_runner.py
```

---

## Detailed Setup (Fresh Pi)

### Step 1: Install HailoRT

```bash
# Install the .deb package (includes kernel driver)
sudo dpkg -i hailort_5.2.0_arm64.deb

# Install DKMS for kernel module building
sudo apt install -y dkms

# Install Python wheel
pip install hailort-5.2.0-cp311-cp311-linux_aarch64.whl
```

### Step 2: Build Hailo Kernel Module (if needed after kernel update)

```bash
# Check if Hailo device is detected
lspci | grep -i hailo

# If /dev/hailo0 doesn't exist, rebuild the driver:
sudo apt install -y linux-headers-$(uname -r) libssl-dev
cd /usr/src/hailort-pcie-driver/linux/pcie
sudo make -C /lib/modules/$(uname -r)/build M=$(pwd) modules
sudo insmod hailo1x_pci.ko

# Make it permanent
sudo mkdir -p /lib/modules/$(uname -r)/extra
sudo cp hailo1x_pci.ko /lib/modules/$(uname -r)/extra/
sudo depmod -a
echo "hailo1x_pci" | sudo tee /etc/modules-load.d/hailo.conf
```

### Step 3: Install Hailo-Ollama (LLM Server)

```bash
# Install build dependencies
sudo apt install -y cmake build-essential libssl-dev

# Clone and build hailo-ollama
git clone https://github.com/hailo-ai/hailo_model_zoo_genai.git
cd hailo_model_zoo_genai
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . -j4

# Install to user directory
mkdir -p ~/.local/bin ~/.config/hailo-ollama ~/.local/share/hailo-ollama
cp src/apps/server/hailo-ollama ~/.local/bin/
cp ../config/hailo-ollama.json ~/.config/hailo-ollama/
cp -r ../models/ ~/.local/share/hailo-ollama/

# Add to PATH (add to ~/.bashrc for permanent)
export PATH=$HOME/.local/bin:$PATH
```

### Step 4: Verify Installation

```bash
# Check Hailo device
python3 -c "from hailo_platform import VDevice; VDevice(); print('✓ Hailo device working')"

# Start hailo-ollama server
hailo-ollama &

# List available models
curl http://localhost:8000/hailo/v1/list
```

## Using the Python Client

Copy `hailo_llm_runner.py` to your project:

```python
from hailo_llm_runner import HailoLLM

# Initialize (auto-starts server if needed)
llm = HailoLLM(model="qwen2.5:1.5b")

# First time: download the model (~1.6GB)
llm.pull_model()

# Chat
response = llm.chat("Hello, what can you do?")
print(response)

# Streaming response
for chunk in llm.chat_stream("Explain Python lists"):
    print(chunk, end="", flush=True)
```

## Direct Model Usage (No Server)

For direct inference without the hailo-ollama server, use `hailo_llm_direct.py`. This requires:

- **hailo-apps** installed (see VLM section below)
- **HEF model files** (downloaded via hailo-ollama or manually)

### Install hailo-apps (Required for Direct Usage)

```bash
# Clone hailo-apps
git clone https://github.com/hailo-ai/hailo-apps.git ~/hailo-apps

# Install dependencies
sudo apt install -y python3-opencv libgstreamer1.0-0 libgstreamer-plugins-base1.0-0

# Install hailo-apps
cd ~/hailo-apps
sudo ./install.sh
source setup_env.sh

# Add to your shell profile
echo "source ~/hailo-apps/setup_env.sh" >> ~/.bashrc
```

### Using hailo_llm_direct.py

```bash
# Interactive chat with model selection
python hailo_llm_direct.py

# It will show:
# 1. qwen2.5:1.5b (LLM)
# 2. qwen2.5-coder:1.5b (LLM)
# ...
# 6. qwen2-vl-2b (VLM)
# 7. florence-2-base (VLM)

# Select by number, load image for VLMs, then chat
```

**Required Files for hailo_llm_direct.py:**
- `hailo_llm_direct.py` - The direct inference script
- `~/hailo-apps/` - Hailo applications library (for direct platform access)
- HEF files for models (download manually if missing):
  - LLMs: Run `hailo-ollama pull <model>` then HEF is in `~/.local/share/hailo-ollama/models/blob/`
  - VLMs: `~/Downloads/Qwen2-VL-2B-v5.2.0.hef`, `~/Downloads/Florence-2-base.hef`

**Note:** Direct usage bypasses the server and runs models directly on Hailo hardware. Faster startup, shows download status. Use server mode (`hailo_llm_runner.py`) for streaming or server-based management.

## Available Models

| Model | Size | Best For | Speed |
|-------|------|----------|-------|
| `qwen2.5:1.5b` | 1.6 GB | General chat | ~7 tok/s |
| `qwen2.5-coder:1.5b` | 1.6 GB | Code generation | ~8 tok/s |
| `llama3.2:1b` | 1.8 GB | General chat | ~8.5 tok/s |
| `deepseek_r1:1.5b` | 2.4 GB | Reasoning | ~7 tok/s |
| `qwen2:1.5b` | 1.6 GB | General chat | ~8 tok/s |

## API Examples

### Using curl
```bash
# Start server
hailo-ollama &

# Chat
curl http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2.5:1.5b", "messages": [{"role": "user", "content": "Hello!"}]}'

# Pull a model
curl http://localhost:8000/api/pull \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2.5:1.5b"}'
```

### Using requests (Python)
```python
import requests

response = requests.post(
    "http://localhost:8000/api/chat",
    json={
        "model": "qwen2.5:1.5b",
        "messages": [{"role": "user", "content": "What is 2+2?"}]
    }
)
print(response.json()["message"]["content"])
```

## Troubleshooting

### "HAILO_OUT_OF_PHYSICAL_DEVICES" error
The kernel module isn't loaded. Run:
```bash
sudo modprobe hailo1x_pci
# Or rebuild if that fails (see Step 2)
```

### "Connection refused" on port 8000
Server isn't running:
```bash
hailo-ollama &
```

### Model download fails
Retry - downloads resume from where they left off:
```python
llm.pull_model()
```

## Files You Need

| File | Keep? | Purpose |
|------|-------|---------|
| `hailo_llm_runner.py` | ✅ Yes | Python client for server-based LLM/VLM usage |
| `hailo_llm_direct.py` | ✅ Yes | Direct inference client (no server, requires hailo-apps) |
| `hailo_vlm_example.py` | ✅ Yes | Direct VLM example script |
| `check_hailo.py` | ✅ Yes | Quick diagnostic script |
| `~/hailo-apps/` | ✅ Yes | Required for direct inference scripts |
| `~/.local/bin/hailo-ollama` | ✅ Yes | The LLM server binary |
| `~/.config/hailo-ollama/` | ✅ Yes | Server config |
| `~/.local/share/hailo-ollama/` | ✅ Yes | Model manifests & downloads |
| `~/Downloads/*.hef` | ✅ Yes | Direct HEF files for models |

## Links

- **Hailo Developer Zone**: https://hailo.ai/developer-zone/
- **Hailo GenAI Model Zoo**: https://github.com/hailo-ai/hailo_model_zoo_genai
- **Hailo Community Forum**: https://community.hailo.ai/
- **HailoRT Documentation**: https://hailo.ai/developer-zone/documentation/
