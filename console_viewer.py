import customtkinter as ctk
import threading
import queue
import subprocess
import re


class ConsoleViewer(ctk.CTkToplevel):
    def __init__(self, parent, process: subprocess.Popen = None, title="Game Console"):
        super().__init__(parent)
        self.title(title)
        self.geometry("800x500")
        self.minsize(600, 300)
        self.transient(parent)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.text_box = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(family="Consolas", size=11))
        self.text_box.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(btn_frame, text="Clear", width=80, fg_color="#555555",
                      command=self.clear_output).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="Copy All", width=80, fg_color="#2980b9",
                      command=self.copy_output).pack(side="left", padx=2)
        self.pause_btn = ctk.CTkButton(btn_frame, text="Pause", width=80, fg_color="#e67e22",
                                       command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=2)

        self.process = process
        self.log_queue = queue.Queue()
        self.paused = False
        self.running = True
        self._max_lines = 10000

        self.after(100, self._poll_queue)

    def write_output(self, text: str):
        if self.paused or not self.running:
            return
        self.text_box.configure(state="normal")

        for line in text.splitlines(True):
            cleaned = self._clean_ansi(line)
            self.text_box.insert("end", cleaned)

        line_count = int(self.text_box.index("end-1c").split(".")[0])
        if line_count > self._max_lines:
            self.text_box.delete("1.0", f"{line_count - self._max_lines + 1}.0")

        self.text_box.see("end")
        self.text_box.configure(state="disabled")

    def _clean_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def clear_output(self):
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.configure(state="disabled")

    def copy_output(self):
        content = self.text_box.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.configure(text="Resume" if self.paused else "Pause",
                                 fg_color="#27ae60" if self.paused else "#e67e22")

    def _poll_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.write_output(line)
        except queue.Empty:
            pass
        if self.running:
            self.after(50, self._poll_queue)

    def feed_line(self, line: str):
        self.log_queue.put(line)

    def on_close(self):
        self.running = False
        self.destroy()


def spawn_console(parent, process: subprocess.Popen, title="Game Console") -> ConsoleViewer:
    viewer = ConsoleViewer(parent, process, title)

    def reader(stream, queue_target):
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                queue_target(line)
            stream.close()
        except Exception:
            pass

    if process.stdout:
        t = threading.Thread(target=reader, args=(process.stdout, viewer.log_queue), daemon=True)
        t.start()
    if process.stderr:
        t = threading.Thread(target=reader, args=(process.stderr, viewer.log_queue), daemon=True)
        t.start()

    return viewer
