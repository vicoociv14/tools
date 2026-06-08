"""Detect whether Teams is currently in a call (window-based preferred; audio fallback).

We enumerate Windows audio sessions via pycaw and look for any session whose
owning process is Teams (configurable exe names). When at least one such
session has State == AudioSessionState.Active (1), audio is flowing in/out of
Teams, which is the closest "in a call" signal we can get without poking
private Teams APIs.

Notification chimes can briefly trip this; consumers smooth it with consecutive
poll thresholds (see tray.py).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from typing import Iterable

import psutil

log = logging.getLogger(__name__)

# pycaw's AudioSessionState enum: Inactive=0, Active=1, Expired=2
_STATE_ACTIVE = 1


def is_teams_audio_active(process_names: Iterable[str]) -> bool:
    """Return True if any Teams process owns an active audio session.

    pycaw is imported lazily so its comtypes-driven CoInitializeEx happens on
    the calling thread (the dedicated teams-poll thread that ran
    CoInitializeEx(MULTITHREADED) for itself first), not on the main thread
    where soundcard already owns the COM apartment.
    """
    from pycaw.pycaw import AudioUtilities  # noqa: WPS433 - intentional lazy import

    names_lower = {n.lower() for n in process_names}
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception:
        log.exception("pycaw GetAllSessions failed")
        return False

    for session in sessions:
        proc = session.Process
        if proc is None:
            continue
        try:
            name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            log.debug("could not read process name", exc_info=True)
            continue

        if name.lower() not in names_lower:
            continue

        try:
            state = session.State
        except Exception:
            log.debug("could not read session state for %s", name, exc_info=True)
            continue

        if state == _STATE_ACTIVE:
            log.debug("teams active session: %s (pid=%s)", name, proc.pid)
            return True

    return False


# --- Window-based detection (preferred) -----------------------------------
#
# A Teams *call* opens a second visible top-level window (the meeting window) on
# top of the main app window, and closes it when the call ends - while the main
# window stays. Unlike the audio session (allocated permanently, only toggling
# Active/Inactive), this gives a clean start/end signal that also survives
# mid-call silence. Empirically: idle = 1 visible Teams window, in a call = 2+.

_user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)


def _teams_pids(process_names: Iterable[str]) -> set:
    names_lower = {n.lower() for n in process_names}
    pids = set()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info["name"] or "").lower() in names_lower:
                pids.add(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:  # noqa: BLE001
            continue
    return pids


def count_teams_windows(process_names: Iterable[str]) -> int:
    """Count visible, titled top-level windows owned by Teams processes."""
    pids = _teams_pids(process_names)
    if not pids:
        return 0
    count = 0

    def _cb(hwnd, _lparam):
        nonlocal count
        if not _user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and _user32.GetWindowTextLengthW(hwnd) > 0:
            count += 1
        return True

    try:
        _user32.EnumWindows(_EnumWindowsProc(_cb), 0)
    except Exception:
        log.exception("EnumWindows failed")
        return 0
    return count


def is_teams_in_call(process_names: Iterable[str], min_windows: int = 2) -> bool:
    """True when Teams has a call window open (>= min_windows visible windows).

    Flips on within a poll of the call window opening and off within a poll of it
    closing, and does NOT drop during mid-call silence - so recordings are never
    chopped. Caveats: a popped-out chat in its own window can read as a call, and
    minimising the main window to the tray during a call can drop the count.
    Switch teams_detect_method to "audio" in config to fall back.
    """
    n = count_teams_windows(process_names)
    if n:
        log.debug("teams visible windows: %d (in_call=%s)", n, n >= min_windows)
    return n >= min_windows


if __name__ == "__main__":
    import time
    import pythoncom
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
    names = ["ms-teams.exe", "Teams.exe"]
    print("polling every 2s. Ctrl-C to stop.")
    try:
        while True:
            wins = count_teams_windows(names)
            audio = is_teams_audio_active(names)
            print(f"{time.strftime('%H:%M:%S')}  windows={wins} in_call={wins >= 2}  audio_active={audio}")
            time.sleep(2)
    finally:
        pythoncom.CoUninitialize()
