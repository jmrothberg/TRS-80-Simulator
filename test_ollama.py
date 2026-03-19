#!/usr/bin/env python3
"""
Simple test script to verify Ollama integration for TRS-80 Simulator
"""

import requests
import json

def test_ollama_connection():
    """Test if Ollama is running and accessible"""
    ollama_url = "http://localhost:11434"
    
    try:
        # Test basic connectivity
        response = requests.get(f"{ollama_url}/api/version", timeout=5)
        if response.status_code == 200:
            print("✓ Ollama is running and accessible")
            return True
        else:
            print(f"✗ Ollama returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to Ollama. Is it running? Try: ollama serve")
        return False
    except requests.exceptions.Timeout:
        print("✗ Connection to Ollama timed out")
        return False
    except Exception as e:
        print(f"✗ Error connecting to Ollama: {e}")
        return False

def test_ollama_models():
    """Test if any models are available"""
    ollama_url = "http://localhost:11434"
    
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json()
            model_list = models.get('models', [])
            
            if model_list:
                print(f"✓ Found {len(model_list)} available models:")
                for model in model_list:
                    print(f"  - {model['name']}")
                return True
            else:
                print("✗ No models found. Try downloading one with: ollama pull llama2")
                return False
        else:
            print(f"✗ Failed to get models list: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error getting models: {e}")
        return False

def test_ollama_generation():
    """Test basic text generation"""
    ollama_url = "http://localhost:11434"
    
    try:
        # Get available models first
        response = requests.get(f"{ollama_url}/api/tags", timeout=10)
        if response.status_code != 200:
            print("✗ Cannot get models list for generation test")
            return False
        
        models = response.json().get('models', [])
        if not models:
            print("✗ No models available for generation test")
            return False
        
        # Use the first available model
        model_name = models[0]['name']
        print(f"Testing generation with model: {model_name}")
        
        payload = {
            "model": model_name,
            "prompt": "Write a simple BASIC program that prints 'Hello World'",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 100
            }
        }
        
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if 'response' in result and result['response'].strip():
                print("✓ Text generation successful")
                print(f"Sample output: {result['response'][:100]}...")
                return True
            else:
                print("✗ Empty response from model")
                return False
        else:
            print(f"✗ Generation failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error during generation test: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Ollama Integration for TRS-80 Simulator")
    print("=" * 50)
    
    # Test connection
    if not test_ollama_connection():
        print("\nSetup Instructions:")
        print("1. Install Ollama from https://ollama.ai/")
        print("2. Start Ollama service: ollama serve")
        print("3. Download a model: ollama pull llama2")
        return
    
    # Test models
    if not test_ollama_models():
        print("\nTo download models:")
        print("ollama pull llama2")
        print("ollama pull codellama")
        print("ollama pull mistral")
        return
    
    # Test generation
    print("\nTesting text generation...")
    if test_ollama_generation():
        print("\n✓ All tests passed! Ollama integration is ready.")
    else:
        print("\n✗ Generation test failed. Check model availability.")

if __name__ == "__main__":
    main() 