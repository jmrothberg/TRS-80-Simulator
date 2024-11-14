# jonathanrothberg@gmail.com HELPER FUNCTIONS FOR TRS80 LLM SUPPORT
# AUGUST 24, 2024
# #for UNIX with CUDA
#CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
#MAC
#CMAKE_ARGS="-DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_APPLE_SILICON_PROCESSOR=arm64 -DGGML_METAL=on" pip install --upgrade --verbose --force-reinstall --no-cache-dir llama-cpp-python

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import anthropic
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from llama_cpp import Llama
import os
import platform
import re
import threading

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

        # Add a new button to append output to input
        self.append_button = ttk.Button(self.control_frame, text="Append to Chat", command=self.append_to_chat)
        self.append_button.pack(side=tk.LEFT, padx=5)

        self.llm_window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_directories(self):
        if platform.system() == 'Darwin':  # macOS
            self.transformer_dir = "/Users/jonathanrothberg/Models_Transformer"
            self.gguf_dir = "/Users/jonathanrothberg/GGUF_Models"
        else:  # Assuming Linux/Unix for the other option
            self.transformer_dir = "/data/Models_Transformer"
            self.gguf_dir = "/data/GGUF_Models"

    def setup_llm(self):
        self.client = anthropic.Anthropic(
            api_key="enter you key here"
        )
        self.model = None
        self.tokenizer = None

    def create_llm_window(self):
        #self.llm_window = tk.Toplevel(self.master)
        self.llm_window.title("TRS-80 BASIC Companion")

        self.paned_window = ttk.PanedWindow(self.llm_window, orient=tk.VERTICAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # Input pane
        self.input_frame = ttk.Frame(self.paned_window)
        self.input_text = scrolledtext.ScrolledText(self.input_frame, wrap=tk.WORD)
        self.input_text.pack(fill=tk.BOTH, expand=True)
        self.paned_window.add(self.input_frame)

        # Output pane
        self.output_frame = ttk.Frame(self.paned_window)
        self.output_text = scrolledtext.ScrolledText(self.output_frame, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.paned_window.add(self.output_frame)

        # Control frame
        self.control_frame = ttk.Frame(self.llm_window)
        self.control_frame.pack(fill=tk.X, padx=5, pady=5)

        # Model selection
        self.model_type_var = tk.StringVar(value="claude")
        ttk.Radiobutton(self.control_frame, text="Claude", variable=self.model_type_var, value="claude", command=self.update_model_options).pack(side=tk.LEFT)
        ttk.Radiobutton(self.control_frame, text="Transformer", variable=self.model_type_var, value="transformer", command=self.update_model_options).pack(side=tk.LEFT)
        ttk.Radiobutton(self.control_frame, text="GGUF", variable=self.model_type_var, value="gguf", command=self.update_model_options).pack(side=tk.LEFT)

        self.model_var = tk.StringVar()
        self.model_menu = ttk.Combobox(self.control_frame, textvariable=self.model_var, state="readonly")
        self.model_menu.pack(side=tk.LEFT, padx=5)
        self.model_menu.bind("<<ComboboxSelected>>", self.load_model)

        # Temperature and max length sliders
        self.temperature = tk.DoubleVar(value=0.0)
        self.temperature_slider = ttk.Scale(self.control_frame, from_=0.0, to=1.0, variable=self.temperature, orient=tk.HORIZONTAL)
        self.temperature_slider.pack(side=tk.LEFT, padx=5)
        ttk.Label(self.control_frame, text="Temp").pack(side=tk.LEFT)

        self.max_length = tk.IntVar(value=1024)
        self.max_length_slider = ttk.Scale(self.control_frame, from_=64, to=8096, variable=self.max_length, orient=tk.HORIZONTAL)
        self.max_length_slider.pack(side=tk.LEFT, padx=5)
        ttk.Label(self.control_frame, text="Max Len").pack(side=tk.LEFT)

        # Buttons
        self.send_button = ttk.Button(self.control_frame, text="Send to LLM", command=self.send_to_llm)
        self.send_button.pack(side=tk.LEFT, padx=5)

        self.transfer_button = ttk.Button(self.control_frame, text="Transfer to TRS-80", command=self.transfer_to_trs80)
        self.transfer_button.pack(side=tk.LEFT, padx=5)

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

    def update_model_options(self):
        model_type = self.model_type_var.get()
        if model_type == "claude":
            self.model_menu['values'] = ["claude-3-sonnet-20240229"]
        elif model_type == "transformer":
            self.model_menu['values'] = [f for f in os.listdir(self.transformer_dir) if os.path.isdir(os.path.join(self.transformer_dir, f))]
        elif model_type == "gguf":
            self.model_menu['values'] = [f for f in os.listdir(self.gguf_dir) if f.endswith('.gguf')]
        self.model_menu.set('')

    def load_model(self, event=None):
        model_name = self.model_var.get()
        model_type = self.model_type_var.get()

        if model_type == "transformer":
            model_path = os.path.join(self.transformer_dir, model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, 
                device_map="auto", 
                torch_dtype=torch.float16,
                trust_remote_code=True  # Add this line
            )
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True  # Add this line
            )
        elif model_type == "gguf":
            model_path = os.path.join(self.gguf_dir, model_name)
            self.model = Llama(model_path=model_path, n_ctx=2048, n_threads=8)

    def send_to_llm(self):
        self.send_button.config(state='disabled')  # Disable the button
        prompt = self.input_text.get("1.0", tk.END).strip()
        system_prompt = ("You are an expert in TRS-80 Model I Level II BASIC. "
                         "Write simple code using only BASIC commands available in that model computer. "
                         "Arrays in basic start at 1 not 0. Never use multidimensional arrays. "
                         "Keep the math simple. "
                         "Check your math. The screen is 128x48. Starting wtih 1, 1 at the top left. "
                         "Available commands are: PRINT, FOR, NEXT, DIM, GOTO, GOSUB, RETURN, IF, THEN, ELSE, END, LET, TAB, PEEK, POKE"
                         "Available functions are: SIN, COS, TAN, ATN, EXP, LOG, SQR, INT, ABS, RND"
                         "Always enclose BASIC code in ```BASIC and ``` tags.")
        
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
            elif model_type == "gguf":
                self.send_to_gguf(system_prompt, prompt)
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Error", f"Failed to get response from {model_type} model: {str(e)}"))
        finally:
            self.master.after(0, self.re_enable_button)

    def re_enable_button(self):
        print("Re-enabling button")  # Debug print
        self.send_button.config(state='normal')

    def send_to_claude(self, system_prompt, prompt):
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
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

    def send_to_gguf(self, system_prompt, prompt):
        try:
            full_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:"
            response = self.model(
                full_prompt,
                max_tokens=self.max_length.get(),
                temperature=self.temperature.get(),
                stop=["User:", "\n"],
                echo=False
            )
            self.update_output(response['choices'][0]['text'].strip())
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get response from GGUF model: {str(e)}")
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

    def on_closing(self):
        self.simulator.on_llm_window_close()
