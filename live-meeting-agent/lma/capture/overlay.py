"""Borderless always-on-top mini-window that shows 'REC HH:MM:SS' while recording.

Tkinter has strict thread affinity (Tk root must live on the thread that
created it), so this runs on a dedicated daemon thread. Other threads
communicate via a command queue: .show(), .hide(), .stop() are safe from
anywhere.
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from typing import Callable, Optional

log = logging.getLogger(__name__)


class RecordingOverlay:
    def __init__(
        self,
        elapsed_provider: Callable[[], float],
        position: str = "top-right",
        margin_px: int = 20,
    ):
        self.elapsed_provider = elapsed_provider
        self.position = position
        self.margin_px = margin_px
        self._commands: "queue.Queue[str]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._root: Optional[tk.Tk] = None
        self._label: Optional[tk.Label] = None
        self._dot: Optional[tk.Label] = None
        self._visible: bool = False
        self._dot_on: bool = True  # for blink

    # ------------------------------------------------------------------
    # Public, thread-safe API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="whisp-rec-overlay", daemon=True)
        self._thread.start()

    def show(self) -> None:
        self._commands.put("show")

    def hide(self) -> None:
        self._commands.put("hide")

    def stop(self) -> None:
        self._commands.put("quit")

    # ------------------------------------------------------------------
    # Tk thread internals
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._root = tk.Tk()
            self._root.withdraw()
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)
            self._root.attributes("-alpha", 0.85)
            self._root.configure(bg="#1a1a1a")

            frame = tk.Frame(self._root, bg="#1a1a1a")
            frame.pack(padx=10, pady=4)
            self._dot = tk.Label(
                frame,
                text="●",
                fg="#dc3232",
                bg="#1a1a1a",
                font=("Segoe UI", 14, "bold"),
            )
            self._dot.pack(side=tk.LEFT)
            self._label = tk.Label(
                frame,
                text="REC 00:00",
                fg="white",
                bg="#1a1a1a",
                font=("Segoe UI", 11, "bold"),
            )
            self._label.pack(side=tk.LEFT, padx=(6, 2))

            self._position_window()
            self._tick()
            self._blink()
            self._poll()
            self._root.mainloop()
        except Exception:
            log.exception("overlay thread crashed")
        finally:
            log.debug("overlay thread exit")

    def _position_window(self) -> None:
        if not self._root:
            return
        self._root.update_idletasks()
        w = self._root.winfo_reqwidth()
        h = self._root.winfo_reqheight()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        m = self.margin_px
        if self.position == "top-right":
            x, y = sw - w - m, m
        elif self.position == "top-left":
            x, y = m, m
        elif self.position == "top-center":
            x, y = (sw - w) // 2, m
        elif self.position == "bottom-right":
            x, y = sw - w - m, sh - h - m - 60  # avoid taskbar
        elif self.position == "bottom-left":
            x, y = m, sh - h - m - 60
        else:
            x, y = sw - w - m, m
        self._root.geometry(f"+{x}+{y}")

    def _poll(self) -> None:
        if not self._root:
            return
        try:
            while True:
                cmd = self._commands.get_nowait()
                if cmd == "show" and not self._visible:
                    self._root.deiconify()
                    self._root.attributes("-topmost", True)
                    self._visible = True
                elif cmd == "hide" and self._visible:
                    self._root.withdraw()
                    self._visible = False
                elif cmd == "quit":
                    self._root.quit()
                    return
        except queue.Empty:
            pass
        self._root.after(100, self._poll)

    def _tick(self) -> None:
        if not self._root or not self._label:
            return
        if self._visible:
            elapsed = int(self.elapsed_provider())
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            text = f"REC {h:d}:{m:02d}:{s:02d}" if h else f"REC {m:02d}:{s:02d}"
            self._label.config(text=text)
        self._root.after(1000, self._tick)

    def _blink(self) -> None:
        if not self._root or not self._dot:
            return
        if self._visible:
            self._dot_on = not self._dot_on
            self._dot.config(fg="#dc3232" if self._dot_on else "#1a1a1a")
        self._root.after(700, self._blink)
