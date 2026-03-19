#!/usr/bin/env python3
"""
Hailo Installation Verifier
Quick script to check if Hailo-10 is properly set up
"""

def main():
    print("Hailo-10 Installation Check")
    print("=" * 40)

    # Check 1: Python package
    try:
        from hailo_platform import pyhailort
        print("✓ Hailo Python package is installed")
        print(f"   Module: hailo_platform.pyhailort")
    except ImportError:
        print("✗ Hailo Python package not found")
        print("   Download from: https://hailo.ai/developer-zone/software-downloads/")
        return

    # Check 2: Device detection
    try:
        from hailo_platform import VDevice
        device = VDevice()
        print("✓ Hailo device connected and working")
    except Exception as e:
        print(f"✗ Error connecting to Hailo device: {e}")
        print("   Make sure your Hailo-10 is connected and powered on")

    # Check 3: CLI tools
    import subprocess
    try:
        result = subprocess.run(['hailortcli', '--version'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✓ Hailo CLI tools are working")
            print(f"   Version info: {result.stdout.strip()}")
        else:
            print("✗ Hailo CLI tools not working properly")
    except FileNotFoundError:
        print("✗ Hailo CLI tools not found in PATH")
        print("   Make sure hailort_*.deb package is installed")
    except Exception as e:
        print(f"✗ Error checking CLI tools: {e}")

    print("\nNext steps:")
    print("1. If all checks pass: You're ready to run LLMs!")
    print("2. Get LLM models from Hailo Model Zoo or compile your own")
    print("3. Run: python3 hailo_llm_runner.py")

if __name__ == "__main__":
    main()