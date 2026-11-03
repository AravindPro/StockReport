import threading
import tkinter as tk
from tkinter import ttk

import argparse
from agent import build_agent
import tkinter as tk
from logging_config import configure_logging

configure_logging()

class Collapsible(ttk.Frame):
    def __init__(self, master, title="Tool Calls"):
        super().__init__(master)
        self.shown = False
        self.btn = ttk.Button(self, text="▶ " + title, command=self.toggle)
        self.btn.pack(fill="x")
        self.body = ttk.Frame(self)

    def toggle(self):
        self.shown = not self.shown
        if self.shown:
            self.btn.configure(text="▼ Tool Calls")
            self.body.pack(fill="x", padx=15, pady=2)
        else:
            self.btn.configure(text="▶ Tool Calls")
            self.body.pack_forget()

    def add(self, txt):
        l = tk.Label(
            self.body,
            text=txt,
            justify="left",
            anchor="w",
            wraplength=750,
            bg="#2b2b2b",
            fg="#f5f5f5",
            relief="groove",
            padx=6,
            pady=4,
        )
        l.pack(fill="x", pady=2)


class ChatUI:
    def __init__(self, root, agent):
        self.root = root
        self.agent = agent
        self.history = []
        self.history_lock = threading.Lock()

        root.title("OpenRouter Agent")
        root.geometry("900x700")
        root.configure(bg="#1e1e1e")

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#f5f5f5")
        style.configure("TEntry", fieldbackground="#2b2b2b", foreground="#f5f5f5", background="#2b2b2b")
        style.configure("TButton", background="#3a3a3a", foreground="#f5f5f5")
        style.map("TButton", background=[("active", "#4a4a4a"), ("pressed", "#2f2f2f")])

        chat_area = ttk.Frame(root)
        chat_area.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(chat_area, highlightthickness=0, bg="#1e1e1e")
        self.scroll = ttk.Scrollbar(chat_area, orient="vertical", command=self.canvas.yview)
        self.frame = ttk.Frame(self.canvas)

        self.frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.frame_window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.bind("<Configure>", self._resize_chat_frame)
        self.canvas.bind("<MouseWheel>", self._mousewheel)
        self.canvas.bind("<Button-4>", lambda event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda event: self.canvas.yview_scroll(1, "units"))

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        bottom = ttk.Frame(root)
        bottom.pack(fill="x")

        self.entry = ttk.Entry(bottom)
        self.entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.entry.bind("<Return>", self.send)

        ttk.Button(bottom, text="Send", command=self.send).pack(side="right", padx=5)

    def _resize_chat_frame(self, event):
        """Keep chat bubbles the width of the visible canvas."""
        self.canvas.itemconfigure(self.frame_window, width=event.width)

    def _mousewheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def _scroll_to_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def bubble(self, who, text):
        outer = ttk.Frame(self.frame)
        outer.pack(fill="x", padx=10, pady=6, anchor="w")

        color = "#2f4b7c" if who == "You" else "#2b2b2b"

        tk.Label(
            outer,
            text=who,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            bg="#1e1e1e",
            fg="#f5f5f5",
        ).pack(anchor="w")

        lbl = tk.Label(
            outer,
            text=text,
            bg=color,
            fg="#f5f5f5",
            justify="left",
            anchor="w",
            wraplength=780,
            padx=8,
            pady=8,
        )
        lbl.pack(anchor="w", fill="x")

        self.root.after_idle(self._scroll_to_bottom)

        return outer, lbl

    def send(self, event=None):
        prompt = self.entry.get().strip()
        if not prompt:
            return
        self.entry.delete(0, tk.END)

        with self.history_lock:
            self.history.append(("user", prompt))

        self.bubble("You", prompt)

        threading.Thread(target=self.run_agent, args=(prompt,), daemon=True).start()

    def run_agent(self, prompt):
        created = threading.Event()
        chat_widgets = {}

        def create_assistant_message():
            assistant_frame, assistant_label = self.bubble("Assistant", "Thinking...")
            tools = Collapsible(assistant_frame)
            tools.pack(fill="x", pady=5)
            chat_widgets.update(label=assistant_label, tools=tools)
            created.set()

        self.root.after(0, create_assistant_message)
        created.wait()
        assistant_label = chat_widgets["label"]
        tools = chat_widgets["tools"]

        final = ""

        try:
            with self.history_lock:
                history_messages = list(self.history)

            for event in self.agent.stream(
                {"messages": history_messages},
                stream_mode="updates",
            ):
                for node, data in event.items():
                    msgs = data.get("messages", [])
                    for m in msgs:
                        t = type(m).__name__

                        if t == "ToolMessage":
                            txt = getattr(m, "content", "")
                            self.root.after(
                                0,
                                lambda txt=txt: (
                                    tools.add(txt if len(str(txt)) < 1000 else str(txt)[:1000] + "..."),
                                    self._scroll_to_bottom(),
                                )
                            )

                        elif hasattr(m, "tool_calls") and m.tool_calls:
                            for tc in m.tool_calls:
                                self.root.after(
                                    0,
                                    lambda tc=tc: tools.add(
                                        f"Calling: {tc['name']}\nArgs: {tc['args']}"
                                    ),
                                )

                        elif getattr(m, "content", ""):
                            final = m.content
                            self.root.after(
                                0,
                                lambda text=final: (assistant_label.config(text=text), self._scroll_to_bottom())
                            )

            if final:
                with self.history_lock:
                    self.history.append(("assistant", final))

        except Exception as e:
            self.root.after(
                0,
                lambda: (assistant_label.config(text=str(e)), self._scroll_to_bottom())
            )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="inclusionai/ling-3.0-flash:free",
    )
    args = parser.parse_args()

    agent = build_agent(args.model)

    root = tk.Tk()
    ChatUI(root, agent)
    root.mainloop()


if __name__ == "__main__":
    main()
