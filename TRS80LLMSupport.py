# jonathanrothberg@gmail.com HELPER FUNCTIONS FOR TRS80 LLM SUPPORT
# AUGUST 24, 2024
# Updated to use Ollama instead of llama-cpp-python
# Install Ollama: https://ollama.ai/
# pip install requests

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import anthropic
# torch and transformers are lazy-imported when needed (see load_model / MyStreamer)
import requests
import json
import os
import platform
import re
import threading

def _make_streamer(tokenizer, skip_special_tokens=True, skip_prompt=True):
    """Factory that lazy-imports transformers and builds a MyStreamer instance."""
    from transformers import TextIteratorStreamer

    class MyStreamer(TextIteratorStreamer):
        def __init__(self, tok, skip_prompt_: bool = False, **decode_kwargs):
            super().__init__(tok, skip_prompt=skip_prompt_, **decode_kwargs)
            self.text_area = None
            self.internal_text = ""
            self.master = None

        def on_finalized_text(self, text: str, stream_end: bool = False):
            self.internal_text += text
            if self.text_area and self.master:
                self.master.after(0, lambda: self._safe_update_gui(text))

        def _safe_update_gui(self, text):
            if self.text_area:
                self.text_area.insert(tk.END, text)
                self.text_area.see(tk.END)
                self.text_area.update_idletasks()

    return MyStreamer(tokenizer, skip_prompt_=skip_prompt, skip_special_tokens=skip_special_tokens)

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
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(
            api_key=api_key
        )
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
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                models = response.json()
                return [model['name'] for model in models.get('models', [])]
            else:
                return []
        except Exception as e:
            print(f"Error getting Ollama models: {e}")
            return []

    def update_model_options(self):
        model_type = self.model_type_var.get()
        if model_type == "claude":
            self.model_menu['values'] = ["claude-sonnet-4-6", "claude-opus-4-6"]
        elif model_type == "transformer":
            self.model_menu['values'] = [f for f in os.listdir(self.transformer_dir) if os.path.isdir(os.path.join(self.transformer_dir, f))]
        elif model_type == "ollama":
            self.model_menu['values'] = self.get_ollama_models()
        self.model_menu.set('')

    def load_model(self, event=None):
        model_name = self.model_var.get()
        model_type = self.model_type_var.get()

        if model_type == "transformer":
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            model_path = os.path.join(self.transformer_dir, model_name)
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
        elif model_type == "ollama":
            # For Ollama, we don't need to load the model in memory
            # The model name is stored and used for API calls
            self.model = model_name

    def send_to_llm(self):
        self.send_button.config(state='disabled')  # Disable the button
        prompt = self.input_text.get("1.0", tk.END).strip()
        system_prompt = (
            "You are an expert TRS-80 Model I Level II BASIC programmer (1978). "
            "You write code for a faithful TRS-80 simulator with STRICT syntax rules. "
            "Code that works in modern BASIC will BREAK here. Follow these rules EXACTLY.\n\n"

            "========== RULES THAT BREAK CODE IF VIOLATED ==========\n\n"

            "1. EVERY line MUST have a line number. No exceptions.\n"
            "2. ALL keywords MUST be UPPERCASE: PRINT, FOR, GOTO, IF, THEN, etc.\n"
            "3. IF/THEN with a line number MUST use GOTO:\n"
            "   CORRECT:   IF X>5 THEN GOTO 200\n"
            "   WRONG:     IF X>5 THEN 200\n"
            "   The simulator does NOT support implicit GOTO after THEN.\n"
            "4. RND(n) returns a random integer from 1 to n (NOT 0 to n-1).\n"
            "   RND(0) returns a random float from 0 to 1.\n"
            "   Bare RND (no parentheses) returns a random float 0 to 1.\n"
            "5. Comparisons return -1 for TRUE, 0 for FALSE (not 1/0).\n"
            "   So IF (X>5) AND (Y<3) works because -1 AND -1 = -1 (true).\n"
            "6. Arrays MUST be declared with DIM before use. No auto-DIM.\n"
            "   DIM A(10) creates elements A(0) through A(10) — that is 11 elements.\n"
            "7. Only 1-dimensional arrays. NO 2D arrays like DIM A(5,5).\n"
            "   Simulate 2D with: INDEX = ROW*COLS + COL\n"
            "8. String variables MUST end with $: A$, N$, W$\n"
            "9. String literals MUST use double quotes: \"HELLO\"\n"
            "10. Multiple statements per line use colon: 10 A=1: B=2: PRINT A+B\n\n"

            "========== FEATURES THAT DO NOT EXIST ==========\n"
            "NEVER use any of these — they will cause errors:\n"
            "- WHILE/WEND, DO/LOOP, REPEAT/UNTIL\n"
            "- SELECT CASE, ELSEIF, ELSE IF (on separate line)\n"
            "- DEF FN, SUB, FUNCTION, END SUB\n"
            "- PRINT USING, LINE INPUT, WRITE\n"
            "- LOCATE, COLOR, SOUND, BEEP, SLEEP\n"
            "- LPRINT, OPEN, CLOSE, FILES (except tape I/O)\n"
            "- SWAP, ERASE, OPTION BASE\n"
            "- Boolean literals TRUE/FALSE (use -1 and 0)\n"
            "Use GOTO and GOSUB/RETURN for all control flow.\n\n"

            "========== SUPPORTED COMMANDS ==========\n"
            "PRINT expr [; or ,] expr  — Output (see formatting rules below)\n"
            "PRINT@ pos, expr          — Print at screen position (0-1023)\n"
            "LET var = expr            — Assignment (LET keyword is optional)\n"
            "INPUT [\"prompt\";] var    — Get user input with optional prompt\n"
            "IF cond THEN stmt [ELSE stmt] — Conditional (single line only)\n"
            "  IF/THEN can have multiple colon-separated stmts after THEN:\n"
            "  10 IF X>0 THEN PRINT X: GOTO 100\n"
            "FOR var = start TO end [STEP inc] — Loop\n"
            "NEXT [var]                — End of FOR loop\n"
            "GOTO linenum             — Jump to line\n"
            "GOSUB linenum            — Call subroutine\n"
            "RETURN                   — Return from GOSUB\n"
            "ON expr GOTO l1, l2, ... — Computed GOTO (1-based index)\n"
            "DIM var(size)            — Declare array (one per DIM statement)\n"
            "DATA v1, v2, ...         — Define data values\n"
            "READ var1, var2, ...     — Read next DATA values\n"
            "RESTORE                  — Reset DATA pointer to beginning\n"
            "REM comment              — Comment (ignored)\n"
            "CLS                      — Clear screen\n"
            "END                      — Stop program\n"
            "STOP                     — Pause program (can CONT)\n"
            "DELAY n                  — Pause n*10 milliseconds\n"
            "POKE addr, val           — Write to memory\n"
            "SET(x, y)               — Turn on pixel (x: 1-128, y: 1-48)\n"
            "RESET(x, y)             — Turn off pixel\n"
            "PRINT#-1, data           — Write to cassette tape\n"
            "INPUT#-1, variable       — Read from cassette tape\n\n"

            "========== FUNCTIONS ==========\n"
            "Math: ABS(x) INT(x) FIX(x) SGN(x) SQR(x)\n"
            "      SIN(x) COS(x) TAN(x) EXP(x) LOG(x)\n"
            "      RND(n) — integer 1..n; RND(0) — float 0..1\n"
            "String: LEN(s$) LEFT$(s$,n) RIGHT$(s$,n)\n"
            "        MID$(s$, start [,len]) — 1-based indexing\n"
            "        STR$(n) — number to string (leading space if positive)\n"
            "        VAL(s$) — string to number\n"
            "        CHR$(n) — ASCII code to character\n"
            "        ASC(s$) — first character to ASCII code\n"
            "        STRING$(count, char) — repeat a character\n"
            "        INSTR([start,] s$, find$) — find substring (1-based, 0=not found)\n"
            "System: PEEK(addr) — read memory\n"
            "        POINT(x,y) — pixel state (0 or 1)\n"
            "        INKEY$ — last key pressed (\"\" if none, non-blocking)\n\n"

            "========== OPERATORS (by precedence) ==========\n"
            "  ^              Exponentiation\n"
            "  * / MOD        Multiply, divide, modulo\n"
            "  + -            Add, subtract (+ also concatenates strings)\n"
            "  = <> < > <= >= Comparison (returns -1 true, 0 false)\n"
            "  NOT            Bitwise NOT (~value)\n"
            "  AND OR         Logical AND, OR\n"
            "String comparison with = and <> WORKS: IF A$=\"YES\" THEN ...\n\n"

            "========== PRINT FORMATTING ==========\n"
            "- Positive numbers print with a leading space:  PRINT 5  shows ' 5 '\n"
            "- Negative numbers print with minus sign:  PRINT -5  shows '-5 '\n"
            "- All numbers have a trailing space\n"
            "- No trailing .0 on whole numbers: PRINT 3.0 shows ' 3 '\n"
            "- Semicolon ; concatenates with no extra space\n"
            "- Comma , advances to next 16-column tab zone\n"
            "- Trailing ; or , suppresses the newline\n"
            "- TAB(n) in PRINT moves to column n\n"
            "- PRINT@ pos, expr — pos = row*64 + col (0-based, 0-1023)\n\n"

            "========== SCREEN & GRAPHICS ==========\n"
            "- Text: 64 columns x 16 rows\n"
            "- Graphics: 128 x 48 pixels (SET/RESET/POINT)\n"
            "- Coordinates are 1-based: x=1-128, y=1-48\n"
            "- Screen memory: 15360-16383 (PEEK/POKE)\n"
            "- Keyboard: PEEK(14400) for key code, INKEY$ for character\n\n"

            "========== WORKING CODE PATTERNS ==========\n"
            "Counting loop:\n"
            "  10 FOR I=1 TO 10\n"
            "  20 PRINT I;\n"
            "  30 NEXT I\n\n"
            "Input with validation:\n"
            "  10 INPUT \"ENTER 1-10\"; A\n"
            "  20 IF A<1 OR A>10 THEN GOTO 10\n\n"
            "String handling:\n"
            "  10 A$=\"HELLO WORLD\"\n"
            "  20 PRINT LEFT$(A$, 5)\n"
            "  30 IF A$=\"HELLO WORLD\" THEN PRINT \"MATCH\"\n\n"
            "Array with DIM:\n"
            "  10 DIM A(20)\n"
            "  20 FOR I=1 TO 20\n"
            "  30 A(I)=RND(100)\n"
            "  40 NEXT I\n\n"
            "Subroutine:\n"
            "  10 X=5: GOSUB 100\n"
            "  20 X=10: GOSUB 100\n"
            "  30 END\n"
            "  100 PRINT X*X\n"
            "  110 RETURN\n\n"
            "Game input loop with INKEY$:\n"
            "  10 CLS: PRINT \"PRESS Q TO QUIT\"\n"
            "  20 K$=INKEY$\n"
            "  30 IF K$=\"\" THEN GOTO 20\n"
            "  40 IF K$=\"Q\" THEN GOTO 100\n"
            "  50 PRINT \"YOU PRESSED: \"; K$\n"
            "  60 GOTO 20\n"
            "  100 PRINT \"BYE!\"\n"
            "  110 END\n\n"
            "Drawing a line:\n"
            "  10 FOR X=1 TO 128\n"
            "  20 SET(X, 24)\n"
            "  30 NEXT X\n\n"
            "Simulated 2D array (5x5 grid in 1D):\n"
            "  10 DIM G(24)\n"
            "  20 REM ACCESS ROW R, COL C AS G(R*5+C)\n"
            "  30 R=2: C=3\n"
            "  40 G(R*5+C) = 42\n"
            "  50 PRINT G(R*5+C)\n\n"

            "========== DEBUGGING EXPERTISE ==========\n"
            "When analyzing debug output or program state:\n"
            "- Look for infinite loops and incorrect GOTO targets\n"
            "- Check FOR loop bounds and STEP values\n"
            "- Verify GOSUB/RETURN stack balance\n"
            "- Examine DATA/READ pointer alignment\n"
            "- Identify array bounds issues (DIM size vs access index)\n"
            "- Check that IF/THEN uses GOTO for line number targets\n"
            "- Suggest specific line number fixes with corrected code\n\n"

            "========== FINAL CHECKLIST ==========\n"
            "Before returning code, verify:\n"
            "[ ] Every line has a line number (10, 20, 30...)\n"
            "[ ] All keywords are UPPERCASE\n"
            "[ ] IF/THEN line jumps use GOTO: IF x THEN GOTO n\n"
            "[ ] FOR loops have matching NEXT\n"
            "[ ] GOSUB calls have matching RETURN\n"
            "[ ] Arrays are DIMensioned before use\n"
            "[ ] No modern BASIC features (WHILE, ELSEIF, SUB, etc.)\n"
            "[ ] RND(n) gives 1..n, not 0..n-1\n"
            "[ ] String vars end with $, literals in double quotes\n"
            "[ ] No 2D arrays\n\n"
            "Always provide complete, runnable programs. "
            "Enclose BASIC code in ```BASIC and ``` tags."
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
            err_msg = f"Failed to get response from {model_type} model: {str(e)}"
            self.master.after(0, lambda: messagebox.showerror("Error", err_msg))
        finally:
            # Always re-enable button, but only once
            self.master.after(0, self.re_enable_button)

    def re_enable_button(self):
        print("Re-enabling button")  # Debug print
        self.send_button.config(state='normal')

    def send_to_claude(self, system_prompt, prompt):
        try:
            # Use the selected model from the dropdown, defaulting to the newest Claude Sonnet 4
            model_name = self.model_var.get() or "claude-sonnet-4-6"
            response = self.client.messages.create(
                model=model_name,
                max_tokens=self.max_length.get(),
                temperature=self.temperature.get(),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            # Thread-safe GUI update
            self.master.after(0, lambda: self.update_output(response.content[0].text))
        except Exception as e:
            # Thread-safe error dialog
            err_msg = f"Failed to get response from Claude: {str(e)}"
            self.master.after(0, lambda: messagebox.showerror("Error", err_msg))

    def my_streamer(self, text_area, tokenizer):
        return _make_streamer(tokenizer, skip_special_tokens=True, skip_prompt=True)

    def send_to_transformer(self, system_prompt, prompt):
        try:
            full_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:"
            inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.model.device)
            
            streamer = self.my_streamer(self.output_text, self.tokenizer)
            streamer.text_area = self.output_text
            streamer.master = self.master  # Set master for thread-safe updates
            
            generation_kwargs = {
                "input_ids": inputs["input_ids"],
                "max_new_tokens": self.max_length.get(),
                "temperature": self.temperature.get(),
                "streamer": streamer,
            }
            
            def generate_and_process():
                try:
                    self.model.generate(**generation_kwargs)
                    # Process streaming in the worker thread instead of main thread
                    for _ in streamer:
                        pass  # This loop is now in the worker thread
                    
                    # Schedule final output update on main thread
                    final_response = streamer.internal_text.strip()
                    self.master.after(0, lambda: self.update_output(final_response))
                except Exception as e:
                    err_msg = f"Transformer model error: {str(e)}"
                    self.master.after(0, lambda: messagebox.showerror("Error", err_msg))
            
            thread = threading.Thread(target=generate_and_process)
            thread.start()

        except Exception as e:
            err_msg = f"Failed to get response from Transformer model: {str(e)}"
            self.master.after(0, lambda: messagebox.showerror("Error", err_msg))

    def send_to_ollama(self, system_prompt, prompt):
        try:
            payload = {
                "model": self.model,
                "system": system_prompt,
                "prompt": prompt,
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
