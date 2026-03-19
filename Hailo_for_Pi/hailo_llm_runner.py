#!/usr/bin/env python3
"""
Hailo-10 LLM Client
Python interface to run LLMs and VLMs on Hailo-10 via hailo-ollama server

Usage:
    from hailo_llm_runner import HailoLLM
    
    llm = HailoLLM()
    response = llm.chat("Hello, how are you?")
    print(response)
    
    # With images (for VLMs):
    response = llm.chat("What's in this image?", images=["photo.jpg"])
    print(response)
    
    # Or stream responses:
    for chunk in llm.chat_stream("Tell me a story"):
        print(chunk, end="", flush=True)
"""

import os
import sys
import json
import subprocess
import time
import requests
from typing import Generator, Optional, List, Dict

# Add hailo-apps to path for VLM support
sys.path.insert(0, os.path.expanduser("~/hailo-apps"))

try:
    import cv2
    import numpy as np
    from hailo_platform import VDevice
    from hailo_platform.genai import VLM
    VLM_AVAILABLE = True
except ImportError:
    VLM_AVAILABLE = False
    print("Warning: Hailo VLM libraries not available. VLM models will not work.")

class HailoLLM:
    """Python client for Hailo-10 LLM inference via hailo-ollama"""
    
    # Available models (pre-compiled for Hailo-10)
    AVAILABLE_MODELS = [
        "qwen2.5:1.5b",        # General purpose, newest
        "qwen2.5-coder:1.5b",  # Code generation
        "qwen2:1.5b",          # General purpose
        "llama3.2:1b",         # Meta's Llama
        "deepseek_r1:1.5b",    # Reasoning focused
        "qwen2-vl-2b",         # Vision-Language Model (VLM)
        "florence-2-base",     # Another VLM for image captioning
    ]
    
    # VLM models that require direct Hailo platform access
    VLM_MODELS = ["qwen2-vl-2b", "florence-2-base"]
    
    # Model configurations for VLMs
    MODEL_CONFIG = {
        "qwen2-vl-2b": {
            "hef": "~/Downloads/Qwen2-VL-2B-v5.2.0.hef",
            "size": (336, 336)
        },
        "florence-2-base": {
            "hef": "~/Downloads/Florence-2-base.hef",
            "size": (768, 768)
        }
    }
    

class HailoVLM:
    """Simple wrapper for Hailo VLM inference"""
    
    def __init__(self, model: str = "qwen2-vl-2b", hef_path: str = None):
        """
        Initialize VLM
        
        Args:
            model: Model name (e.g., "qwen2-vl-2b", "florence-2-base")
            hef_path: Path to the .hef model file (overrides model default)
        """
        if hef_path:
            self.hef_path = hef_path
            self.size = (336, 336)
        else:
            if model not in HailoLLM.MODEL_CONFIG:
                raise ValueError(f"Unknown VLM model '{model}'. Available: {list(HailoLLM.MODEL_CONFIG.keys())}")
            self.hef_path = os.path.expanduser(HailoLLM.MODEL_CONFIG[model]["hef"])
            self.size = HailoLLM.MODEL_CONFIG[model]["size"]
        
        if not os.path.exists(self.hef_path):
            raise FileNotFoundError(f"HEF file not found: {self.hef_path}")
        
        self.vdevice = None
        self.vlm = None
        self._initialize()
    
    def _initialize(self):
        """Initialize Hailo device and load model"""
        # Create virtual device
        params = VDevice.create_params()
        params.group_id = "shared_vdevice"
        self.vdevice = VDevice(params)
        
        # Load VLM model
        self.vlm = VLM(self.vdevice, self.hef_path)
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for VLM
        - Convert BGR to RGB
        - Resize to model-specific size
        """
        if len(image.shape) == 3 and image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        image = cv2.resize(image, self.size, interpolation=cv2.INTER_LINEAR)
        return image.astype(np.uint8)
    
    def ask_about_image(self, image: np.ndarray, question: str, 
                        system_prompt: str = None, first_message: bool = True) -> str:
        """
        Ask a question about an image
        
        Args:
            image: OpenCV image (BGR format)
            question: Question about the image
            system_prompt: Optional system prompt
            first_message: Whether this is the first message (system prompt only on first)
            
        Returns:
            Model's response
        """
        # Preprocess image
        processed_image = self.preprocess_image(image)
        
        # Build prompt - system prompt only on first message
        prompt = []
        
        if first_message:
            if system_prompt:
                prompt.append({
                    "role": "system",
                    "content": [{"type": "text", "text": system_prompt}]
                })
            else:
                prompt.append({
                    "role": "system", 
                    "content": [{"type": "text", "text": "You are a helpful assistant that analyzes images and answers questions about them."}]
                })
        
        prompt.append({
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": question}
            ]
        })
        
        # Generate response
        response = self.vlm.generate_all(
            prompt=prompt,
            frames=[processed_image],
            temperature=0.1,
            seed=42,
            max_generated_tokens=200
        )
        
        # Clean up response (remove special tokens)
        response = response.split("<|im_end|>")[0]
        response = response.split(". [{'type'")[0]
        
        return response.strip()
    
    def release(self):
        """Release resources"""
        if self.vlm:
            try:
                self.vlm.clear_context()
                self.vlm.release()
            except:
                pass
        
        if self.vdevice:
            try:
                self.vdevice.release()
            except:
                pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.release()


    def __init__(self, model: str = "qwen2.5:1.5b", host: str = "localhost", port: int = 8000):
        """
        Initialize Hailo LLM client
        
        Args:
            model: Model name (default: qwen2.5:1.5b)
            host: Server host (default: localhost)
            port: Server port (default: 8000)
        """
        self.model = model
        self.base_url = f"http://{host}:{port}"
        self.conversation_history: List[Dict] = []
        self.vlm = None
        
    def is_server_running(self) -> bool:
        """Check if hailo-ollama server is running"""
        try:
            response = requests.get(f"{self.base_url}/hailo/v1/list", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def start_server(self) -> bool:
        """Start the hailo-ollama server if not running"""
        if self.is_server_running():
            return True
            
        print("Starting hailo-ollama server...")
        hailo_ollama_path = os.path.expanduser("~/.local/bin/hailo-ollama")
        
        if not os.path.exists(hailo_ollama_path):
            print(f"Error: hailo-ollama not found at {hailo_ollama_path}")
            return False
        
        # Start server in background
        subprocess.Popen(
            [hailo_ollama_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Wait for server to start
        for _ in range(10):
            time.sleep(1)
            if self.is_server_running():
                print("✓ Server started")
                return True
        
        print("✗ Failed to start server")
        return False
    
    def list_models(self) -> List[str]:
        """List available models"""
        try:
            response = requests.get(f"{self.base_url}/hailo/v1/list", timeout=5)
            data = response.json()
            return data.get("models", [])
        except Exception as e:
            print(f"Error listing models: {e}")
            return []
    
    def pull_model(self, model: Optional[str] = None, stream: bool = True) -> bool:
        """
        Download a model from Hailo servers
        
        Args:
            model: Model name (uses self.model if not specified)
            stream: Show download progress
        """
        model = model or self.model
        print(f"Pulling model: {model}")
        
        try:
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"model": model, "stream": stream},
                stream=stream,
                timeout=600  # 10 minute timeout for large downloads
            )
            
            if stream:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "completed" in data and "total" in data:
                            pct = (data["completed"] / data["total"]) * 100
                            print(f"\rDownloading: {pct:.1f}%", end="", flush=True)
                        elif "status" in data:
                            print(f"\n{data['status']}")
                print("\n✓ Model downloaded")
            return True
            
        except Exception as e:
            print(f"Error pulling model: {e}")
            return False
    
    def chat(self, message: str, system_prompt: Optional[str] = None, images: Optional[List[str]] = None) -> str:
        """
        Send a chat message and get response
        
        Args:
            message: User message
            system_prompt: Optional system prompt
            images: List of image file paths
            
        Returns:
            AI response text
        """
        if self.model in self.VLM_MODELS:
            if not VLM_AVAILABLE:
                return "Error: VLM libraries not available."
            if not images:
                return "Error: VLM models require images for analysis. Please provide image paths."
            try:
                if not self.vlm:
                    self.vlm = HailoVLM(model=self.model)
                # Assume single image for simplicity
                img_path = images[0]
                image = cv2.imread(img_path)
                if image is None:
                    return f"Error: Failed to load image {img_path}"
                response = self.vlm.ask_about_image(image, message, system_prompt)
                # Update history (simple, no full conversation for VLM)
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": "assistant", "content": response})
                return response
            except Exception as e:
                return f"Error: {e}"
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history
        messages.extend(self.conversation_history)
        
        # Prepare message content
        content = message
        if images:
            # For VLMs, format as list of content items
            content = [{"type": "text", "text": message}]
            for img_path in images:
                if os.path.exists(img_path):
                    # Read image as base64
                    import base64
                    with open(img_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode()
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
                    })
                else:
                    print(f"Warning: Image not found: {img_path}")
        
        # Add current message
        messages.append({"role": "user", "content": content})
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=120
            )
            
            data = response.json()
            assistant_message = data.get("message", {}).get("content", "")
            
            # Update history
            self.conversation_history.append({"role": "user", "content": content})
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            
            return assistant_message
            
        except Exception as e:
            return f"Error: {e}"
    
    def chat_stream(self, message: str, system_prompt: Optional[str] = None, images: Optional[List[str]] = None) -> Generator[str, None, None]:
        """
        Send a chat message and stream the response
        
        Args:
            message: User message
            system_prompt: Optional system prompt
            images: List of image file paths
            
        Yields:
            Response text chunks
        """
        if self.model in self.VLM_MODELS:
            if not VLM_AVAILABLE:
                yield "Error: VLM libraries not available."
                return
            if not images:
                yield "Error: VLM models require images for analysis. Please provide image paths."
                return
            try:
                if not self.vlm:
                    self.vlm = HailoVLM(model=self.model)
                # Assume single image for simplicity
                img_path = images[0]
                image = cv2.imread(img_path)
                if image is None:
                    yield f"Error: Failed to load image {img_path}"
                    return
                response = self.vlm.ask_about_image(image, message, system_prompt)
                # Update history
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": "assistant", "content": response})
                yield response
            except Exception as e:
                yield f"Error: {e}"
            return
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.extend(self.conversation_history)
        
        # Prepare message content
        content = message
        if images:
            # For VLMs, format as list of content items
            content = [{"type": "text", "text": message}]
            for img_path in images:
                if os.path.exists(img_path):
                    # Read image as base64
                    import base64
                    with open(img_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode()
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
                    })
                else:
                    print(f"Warning: Image not found: {img_path}")
        
        messages.append({"role": "user", "content": content})
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True
                },
                stream=True,
                timeout=120
            )
            
            full_response = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    full_response += chunk
                    yield chunk
            
            # Update history
            self.conversation_history.append({"role": "user", "content": content})
            self.conversation_history.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            yield f"Error: {e}"
    
    def generate(self, prompt: str) -> str:
        """
        Simple text generation (no chat format)
        
        Args:
            prompt: Text prompt
            
        Returns:
            Generated text
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=120
            )
            
            data = response.json()
            return data.get("response", "")
            
        except Exception as e:
            return f"Error: {e}"
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []


def main():
    """Interactive chat demo"""
    print("Hailo-10 LLM Chat")
    print("=" * 50)
    
    # Initialize client
    llm = HailoLLM(model="qwen2.5:1.5b")
    
    # Check/start server
    if not llm.start_server():
        print("Please start hailo-ollama manually:")
        print("  ~/.local/bin/hailo-ollama")
        return
    
    # Check if model is available
    available = llm.list_models()
    print(f"Available models: {available}")
    
    if llm.model not in available:
        print(f"\nModel {llm.model} not downloaded yet.")
        print("Downloading now (this may take a few minutes)...")
        llm.pull_model()
    
    # Interactive chat
    print("\n" + "=" * 50)
    print("Chat with Hailo-10 models!")
    print("Commands: /clear (reset), /model <name>, /image <path>, /quit")
    print("=" * 50)
    
    current_images = []
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['/quit', '/exit', '/q']:
                break
            elif user_input.lower() == '/clear':
                llm.clear_history()
                current_images = []
                print("Conversation cleared.")
                continue
            elif user_input.startswith('/model '):
                new_model = user_input[7:].strip()
                llm.model = new_model
                llm.clear_history()
                current_images = []
                print(f"Switched to model: {new_model}")
                continue
            elif user_input.startswith('/image '):
                img_path = user_input[7:].strip()
                if os.path.exists(img_path):
                    current_images.append(img_path)
                    print(f"Added image: {img_path}")
                else:
                    print(f"Image not found: {img_path}")
                continue
            
            # Stream response
            print("AI: ", end="", flush=True)
            for chunk in llm.chat_stream(user_input, images=current_images if current_images else None):
                print(chunk, end="", flush=True)
            print()
            
            # Clear images after use (one-time use)
            current_images = []
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()