#!/usr/bin/env python3
"""
Hailo-10H Direct LLM/VLM Chat
Uses the hailo-apps library to run LLMs and VLMs directly on Hailo-10H

REQUIRED FILES:
- hailo_llm_direct.py (this script)
- ~/hailo-apps/ (Hailo applications library - install via git clone + install.sh)
- HEF model files (download manually if missing):
  * LLMs: run 'hailo-ollama pull <model>' then HEF is in ~/.local/share/hailo-ollama/models/blob/
  * VLMs: ~/Downloads/Qwen2-VL-2B-v5.2.0.hef, ~/Downloads/Florence-2-base.hef

Select model from numbered list, load image if needed, then chat interactively.
Type 'new model' to switch models, 'quit' to exit.
"""

import argparse
import sys
import os

# Add hailo-apps to path
sys.path.insert(0, os.path.expanduser("~/hailo-apps"))

try:
    import cv2
    import numpy as np
    from hailo_platform import VDevice
    from hailo_platform.genai import LLM, VLM
except ImportError as e:
    print(f"Import error: {e}")
    print("\nMake sure you've installed hailo-apps:")
    print("  cd ~/hailo-apps && sudo ./install.sh")
    print("  source ~/hailo-apps/setup_env.sh")
    sys.exit(1)


class HailoModel:
    """Unified wrapper for Hailo LLM and VLM inference
    
    Requires:
    - hailo-apps installed (~/hailo-apps/)
    - HEF files for models (download manually if missing)
    """
    
    # Model configurations
    MODELS = [
        {"name": "qwen2.5:1.5b", "type": "llm", "manifest": "manifests/qwen2.5/1.5b/manifest.json"},
        {"name": "qwen2.5-coder:1.5b", "type": "llm", "manifest": "manifests/qwen2.5-coder/1.5b/manifest.json"},
        {"name": "qwen2:1.5b", "type": "llm", "manifest": "manifests/qwen2/1.5b/manifest.json"},
        {"name": "llama3.2:1b", "type": "llm", "manifest": "manifests/llama3.2/1b/manifest.json"},
        {"name": "deepseek_r1:1.5b", "type": "llm", "manifest": "manifests/deepseek_r1/1.5b/manifest.json"},
        {"name": "qwen2-vl-2b", "type": "vlm", "hef": "~/Downloads/Qwen2-VL-2B-v5.2.0.hef", "size": (336, 336)},
        {"name": "florence-2-base", "type": "vlm", "hef": "~/Downloads/Florence-2-base.hef", "size": (768, 768)},
    ]
    
    MODELS_BASE = os.path.expanduser("~/.local/share/hailo-ollama/models")
    
    @classmethod
    def get_hef_path(cls, model_config):
        """Get HEF path for a model config"""
        if "hef" in model_config:
            return os.path.expanduser(model_config["hef"])
        
        # For LLMs, resolve via manifest
        manifest_rel = model_config.get("manifest")
        if not manifest_rel:
            return None
        
        manifest_path = os.path.join(cls.MODELS_BASE, manifest_rel)
        if not os.path.exists(manifest_path):
            return None
        
        try:
            import json
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            hef_hash = manifest.get("hef_h10h")
            if not hef_hash:
                return None
            return os.path.join(cls.MODELS_BASE, "blob", f"sha256_{hef_hash}")
        except:
            return None
    
    @classmethod
    def is_available(cls, model_config):
        """Check if model HEF is available"""
        hef_path = cls.get_hef_path(model_config)
        return hef_path and os.path.exists(hef_path)
    
    @classmethod
    def download_model(cls, model_config):
        """Download instructions for missing models"""
        model_name = model_config["name"]
        if model_config["type"] == "vlm":
            print(f"To download {model_name}:")
            if "Qwen2-VL" in model_name:
                print("  Visit: https://dev-public.hailo.ai/v5.1.1/blob/Qwen2-VL-2B-Instruct.hef")
                print("  Save as: ~/Downloads/Qwen2-VL-2B-v5.2.0.hef")
            else:
                print("  Check Hailo developer zone for Florence-2 HEF download")
        else:
            print(f"To download {model_name}:")
            print("  Run: hailo-ollama pull <model_name>")
            print("  Then the HEF will be available in ~/.local/share/hailo-ollama/models/blob/")
        return False
    
    def __init__(self, model_idx: int):
        """
        Initialize model
        
        Args:
            model_idx: Index of model in MODELS list
        """
        if model_idx < 0 or model_idx >= len(self.MODELS):
            raise ValueError(f"Invalid model index {model_idx}")
        
        self.config = self.MODELS[model_idx]
        self.name = self.config["name"]
        self.type = self.config["type"]
        self.hef_path = self.get_hef_path(self.config)
        
        if not self.hef_path or not os.path.exists(self.hef_path):
            print(f"Error: HEF file not found: {self.hef_path}")
            print("Please ensure the HEF file is available at the expected path.")
            print("For cached models, you may need to copy/link the blob file:")
            print("  ls ~/.cache/hailo-ollama/models/")
            print("  cp ~/.cache/hailo-ollama/models/<sha256> ~/Downloads/<model>.hef")
            sys.exit(1)
        
        self.vdevice = None
        self.model = None
        self.image = None  # For VLMs
        self.conversation = []  # For LLMs
        self._initialize()
    
    def _initialize(self):
        """Initialize Hailo device and load model"""
        print(f"Loading {self.type.upper()} {self.name} from: {self.hef_path}")
        print("This may take 10-20 seconds...")
        
        # Create virtual device
        params = VDevice.create_params()
        params.group_id = "shared_vdevice"
        self.vdevice = VDevice(params)
        
        # Load model
        if self.type == "llm":
            self.model = LLM(self.vdevice, self.hef_path)
        elif self.type == "vlm":
            self.model = VLM(self.vdevice, self.hef_path)
        
        print(f"✓ {self.type.upper()} loaded successfully!")
    
    def load_image(self, image_path: str):
        """Load image for VLM"""
        if self.type != "vlm":
            print("Error: This model doesn't support images")
            return False
        
        if not os.path.exists(image_path):
            print(f"Error: Image not found: {image_path}")
            return False
        
        self.image = cv2.imread(image_path)
        if self.image is None:
            print(f"Error: Failed to load image: {image_path}")
            return False
        
        print(f"✓ Image loaded: {image_path}")
        return True
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for VLM"""
        size = self.config.get("size", (336, 336))
        if len(image.shape) == 3 and image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, size, interpolation=cv2.INTER_LINEAR)
        return image.astype(np.uint8)
    
    def chat(self, message: str) -> str:
        """
        Send message and get response
        
        Args:
            message: User message
            
        Returns:
            Model's response
        """
        if self.type == "vlm":
            if self.image is None:
                return "Error: No image loaded. Use 'load image <path>' first."
            
            processed_image = self.preprocess_image(self.image)
            prompt = [{
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": message}
                ]
            }]
            
            response = self.model.generate_all(
                prompt=prompt,
                frames=[processed_image],
                temperature=0.1,
                seed=42,
                max_generated_tokens=200
            )
            
        elif self.type == "llm":
            # Build conversation
            self.conversation.append({"role": "user", "content": [{"type": "text", "text": message}]})
            
            response = self.model.generate_all(
                prompt=self.conversation,
                temperature=0.7,
                seed=42,
                max_generated_tokens=500
            )
            
            self.conversation.append({"role": "assistant", "content": [{"type": "text", "text": response}]})
        
        # Clean up response
        response = response.split("<|im_end|>")[0]
        response = response.split("<|eot_id|>")[0]
        
        return response.strip()
    
    def release(self):
        """Release resources"""
        if self.model:
            try:
                if hasattr(self.model, 'clear_context'):
                    self.model.clear_context()
                self.model.release()
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


def main():
    print("Hailo-10H Direct Model Chat")
    print("=" * 50)
    
    while True:
        # Show model list with availability
        print("\nAvailable models:")
        for i, model in enumerate(HailoModel.MODELS):
            status = "✓" if HailoModel.is_available(model) else "✗"
            print(f"  {i+1}. {model['name']} ({model['type'].upper()}) {status}")
        
        try:
            choice = input("\nSelect model (number) or 'quit': ").strip()
            if choice.lower() in ['quit', 'q']:
                break
            
            model_idx = int(choice) - 1
            if model_idx < 0 or model_idx >= len(HailoModel.MODELS):
                print("Invalid choice")
                continue
            
            model_config = HailoModel.MODELS[model_idx]
            
            # Show download instructions if not available
            if not HailoModel.is_available(model_config):
                HailoModel.download_model(model_config)
                input("Press Enter after downloading the model...")
                if not HailoModel.is_available(model_config):
                    print("Model still not available. Please check download instructions.")
                    continue
            
            # Load model
            with HailoModel(model_idx) as hailo_model:
                print(f"\nLoaded {hailo_model.name} ({hailo_model.type.upper()})")
                
                # Load image if VLM
                if hailo_model.type == "vlm":
                    while True:
                        img_path = input("Enter image path (or 'skip' for no image): ").strip()
                        if img_path.lower() == 'skip':
                            break
                        if hailo_model.load_image(img_path):
                            break
                
                # Chat loop
                print("\nChat mode. Type 'quit' to exit, 'new model' to switch models.")
                print("=" * 50)
                
                while True:
                    try:
                        user_input = input("\nYou: ").strip()
                        
                        if not user_input:
                            continue
                        elif user_input.lower() in ['quit', 'q']:
                            return
                        elif user_input.lower() == 'new model':
                            break
                        elif hailo_model.type == "vlm" and user_input.startswith('load image '):
                            img_path = user_input[11:].strip()
                            hailo_model.load_image(img_path)
                            continue
                        
                        response = hailo_model.chat(user_input)
                        print(f"AI: {response}")
                        
                    except KeyboardInterrupt:
                        return
                    except Exception as e:
                        print(f"Error: {e}")
                
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            break
    
    print("\nDone!")


if __name__ == "__main__":
    main()
