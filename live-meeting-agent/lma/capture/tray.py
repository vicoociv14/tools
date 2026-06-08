"""Tray icon + hotkey + Teams auto-detect orchestration.

Run via pythonw.exe (no console window) for a silent background process.

State model:
  IDLE  -> START_MANUAL (hotkey or menu)              -> RECORDING_MANUAL
        -> START_AUTO   (Teams sustained-active)      -> RECORDING_AUTO
  RECORDING_MANUAL -> STOP (hotkey/menu) -> IDLE
  RECORDING_AUTO   -> STOP (Teams sustained-inactive) -> IDLE
  RECORDING_AUTO   -> STOP (hotkey/menu) -> IDLE + suppress auto-restart for 60s
                                            (so re-joining doesn't get caught immediately)

Hotkey is registered via Win32 RegisterHotKey on a dedicated background thread
with its own message loop. That's event-driven and lighter than a global
keyboard hook, and never sees keystrokes that aren't the registered combo.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import logging
import os
import subprocess
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional

import psutil
import pystray
from PIL import Image, ImageDraw

from .overlay import RecordingOverlay
from .recorder import Recorder, RecorderConfig
from .teams_detect import is_teams_audio_active, is_teams_in_call

log = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
LOCK_PATH = SCRIPT_DIR / ".whisp-rec.lock"
LOG_PATH = SCRIPT_DIR / "whisp-rec.log"

# Win32 hotkey modifiers
MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

VK_MAP = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
VK_MAP.update({str(d): 0x30 + d for d in range(10)})
VK_MAP.update({f"F{i}": 0x6F + i for i in range(1, 13)})  # F1 = 0x70


class State(Enum):
    IDLE = "idle"
    RECORDING_MANUAL = "recording_manual"
    RECORDING_AUTO = "recording_auto"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def acquire_lock() -> bool:
    """Refuse to start a second instance. Returns True if we got the lock."""
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
        except ValueError:
            pid = -1
        if pid > 0 and psutil.pid_exists(pid):
            try:
                proc = psutil.Process(pid)
                if "python" in proc.name().lower():
                    log.warning("another whisp-rec instance is running (pid=%d)", pid)
                    return False
            except psutil.NoSuchProcess:
                pass
        # stale lock
        LOCK_PATH.unlink(missing_ok=True)
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        if LOCK_PATH.exists() and LOCK_PATH.read_text().strip() == str(os.getpid()):
            LOCK_PATH.unlink()
    except Exception:
        log.debug("failed to release lock", exc_info=True)


def free_space_gb(path: Path) -> float:
    try:
        usage = psutil.disk_usage(str(path))
        return usage.free / (1024 ** 3)
    except Exception:
        return float("inf")


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse 'ctrl+alt+r' into (modifiers, vk_code). Raises on invalid input."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    mods = MOD_NOREPEAT
    vk: Optional[int] = None
    for part in parts:
        if part == "ctrl":
            mods |= MOD_CTRL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in ("win", "super"):
            mods |= MOD_WIN
        else:
            key = part.upper()
            if key in VK_MAP:
                vk = VK_MAP[key]
            else:
                raise ValueError(f"unrecognised hotkey token '{part}' in '{spec}'")
    if vk is None:
        raise ValueError(f"hotkey '{spec}' has no key, only modifiers")
    return mods, vk


def make_icon(color: str) -> Image.Image:
    """Generate a simple 64x64 tray icon. color: gray | red | orange."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    palette = {
        "gray": (120, 120, 120, 255),
        "red": (220, 50, 50, 255),
        "orange": (240, 150, 30, 255),
    }
    fill = palette.get(color, palette["gray"])
    d.ellipse((8, 8, 56, 56), fill=fill)
    d.ellipse((26, 26, 38, 38), fill=(255, 255, 255, 255))
    return img


class WhispRecApp:
    def __init__(self, config: dict):
        self.config = config
        self.state: State = State.IDLE
        self.state_lock = threading.Lock()

        output_dir = Path(config["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        self.recorder = Recorder(RecorderConfig(
            output_dir=output_dir,
            samplerate=config["samplerate"],
            fmt=config["format"],
            subtype=config["subtype"],
            max_recording_minutes=config["max_recording_minutes"],
        ))

        # Teams autodetect state
        self.teams_active_streak = 0
        self.teams_inactive_streak = 0
        self.teams_seen_during_recording: bool = False
        # If the user manually stops a recording that overlapped with an ongoing
        # Teams call, we suppress auto-restart until the call actually ends.
        # (Fixed-time suppression isn't enough: the call can outlast it.)
        self.suppress_until_teams_ends: bool = False

        # Threads
        self._hotkey_thread: Optional[threading.Thread] = None
        self._teams_thread: Optional[threading.Thread] = None
        self._hotkey_thread_id: Optional[int] = None
        self._shutdown = threading.Event()

        # Tray
        self.icon: Optional[pystray.Icon] = None

        # On-screen recording overlay
        self.overlay: Optional[RecordingOverlay] = None
        if config.get("overlay_enabled", True):
            self.overlay = RecordingOverlay(
                elapsed_provider=lambda: self.recorder.elapsed_seconds,
                position=config.get("overlay_position", "top-right"),
            )
        # When True, keep the REC pill hidden even while recording. Toggled
        # from the tray menu so the overlay can be dropped right before a
        # full-screen share without stopping the recording. Session-only.
        self.overlay_suppressed: bool = False

        # Live brain/UI session (M4 auto-live). Best-effort: never breaks recording.
        self._session = None
        self._live_mode = str(config.get("live_brain", "off")).lower()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _set_state(self, new_state: State) -> None:
        with self.state_lock:
            self.state = new_state
        self._refresh_icon()
        if self.overlay is not None:
            if (new_state in (State.RECORDING_MANUAL, State.RECORDING_AUTO)
                    and not self.overlay_suppressed):
                self.overlay.show()
            else:
                self.overlay.hide()

    def toggle_manual(self) -> None:
        with self.state_lock:
            current = self.state

        if current == State.IDLE:
            # User explicitly starting = clear any leftover suppression.
            self.suppress_until_teams_ends = False
            self._start(State.RECORDING_MANUAL)
        else:
            # Set suppression BEFORE _stop() so the teams-poll thread can't race
            # us and auto-restart during the ~1-2 s the writer thread takes to
            # finalize the FLAC.
            # Suppress if: recording was auto-started (Teams must have been
            # active to trigger it), OR Teams was observed active at any point
            # during the recording.
            if current == State.RECORDING_AUTO or self.teams_seen_during_recording:
                self.suppress_until_teams_ends = True
                log.info("auto-detect suppressed until current Teams call ends")
            self._stop()

    def toggle_overlay_hidden(self) -> None:
        """Flip the 'hide overlay' preference and apply it immediately.

        Lets the user drop the REC pill before a full-screen share without
        stopping the recording, then bring it back afterwards. The recording
        itself is untouched - this only affects what's drawn on screen.
        """
        if self.overlay is None:
            return
        self.overlay_suppressed = not self.overlay_suppressed
        log.info("overlay %s via menu", "hidden" if self.overlay_suppressed else "shown")
        with self.state_lock:
            recording = self.state in (State.RECORDING_MANUAL, State.RECORDING_AUTO)
        if self.overlay_suppressed:
            self.overlay.hide()
        elif recording:
            self.overlay.show()

    def _start(self, target: State) -> None:
        free = free_space_gb(Path(self.config["output_dir"]))
        if free < float(self.config.get("min_free_gb_warning", 1)):
            log.warning("low disk space: %.2f GB free under %s", free, self.config["output_dir"])

        # Live brain/UI (M4): attach the audio tap BEFORE recording starts so the
        # brain sees audio from the first chunk. Entirely best-effort - any failure
        # here must never stop the recording.
        if self._live_mode in ("auto", "on"):
            try:
                from ..server.session import LiveSession
                self._session = LiveSession(self.config)
                self.recorder.set_tap(self._session.bus.push)
            except Exception:
                log.exception("live session setup failed; recording without live brain")
                self._session = None
                self.recorder.set_tap(None)

        try:
            path = self.recorder.start()
        except Exception:
            log.exception("recorder failed to start")
            self.recorder.set_tap(None)
            self._session = None
            return

        if self._session is not None:
            try:
                self._session.start(path)
            except Exception:
                log.exception("live session failed to start; recording continues")
                try:
                    self._session.stop()
                except Exception:
                    log.debug("session stop after failed start raised", exc_info=True)
                self._session = None

        self.teams_seen_during_recording = False
        self._set_state(target)

    def _stop(self) -> None:
        path = self.recorder.stop()
        self.recorder.set_tap(None)
        # Tear the live session down OFF the caller's thread: brain.stop() can
        # block for tens of seconds finishing an in-flight whisper utterance.
        # We must hide the REC overlay and free the tray immediately, not after.
        session = self._session
        self._session = None
        self.teams_seen_during_recording = False
        self._set_state(State.IDLE)  # hide overlay NOW, before slow teardown
        if session is not None:
            threading.Thread(
                target=self._teardown_session, args=(session,),
                name="lma-session-teardown", daemon=True,
            ).start()
        if path and self.config.get("auto_transcribe", False):
            self._kick_transcription(path)

    def _teardown_session(self, session) -> None:
        try:
            session.stop()
        except Exception:
            log.exception("live session stop failed")

    def _kick_transcription(self, audio_path: Path) -> None:
        py = self.config.get("transcribe_python")
        script = self.config.get("transcribe_script")
        if not py or not script or not Path(py).exists() or not Path(script).exists():
            log.warning("auto_transcribe on but python/script paths missing: py=%s script=%s", py, script)
            return
        cmd = [py, script, str(audio_path),
               "--lang", self.config.get("transcribe_lang", "auto"),
               "--model", self.config.get("transcribe_model", "large-v3-turbo")]
        context = self.config.get("transcribe_context") or ""
        if context:
            cmd.extend(["--context", context])
        log.info("dispatching transcription: %s", " ".join(cmd))
        try:
            subprocess.Popen(
                cmd,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            log.exception("could not start transcription subprocess")

    def _open_ui_window(self) -> None:
        """Open (or re-open) the live transcript window, pointed at the server."""
        port = int(self.config.get("server_port", 8731))
        pyw = SCRIPT_DIR.parent.parent / ".venv" / "Scripts" / "pythonw.exe"
        exe = str(pyw) if pyw.exists() else sys.executable
        try:
            subprocess.Popen(
                [exe, "-m", "lma.ui", "--port", str(port)],
                cwd=str(SCRIPT_DIR.parent.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log.exception("failed to open live transcript window")

    # ------------------------------------------------------------------
    # Hotkey thread
    # ------------------------------------------------------------------

    def _hotkey_loop(self) -> None:
        try:
            mods, vk = parse_hotkey(self.config["hotkey"])
        except ValueError as e:
            log.error("invalid hotkey config: %s", e)
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._hotkey_thread_id = kernel32.GetCurrentThreadId()
        hotkey_id = 1

        # Force MSG queue creation
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)

        if not user32.RegisterHotKey(None, hotkey_id, mods, vk):
            err = ctypes.get_last_error()
            log.error("RegisterHotKey failed for '%s' (error %s). Another app likely owns this combo.",
                      self.config["hotkey"], err)
            return

        log.info("hotkey registered: %s", self.config["hotkey"])

        try:
            while not self._shutdown.is_set():
                bret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if bret == 0 or bret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                    log.debug("hotkey fired")
                    try:
                        self.toggle_manual()
                    except Exception:
                        log.exception("toggle_manual failed")
        finally:
            user32.UnregisterHotKey(None, hotkey_id)
            log.info("hotkey unregistered")

    # ------------------------------------------------------------------
    # Teams autodetect thread
    # ------------------------------------------------------------------

    def _teams_loop(self) -> None:
        # COM init for this thread, in MTA mode (what pycaw/comtypes expect).
        # Done here, not on the main thread, so soundcard's WASAPI COM use
        # stays clean.
        import pythoncom
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)

        interval = float(self.config.get("teams_poll_interval_seconds", 5))
        start_thresh = int(self.config.get("teams_start_after_active_polls", 2))
        stop_thresh = int(self.config.get("teams_stop_after_inactive_polls", 6))
        proc_names = self.config.get("teams_process_names", ["ms-teams.exe", "Teams.exe"])
        stop_manual_too = bool(self.config.get("auto_stop_manual_if_teams_was_active", True))
        detect_method = str(self.config.get("teams_detect_method", "window")).lower()
        call_window_min = int(self.config.get("teams_call_window_min", 2))
        log.info("teams detect method: %s (call_window_min=%d)", detect_method, call_window_min)

        while not self._shutdown.is_set():
            try:
                if detect_method == "audio":
                    active = is_teams_audio_active(proc_names)
                else:
                    active = is_teams_in_call(proc_names, call_window_min)
            except Exception:
                log.exception("teams detect failed")
                active = False

            if active:
                self.teams_active_streak += 1
                self.teams_inactive_streak = 0
            else:
                self.teams_inactive_streak += 1
                self.teams_active_streak = 0
                # Teams call has fully ended; clear suppression so the next call
                # can be auto-recorded normally.
                if self.suppress_until_teams_ends and self.teams_inactive_streak >= stop_thresh:
                    self.suppress_until_teams_ends = False
                    log.info("Teams call ended; auto-detect suppression cleared")

            with self.state_lock:
                current = self.state

            # Mark Teams overlap for any ongoing recording, so we can later
            # auto-stop a manual recording that bridged a Teams call.
            if active and current in (State.RECORDING_MANUAL, State.RECORDING_AUTO):
                self.teams_seen_during_recording = True

            if current == State.IDLE and active and self.teams_active_streak >= start_thresh:
                if self.suppress_until_teams_ends:
                    log.debug("auto-detect suppressed (user stopped during current Teams call)")
                else:
                    log.info("teams call detected, auto-starting recording")
                    self._start(State.RECORDING_AUTO)
            elif current == State.RECORDING_AUTO and not active and self.teams_inactive_streak >= stop_thresh:
                log.info("teams call ended, auto-stopping recording (auto-started)")
                self._stop()
            elif (stop_manual_too and current == State.RECORDING_MANUAL
                  and self.teams_seen_during_recording
                  and not active and self.teams_inactive_streak >= stop_thresh):
                log.info("teams call ended, auto-stopping recording (manual, but Teams was active during it)")
                self._stop()

            self._shutdown.wait(interval)

        try:
            pythoncom.CoUninitialize()
        except Exception:
            log.debug("CoUninitialize failed", exc_info=True)

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def _refresh_icon(self) -> None:
        if self.icon is None:
            return
        with self.state_lock:
            s = self.state
        if s == State.IDLE:
            self.icon.icon = make_icon("gray")
            self.icon.title = "whisp-rec (idle)"
        elif s == State.RECORDING_MANUAL:
            self.icon.icon = make_icon("red")
            self.icon.title = f"whisp-rec (recording manual) {self.recorder.current_path}"
        else:
            self.icon.icon = make_icon("orange")
            self.icon.title = f"whisp-rec (recording auto/Teams) {self.recorder.current_path}"

    def _menu(self) -> pystray.Menu:
        def on_toggle(_icon, _item):
            self.toggle_manual()

        def on_open_folder(_icon, _item):
            os.startfile(self.config["output_dir"])  # type: ignore[attr-defined]

        def on_open_log(_icon, _item):
            os.startfile(str(LOG_PATH))  # type: ignore[attr-defined]

        def on_quit(_icon, _item):
            self.shutdown()

        def on_toggle_overlay(_icon, _item):
            self.toggle_overlay_hidden()

        def on_open_ui(_icon, _item):
            self._open_ui_window()

        def overlay_hidden(_item) -> bool:
            return self.overlay_suppressed

        def is_recording(_item) -> bool:
            with self.state_lock:
                return self.state != State.IDLE

        return pystray.Menu(
            pystray.MenuItem(
                lambda item: "Stop recording" if is_recording(item) else "Start recording",
                on_toggle,
                default=True,
            ),
            pystray.MenuItem(
                lambda item: f"Status: {self.state.value}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Hide overlay",
                on_toggle_overlay,
                checked=overlay_hidden,
                enabled=self.overlay is not None,
            ),
            pystray.MenuItem("Open live transcript", on_open_ui),
            pystray.MenuItem("Open recordings folder", on_open_folder),
            pystray.MenuItem("Open log file", on_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        if self.overlay is not None:
            self.overlay.start()

        self._hotkey_thread = threading.Thread(target=self._hotkey_loop, name="whisp-rec-hotkey", daemon=True)
        self._hotkey_thread.start()

        if self.config.get("teams_autodetect", True):
            self._teams_thread = threading.Thread(target=self._teams_loop, name="whisp-rec-teams", daemon=True)
            self._teams_thread.start()

        self.icon = pystray.Icon(
            "whisp-rec",
            icon=make_icon("gray"),
            title="whisp-rec (idle)",
            menu=self._menu(),
        )
        self.icon.run()  # blocks until shutdown

    def shutdown(self) -> None:
        log.info("shutdown requested")
        self._shutdown.set()
        if self.recorder.is_recording:
            self.recorder.stop()
        if self._session is not None:
            try:
                self._session.stop()
            except Exception:
                log.debug("session stop on shutdown raised", exc_info=True)
            self._session = None
        if self.overlay is not None:
            self.overlay.stop()
        # Post WM_QUIT to the hotkey thread's message loop.
        if self._hotkey_thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._hotkey_thread_id, WM_QUIT, 0, 0)
        if self.icon is not None:
            self.icon.stop()


def main() -> int:
    log_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[log_handler])

    log.info("whisp-rec starting (pid=%d)", os.getpid())

    if not acquire_lock():
        print("another whisp-rec instance is running. exiting.", file=sys.stderr)
        return 1

    try:
        config = load_config()
    except Exception:
        log.exception("could not load config.json")
        release_lock()
        return 2

    app = WhispRecApp(config)
    try:
        app.run()
    except KeyboardInterrupt:
        log.info("keyboard interrupt")
        app.shutdown()
    except Exception:
        log.exception("crashed in main loop")
        return 3
    finally:
        release_lock()
        log.info("whisp-rec exited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
