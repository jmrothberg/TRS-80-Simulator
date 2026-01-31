"""
TRS-80 BASIC LLM Support Module
===============================
Author: Jonathan M. Rothberg (jonathanrothberg@gmail.com)
Original Date: August 24, 2024
Last Updated: January 2025

Description:
    AI assistant integration for the TRS-80 BASIC Simulator.
    Supports multiple LLM backends: Claude, OpenAI, Ollama, and local Transformers.

Environment Variables (for cloud LLMs):
    ANTHROPIC_API_KEY - For Claude models
    OPENAI_API_KEY - For OpenAI/GPT models
    
    Set via: export ANTHROPIC_API_KEY=your_key_here

For local LLMs (no API key needed):
    - Ollama: Install from https://ollama.ai/, then run: ollama pull llama2
    - Transformers: Download HuggingFace models to ~/Models_Transformer

License: MIT
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import anthropic
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
import requests
import json
import os
import platform
import re
import threading

# Try to import openai for GPT support
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class MyStreamer(TextIteratorStreamer):
    def __init__(self, tokenizer, skip_prompt: bool = False, **decode_kwargs):
        super().__init__(tokenizer, skip_prompt=skip_prompt, **decode_kwargs)
        self.text_area = None
        self.internal_text = ""

    def on_finalized_text(self, text: str, stream_end: bool = False):
        self.internal_text += text
        if self.text_area:
            self.text_area.insert(tk.END, text)
            self.text_area.see(tk.END)
            self.text_area.update()

class TRS80LLMSupport:
    def __init__(self, master, simulator):
        self.master = master
        self.simulator = simulator
        self.llm_window = tk.Toplevel(master)
        self.llm_window.title("TRS-80 Assistant")
        self.setup_directories()
        self.setup_llm()
        self.create_llm_window()

        self.llm_window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_directories(self):
        if platform.system() == 'Darwin':  # macOS
            self.transformer_dir = "/Users/jonathanrothberg/Models_Transformer"
        else:  # Assuming Linux/Unix for the other option
            self.transformer_dir = "/data/Models_Transformer"
        
        # Ollama API endpoint
        self.ollama_url = "http://localhost:11434"

    def setup_llm(self):
        """
        Initialize LLM clients using environment variables for API keys.
        
        Required environment variables:
        - ANTHROPIC_API_KEY: For Claude models (export ANTHROPIC_API_KEY=your_key)
        - OPENAI_API_KEY: For OpenAI/GPT models (export OPENAI_API_KEY=your_key)
        
        Ollama and local Transformers do not require API keys.
        """
        # Initialize Anthropic client (Claude) - uses ANTHROPIC_API_KEY env var
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if self.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        else:
            self.client = None  # Will show warning when Claude is selected
            
        # Initialize OpenAI client - uses OPENAI_API_KEY env var
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if OPENAI_AVAILABLE and self.openai_api_key:
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
        else:
            self.openai_client = None
            
        self.model = None
        self.tokenizer = None

    def create_llm_window(self):
        #self.llm_window = tk.Toplevel(self.master)
        self.llm_window.title("TRS-80 BASIC Companion")
        # Size and position will be set by main window

        # Control frame - more compact for 7" screen - PACK FIRST to reserve space
        self.control_frame = ttk.Frame(self.llm_window)
        self.control_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)

        self.paned_window = ttk.PanedWindow(self.llm_window, orient=tk.VERTICAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # Input pane - font size to match other windows (Courier 10)
        self.input_frame = ttk.Frame(self.paned_window)
        self.input_text = scrolledtext.ScrolledText(self.input_frame, wrap=tk.WORD, font=("Courier", 10))
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.paned_window.add(self.input_frame)

        # Output pane - font size to match other windows (Courier 10)
        self.output_frame = ttk.Frame(self.paned_window)
        self.output_text = scrolledtext.ScrolledText(self.output_frame, wrap=tk.WORD, font=("Courier", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.paned_window.add(self.output_frame)
        
        # Set initial split to middle (50/50)
        self.llm_window.after(100, lambda: self.paned_window.sashpos(0, 120))

        # Model selection - compact for 7" screen
        self.model_type_var = tk.StringVar(value="claude")
        # Use smaller radio buttons with abbreviated text
        claude_rb = ttk.Radiobutton(self.control_frame, text="C", variable=self.model_type_var, value="claude", command=self.update_model_options)
        claude_rb.pack(side=tk.LEFT, padx=1)
        trans_rb = ttk.Radiobutton(self.control_frame, text="T", variable=self.model_type_var, value="transformer", command=self.update_model_options)
        trans_rb.pack(side=tk.LEFT, padx=1)
        ollama_rb = ttk.Radiobutton(self.control_frame, text="O", variable=self.model_type_var, value="ollama", command=self.update_model_options)
        ollama_rb.pack(side=tk.LEFT, padx=1)

        self.model_var = tk.StringVar()
        self.model_menu = ttk.Combobox(self.control_frame, textvariable=self.model_var, state="readonly", width=30, font=("Arial", 7))
        self.model_menu.pack(side=tk.LEFT, padx=1)
        self.model_menu.bind("<<ComboboxSelected>>", self.load_model)

        # Temperature and max length sliders - match debug window
        self.temperature = tk.DoubleVar(value=0.0)
        self.temperature_slider = ttk.Scale(self.control_frame, from_=0.0, to=1.0, variable=self.temperature, orient=tk.HORIZONTAL, length=40)
        self.temperature_slider.pack(side=tk.LEFT, padx=1)
        ttk.Label(self.control_frame, text="T", font=("Arial", 7)).pack(side=tk.LEFT)

        self.max_length = tk.IntVar(value=1024)
        self.max_length_slider = ttk.Scale(self.control_frame, from_=64, to=8096, variable=self.max_length, orient=tk.HORIZONTAL, length=40)
        self.max_length_slider.pack(side=tk.LEFT, padx=1)
        ttk.Label(self.control_frame, text="L", font=("Arial", 7)).pack(side=tk.LEFT)

        # Create style for buttons - one point larger (Arial 8)
        style = ttk.Style()
        style.configure('Small.TButton', font=('Arial', 8))

        # Buttons - Arial 8 font, 50% wider for text fit
        self.send_button = ttk.Button(self.control_frame, text="Send", command=self.send_to_llm, width=6, style='Small.TButton')
        self.send_button.pack(side=tk.LEFT, padx=1)

        self.transfer_button = ttk.Button(self.control_frame, text="Transfer", command=self.transfer_to_trs80, width=8, style='Small.TButton')
        self.transfer_button.pack(side=tk.LEFT, padx=1)

        # Add append button for 7" screen
        self.append_button = ttk.Button(self.control_frame, text="Append", command=self.append_to_chat, width=6, style='Small.TButton')
        self.append_button.pack(side=tk.LEFT, padx=1)

        self.create_right_click_menu(self.input_text)
        self.create_right_click_menu(self.output_text)

        self.update_model_options()

    def create_right_click_menu(self, text_widget):
        menu = tk.Menu(self.llm_window, tearoff=0)
        menu.add_command(label="Cut", command=lambda: text_widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: text_widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: text_widget.event_generate("<<Paste>>"))
        menu.add_command(label="Clear", command=lambda: text_widget.delete(1.0, tk.END))
        menu.add_command(label="Select All", command=lambda: text_widget.tag_add(tk.SEL, "1.0", tk.END))
        
        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)
            return "break"  # Prevent default behavior
        
        # Bind for different systems and mouse buttons
        for button in ("<Button-2>", "<Button-3>", "<Control-Button-1>", "<Control-Button-2>"):
            text_widget.bind(button, show_menu)

    def get_ollama_models(self):
        """Get list of available Ollama models"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json()
                model_list = [model['name'] for model in models.get('models', [])]
                return model_list if model_list else []
            else:
                print(f"Ollama API returned status {response.status_code}")
                return []
        except requests.exceptions.ConnectionError:
            print("Ollama is not running or not installed")
            return []
        except requests.exceptions.Timeout:
            print("Ollama connection timed out")
            return []
        except Exception as e:
            print(f"Error getting Ollama models: {e}")
            return []

    def update_model_options(self):
        """Update the model dropdown based on selected provider type."""
        model_type = self.model_type_var.get()
        if model_type == "claude":
            if not self.anthropic_api_key:
                messagebox.showwarning("API Key Missing", 
                    "ANTHROPIC_API_KEY environment variable not set.\n\n"
                    "Set it with:\nexport ANTHROPIC_API_KEY=your_key_here\n\n"
                    "Then restart the application.")
            self.model_menu['values'] = ["claude-sonnet-4-0", "claude-opus-4-0"]
        elif model_type == "transformer":
            if os.path.exists(self.transformer_dir):
                try:
                    models = [f for f in os.listdir(self.transformer_dir) if os.path.isdir(os.path.join(self.transformer_dir, f))]
                    if models:
                        self.model_menu['values'] = models
                    else:
                        self.model_menu['values'] = ["No models found in directory"]
                except Exception as e:
                    self.model_menu['values'] = [f"Error reading models: {str(e)}"]
            else:
                self.model_menu['values'] = ["Models directory not found - please set up transformer models"]
        elif model_type == "ollama":
            models = self.get_ollama_models()
            if not models:
                self.model_menu['values'] = ["Ollama not available - please install and start Ollama"]
            else:
                self.model_menu['values'] = models
        self.model_menu.set('')

    def load_model(self, event=None):
        model_name = self.model_var.get()
        model_type = self.model_type_var.get()
        
        # Check if user selected an error message instead of a real model
        if not model_name or "not found" in model_name.lower() or "not available" in model_name.lower() or "error" in model_name.lower():
            self.output_text.insert(tk.END, f"Please set up {model_type} models before selecting one.\n")
            return

        if model_type == "transformer":
            try:
                model_path = os.path.join(self.transformer_dir, model_name)
                if not os.path.exists(model_path):
                    self.output_text.insert(tk.END, f"Model path does not exist: {model_path}\n")
                    return
                    
                self.output_text.insert(tk.END, f"Loading transformer model: {model_name}...\n")
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_path, 
                    device_map="auto", 
                    torch_dtype=torch.float16,
                    trust_remote_code=True
                )
                self.tokenizer = AutoTokenizer.from_pretrained(
                    model_path,
                    trust_remote_code=True
                )
                self.output_text.insert(tk.END, f"Model loaded successfully!\n")
            except Exception as e:
                self.output_text.insert(tk.END, f"Error loading transformer model: {str(e)}\n")
                self.model = None
                self.tokenizer = None
        elif model_type == "ollama":
            # For Ollama, we don't need to load the model in memory
            # The model name is stored and used for API calls
            self.model = model_name
            self.output_text.insert(tk.END, f"Selected Ollama model: {model_name}\n")

    def send_to_llm(self):
        self.send_button.config(state='disabled')  # Disable the button
        
        # Check if a valid model is selected
        model_name = self.model_var.get()
        model_type = self.model_type_var.get()
        
        if not model_name or "not found" in model_name.lower() or "not available" in model_name.lower() or "error" in model_name.lower():
            self.output_text.insert(tk.END, f"\nPlease select a valid {model_type} model first. Set up the appropriate AI service:\n")
            if model_type == "ollama":
                self.output_text.insert(tk.END, "- Install Ollama from https://ollama.ai/\n- Run 'ollama pull llama2' or another model\n")
            elif model_type == "transformer":
                self.output_text.insert(tk.END, f"- Set up transformer models in {self.transformer_dir}\n")
            elif model_type == "claude":
                self.output_text.insert(tk.END, "- Claude models should be available by default\n")
            self.send_button.config(state='normal')
            return
        
        prompt = self.input_text.get("1.0", tk.END).strip()
        if not prompt.strip():
            self.output_text.insert(tk.END, "\nPlease enter a prompt before sending.\n")
            self.send_button.config(state='normal')
            return
            
        system_prompt = (
            "You are an expert in TRS-80 Model I Level II BASIC programming from 1978 and debugging assistant. "
            "This is a very limited BASIC interpreter with strict syntax rules. "
            "You must write code that works EXACTLY as implemented in this specific simulator.\n\n"
            
            "DEBUGGING EXPERTISE:\n"
            "When analyzing debug output or program state information:\n"
            "- Look for infinite loops, incorrect variable assignments, logic errors\n"
            "- Check FOR loop bounds and STEP values\n"
            "- Verify GOSUB/RETURN stack balance\n"
            "- Examine DATA/READ pointer alignment\n"
            "- Identify array bounds issues\n"
            "- Check for syntax errors in TRS-80 BASIC context\n"
            "- Suggest specific line number fixes\n"
            "- Provide corrected code snippets when possible\n\n"
            
            "CRITICAL LIMITATIONS:\n"
            "- All programs must use line numbers (10, 20, 30, etc.)\n"
            "- Variable names: single letter or letter+digit (A, B1, X$, etc.)\n"
            "- String variables must end with $ (A$, NAME$, etc.)\n"
            "- Arrays start at index 0 but BASIC convention uses 1-based indexing\n"
            "- Screen is 64 columns x 16 rows for text, 128x48 pixels for graphics\n"
            "- Graphics coordinates are 1-based (1,1 to 128,48)\n"
            "- No multidimensional arrays\n"
            "- No subroutines with parameters\n"
            "- No local variables\n\n"
            
            "SUPPORTED COMMANDS:\n"
            "- PRINT [expression] [,;] - Output text/numbers\n"
            "- PRINT@ position, text - Print at specific screen position\n"
            "- LET variable = expression - Assignment (LET is optional)\n"
            "- INPUT [\"prompt\";] variable - Get user input\n"
            "- IF condition THEN statement [ELSE statement]\n"
            "- FOR variable = start TO end [STEP increment]\n"
            "- NEXT [variable]\n"
            "- GOTO line_number\n"
            "- GOSUB line_number / RETURN\n"
            "- ON expression GOTO line1, line2, ...\n"
            "- DIM array(size) - Declare array\n"
            "- DATA value1, value2, ... / READ variable1, variable2, ...\n"
            "- RESTORE - Reset DATA pointer\n"
            "- REM comment\n"
            "- CLS - Clear screen\n"
            "- END - Stop program\n"
            "- STOP - Pause program\n"
            "- POKE address, value - Write to memory\n"
            "- SET(x,y) - Turn on pixel\n"
            "- RESET(x,y) - Turn off pixel\n"
            "- PRINT#-1,data - Write to tape\n"
            "- INPUT#-1,variable - Read from tape\n\n"
            
            "MATHEMATICAL FUNCTIONS:\n"
            "- ABS(x) - Absolute value\n"
            "- INT(x) - Integer part\n"
            "- FIX(x) - Truncate to integer\n"
            "- SGN(x) - Sign (-1, 0, or 1)\n"
            "- SQR(x) - Square root\n"
            "- SIN(x), COS(x), TAN(x) - Trigonometric\n"
            "- EXP(x), LOG(x) - Exponential and natural log\n"
            "- RND - Random number 0-1, RND(n) - Random 0 to n-1\n\n"
            
            "STRING FUNCTIONS:\n"
            "- LEN(string$) - Length of string\n"
            "- LEFT$(string$, n) - Leftmost n characters\n"
            "- RIGHT$(string$, n) - Rightmost n characters\n"
            "- MID$(string$, start[, length]) - Substring (1-based)\n"
            "- STR$(number) - Convert number to string\n"
            "- VAL(string$) - Convert string to number\n"
            "- CHR$(code) - ASCII code to character\n"
            "- ASC(string$) - Character to ASCII code\n"
            "- STRING$(count, char) - Repeat character\n"
            "- INSTR([start,] string$, substring$) - Find substring\n\n"
            
            "SYSTEM FUNCTIONS:\n"
            "- PEEK(address) - Read memory (14400=keyboard, 15360-16383=screen)\n"
            "- POINT(x,y) - Check if pixel is on (returns 0 or 1)\n"
            "- INKEY$ - Get pressed key (non-blocking)\n\n"
            
            "OPERATORS:\n"
            "- Arithmetic: +, -, *, /, ^ (exponentiation), MOD\n"
            "- Comparison: =, <>, <, >, <=, >=\n"
            "- Logical: AND, OR, NOT\n"
            "- String: + (concatenation)\n\n"
            
            "SYNTAX RULES:\n"
            "- Use : to separate multiple statements on one line\n"
            "- PRINT items separated by ; (no space) or , (tab to column)\n"
            "- String literals in double quotes\n"
            "- Comments with REM\n"
            "- All keywords in UPPERCASE\n"
            "- Line numbers required, typically increment by 10\n\n"
            
            "MEMORY MAP:\n"
            "- 14400: Keyboard input\n"
            "- 15360-16383: Screen memory (64x16 text)\n\n"
            
            "Always provide complete, runnable programs with line numbers. "
            "Test your logic carefully. Keep programs simple and educational. "
            "Always enclose BASIC code in ```BASIC and ``` tags."
        )
        
        model_type = self.model_type_var.get()
        
        # Append the user's message to the chat history
        self.input_text.insert(tk.END, f"\nUser: {prompt}\n")
        
        # Start a new thread for LLM processing
        thread = threading.Thread(target=self.process_llm_request, args=(model_type, system_prompt, prompt))
        thread.start()

    def process_llm_request(self, model_type, system_prompt, prompt):
        try:
            if model_type == "claude":
                self.send_to_claude(system_prompt, prompt)
            elif model_type == "transformer":
                self.send_to_transformer(system_prompt, prompt)
            elif model_type == "ollama":
                self.send_to_ollama(system_prompt, prompt)
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Error", f"Failed to get response from {model_type} model: {str(e)}"))
        finally:
            self.master.after(0, self.re_enable_button)

    def re_enable_button(self):
        print("Re-enabling button")  # Debug print
        self.send_button.config(state='normal')

    def send_to_claude(self, system_prompt, prompt):
        """Send request to Anthropic Claude API."""
        try:
            if not self.client:
                raise Exception("ANTHROPIC_API_KEY environment variable not set.\n"
                              "Set it with: export ANTHROPIC_API_KEY=your_key_here")
            # Use the selected model from the dropdown, defaulting to the newest Claude Sonnet 4
            model_name = self.model_var.get() or "claude-sonnet-4-0"
            response = self.client.messages.create(
                model=model_name,
                max_tokens=self.max_length.get(),
                temperature=self.temperature.get(),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            self.update_output(response.content[0].text)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get response from Claude: {str(e)}")
        finally:
            self.master.after(0, self.re_enable_button)

    def my_streamer(self, text_area, tokenizer):
        return MyStreamer(tokenizer, skip_special_tokens=True, skip_prompt=True)

    def send_to_transformer(self, system_prompt, prompt):
        try:
            full_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:"
            inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.model.device)
            
            streamer = self.my_streamer(self.output_text, self.tokenizer)
            streamer.text_area = self.output_text
            
            generation_kwargs = {
                "input_ids": inputs["input_ids"],
                "max_new_tokens": self.max_length.get(),
                "temperature": self.temperature.get(),
                "streamer": streamer,
            }
            
            def generate_and_re_enable():
                try:
                    self.model.generate(**generation_kwargs)
                finally:
                    self.master.after(0, self.re_enable_button)
            
            thread = threading.Thread(target=generate_and_re_enable)
            thread.start()

            for _ in streamer:
                pass  # This loop is necessary to keep the streaming going

            final_response = streamer.internal_text.strip()
            self.master.after(0, lambda: self.update_output(final_response))
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Error", f"Failed to get response from Transformer model: {str(e)}"))
            self.master.after(0, self.re_enable_button)

    def re_enable_button(self):
        print("Re-enabling button")  # Debug print
        self.send_button.config(state='normal')

    def send_to_ollama(self, system_prompt, prompt):
        try:
            full_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:"
            
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature.get(),
                    "num_predict": self.max_length.get()
                }
            }
            
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload)
            
            if response.status_code == 200:
                result = response.json()
                self.master.after(0, lambda: self.update_output(result['response']))
            else:
                error_msg = f"Ollama API error: {response.status_code} - {response.text}"
                self.master.after(0, lambda: messagebox.showerror("Error", error_msg))
                
        except Exception as e:
            error_msg = f"Failed to get response from Ollama model: {str(e)}"
            self.master.after(0, lambda: messagebox.showerror("Error", error_msg))
        finally:
            self.master.after(0, self.re_enable_button)

    def update_output(self, text):
        self.output_text.config(state='normal')
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)
        self.output_text.config(state='normal')
        self.output_text.see(tk.END)

    def transfer_to_trs80(self):
        try:
            selected_text = self.output_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected_text = self.output_text.get("1.0", tk.END)
        
        basic_code = self.extract_basic_code(selected_text)
        if basic_code:
            self.simulator.input_area.insert(tk.END, basic_code)
        else:
            messagebox.showinfo("No BASIC Code", "No BASIC code found in the selected text.")

    def extract_basic_code(self, text):
        basic_sections = []
        pattern = r'```(?:BASIC|basic)\s*([\s\S]*?)\s*```'
        matches = re.finditer(pattern, text, re.IGNORECASE)
        
        for match in matches:
            basic_sections.append(match.group(1).strip())
        
        if basic_sections:
            return "\n".join(basic_sections) + "\n"
        return ""

    def append_to_chat(self):
        output_text = self.output_text.get("1.0", tk.END).strip()
        if output_text:
            chat_append = f"\nAssistant: {output_text}\n\nUser: "
            self.input_text.insert(tk.END, chat_append)
            self.input_text.see(tk.END)
            self.output_text.delete("1.0", tk.END)

    def append_debug_output(self, debug_text):
        self.input_text.insert(tk.END, "\n--- Debug Output ---\n" + debug_text + "\n--- End Debug Output ---\n")
        self.input_text.see(tk.END)
    
    def append_program_state(self, state_text):
        """Append program state information to the input area"""
        self.input_text.insert(tk.END, "\n--- Program State ---\n" + state_text + "\n--- End Program State ---\n")
        self.input_text.see(tk.END)

    def on_closing(self):
        self.simulator.on_llm_window_close()
