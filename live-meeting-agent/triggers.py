import threading
import time
from typing import Callable


class IntervalTimer:
    def __init__(self, interval_seconds: float, callback: Callable[[], None]):
        self.interval = interval_seconds
        self.callback = callback
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        def loop():
            while not self.stop_flag.wait(self.interval):
                try:
                    self.callback()
                except Exception as exc:  # pragma: no cover
                    print(f"timer: callback error {exc!r}")
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_flag.set()


def register_hotkey(hotkey: str, callback: Callable[[], None]) -> Callable[[], None]:
    """Register a global hotkey. Returns an unregister function."""
    import keyboard
    keyboard.add_hotkey(hotkey, callback)
    return lambda: keyboard.remove_hotkey(hotkey)
