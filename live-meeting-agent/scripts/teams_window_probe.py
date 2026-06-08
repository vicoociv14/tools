"""Diagnostic 2: watch Teams *windows* (not audio) to find a precise call signal.

The audio sessions can't tell 'call ended' from 'idle'. A separate Teams call
window might. Read-only. Run it, then: (1) Teams idle ~10 s, (2) join a call
~15 s, (3) end the call ~15 s. Paste the output. We are looking for a window
(title or class) that appears ONLY while you are in a call.
"""
import ctypes
import ctypes.wintypes
import time

import psutil

user32 = ctypes.windll.user32
TEAMS = {"ms-teams.exe", "teams.exe"}

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)


def teams_pids() -> set[int]:
    pids = set()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info["name"] or "").lower() in TEAMS:
                pids.add(p.info["pid"])
        except Exception:  # noqa: BLE001
            pass
    return pids


def list_windows(pids: set[int]):
    out = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        out.append((title_buf.value, cls_buf.value))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


print("watching Teams windows every 2 s. phases: (1) idle (2) in call (3) ended. Ctrl+C to stop.")
print("-" * 60)
try:
    while True:
        pids = teams_pids()
        wins = list_windows(pids)
        titled = [w for w in wins if w[0].strip()]
        stamp = time.strftime("%H:%M:%S")
        print(f"{stamp} procs={len(pids)} visible_windows={len(wins)} titled={len(titled)}")
        for t, c in titled:
            print(f"        title={t!r} class={c!r}")
        time.sleep(2)
except KeyboardInterrupt:
    print("stopped")
