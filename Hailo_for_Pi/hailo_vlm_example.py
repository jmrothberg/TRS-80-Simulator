#!/usr/bin/env python3
"""
Hailo-10H VLM (Vision Language Model) Example
Uses the hailo-apps library to run Qwen2-VL on Hailo-10H

Requirements:
    1. Install hailo-apps:
       cd ~/hailo-apps && sudo ./install.sh && source setup_env.sh
    
    2. The VLM HEF file (auto-downloads or use your downloaded one):
       ~/Downloads/Qwen2-VL-2B-Instruct.hef

Usage:
    python hailo_vlm_example.py                          # Uses default test image and qwen2-vl-2b
    python hailo_vlm_example.py --image /path/to/img.jpg # Your own image
    python hailo_vlm_example.py --camera                 # Use camera (if available)
    python hailo_vlm_example.py --model florence-2-base  # Use Florence-2 model
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
    from hailo_platform.genai import VLM
except ImportError as e:
    print(f"Import error: {e}")
    print("\nMake sure you've installed hailo-apps:")
    print("  cd ~/hailo-apps && sudo ./install.sh")
    print("  source ~/hailo-apps/setup_env.sh")
    sys.exit(1)


class HailoVLM:
    """Simple wrapper for Hailo VLM inference"""
    
    # Model configurations
    MODEL_CONFIG = {
        "qwen2-vl-2b": {
            "hef": "~/Downloads/Qwen2-VL-2B-v5.2.0.hef",
            "size": (336, 336)
        },
        "florence-2-base": {
            "hef": "~/Downloads/Florence-2-base.hef",
            "size": (768, 768)  # Assuming Florence-2 uses 768x768
        }
    }
    
    def __init__(self, model: str = "qwen2-vl-2b", hef_path: str = None):
        """
        Initialize VLM
        
        Args:
            model: Model name (e.g., "qwen2-vl-2b", "florence-2-base")
            hef_path: Path to the .hef model file (overrides model default)
        """
        if hef_path:
            self.hef_path = hef_path
            # Use default size for unknown models
            self.size = (336, 336)
        else:
            if model not in self.MODEL_CONFIG:
                print(f"Error: Unknown model '{model}'. Available: {list(self.MODEL_CONFIG.keys())}")
                sys.exit(1)
            self.hef_path = os.path.expanduser(self.MODEL_CONFIG[model]["hef"])
            self.size = self.MODEL_CONFIG[model]["size"]
        
        if not os.path.exists(self.hef_path):
            print(f"Error: HEF file not found: {self.hef_path}")
            if "Qwen2-VL" in self.hef_path:
                print("\nDownload it from:")
                print("  https://dev-public.hailo.ai/v5.1.1/blob/Qwen2-VL-2B-Instruct.hef")
            else:
                print("\nPlease ensure the HEF file is downloaded to the expected path.")
            sys.exit(1)
        
        self.vdevice = None
        self.vlm = None
        self._initialize()
    
    def _initialize(self):
        """Initialize Hailo device and load model"""
        print(f"Loading VLM from: {self.hef_path}")
        print("This may take 10-20 seconds...")
        
        # Create virtual device
        params = VDevice.create_params()
        params.group_id = "shared_vdevice"
        self.vdevice = VDevice(params)
        
        # Load VLM model
        self.vlm = VLM(self.vdevice, self.hef_path)
        print("✓ VLM loaded successfully!")
    
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
    
    def describe_image(self, image: np.ndarray) -> str:
        """Get a general description of the image"""
        return self.ask_about_image(image, "Describe what you see in this image.")
    
    def count_objects(self, image: np.ndarray, object_type: str = "objects") -> str:
        """Count specific objects in the image"""
        return self.ask_about_image(image, f"How many {object_type} are in this image?")
    
    def read_text(self, image: np.ndarray) -> str:
        """Read any text visible in the image"""
        return self.ask_about_image(image, "Read and transcribe any text you can see in this image.")
    
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


def capture_from_camera() -> np.ndarray:
    """Capture a single frame from the camera"""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera")
        return None
    
    print("Camera opened. Press SPACE to capture, Q to quit...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        cv2.imshow("Press SPACE to capture", frame)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord(' '):
            cap.release()
            cv2.destroyAllWindows()
            return frame
        elif key == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    return None


def main():
    parser = argparse.ArgumentParser(description="Hailo VLM Example")
    parser.add_argument("--image", type=str, help="Path to image file")
    parser.add_argument("--camera", action="store_true", help="Capture from camera")
    parser.add_argument("--hef", type=str, help="Path to HEF model file")
    parser.add_argument("--model", type=str, default="qwen2-vl-2b", 
                        choices=["qwen2-vl-2b", "florence-2-base"],
                        help="VLM model to use")
    parser.add_argument("--question", type=str, default="What do you see in this image?",
                        help="Question to ask about the image")
    args = parser.parse_args()
    
    # Get image
    if args.camera:
        image = capture_from_camera()
        if image is None:
            print("Failed to capture image from camera")
            sys.exit(1)
    elif args.image:
        image = cv2.imread(args.image)
        if image is None:
            print(f"Failed to load image: {args.image}")
            sys.exit(1)
    else:
        # Look for test image on Desktop first
        desktop_images = []
        desktop_path = os.path.expanduser("~/Desktop")
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            import glob
            desktop_images.extend(glob.glob(os.path.join(desktop_path, ext)))
        
        if desktop_images:
            # Use first image found on Desktop
            image_path = desktop_images[0]
            print(f"Using image from Desktop: {image_path}")
            image = cv2.imread(image_path)
            if image is None:
                print(f"Failed to load: {image_path}")
                sys.exit(1)
        else:
            # Create a simple test image with colored rectangles
            print("No image on Desktop, creating test image...")
            image = np.zeros((336, 336, 3), dtype=np.uint8)
            cv2.rectangle(image, (50, 50), (150, 150), (255, 0, 0), -1)   # Blue square
            cv2.rectangle(image, (180, 50), (280, 150), (0, 255, 0), -1)  # Green square
            cv2.rectangle(image, (115, 180), (215, 280), (0, 0, 255), -1) # Red square
            cv2.putText(image, "TEST", (100, 320), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    print(f"Image size: {image.shape[1]}x{image.shape[0]}")
    
    # Initialize VLM
    with HailoVLM(model=args.model, hef_path=args.hef) as vlm:
        print("\n" + "="*60)
        print(f"Question: {args.question}")
        print("="*60)
        
        response = vlm.ask_about_image(image, args.question)
        
        print(f"\nResponse:\n{response}")
        print("="*60)
        
        # Interactive mode
        print("\nEnter more questions (or 'quit' to exit):")
        first_msg = False  # Already sent first message above
        while True:
            try:
                question = input("\nYou: ").strip()
                if not question or question.lower() in ['quit', 'exit', 'q']:
                    break
                
                response = vlm.ask_about_image(image, question, first_message=first_msg)
                print(f"VLM: {response}")
                first_msg = False  # All subsequent messages are not first
                
            except KeyboardInterrupt:
                break
    
    print("\nDone!")


if __name__ == "__main__":
    main()
