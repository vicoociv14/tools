# Live Meeting Agent - M0 (Lift + Parity) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Commit note:** Vico's standing rule is "never commit unless explicitly asked." The commit steps below are the checkpoints; during execution, pause at each and commit only on his go-ahead.

**Goal:** Move the working `whisp-rec` recorder into the `live-meeting-agent` repo as an `lma` package, add a no-op-by-default fan-out audio tap + a 16 kHz live audio bus, and repoint the logon auto-start - with the recorder behaving byte-identically (hotkey, Teams auto-detect, overlay, FLAC archive) before any brain is added.

**Architecture:** The capture core (lifted from `whisp-rec`) keeps running exactly as today. `recorder.Recorder` gains an optional `tap` callable, default `None`, so existing behaviour is unchanged. A new `lma/capture/bus.py` (`AudioBus`) splits the stereo capture frame into mic/system, downsamples each to 16 kHz mono, and ring-buffers it for later milestones. M0 wires nothing into the always-on tray (the bus stays unattached) so idle/recording behaviour is untouched.

**Tech Stack:** Python 3.11+, soundcard, soundfile, numpy<2, pystray, Pillow, pycaw, comtypes, psutil, pywin32, scipy (new, for resampling), pytest, pytest-mock. Windows Task Scheduler for auto-start.

**Spec:** `docs/superpowers/specs/2026-06-07-sparring-partner-design.md`

---

## File Structure

```
live-meeting-agent/
├─ run.pyw                      # NEW entry point (launched by Task Scheduler)
├─ install.ps1                  # NEW (repo-root): venv + repoint Task Scheduler
├─ lma/
│  ├─ __init__.py               # NEW (empty package marker)
│  ├─ capture/
│  │  ├─ __init__.py            # NEW (empty package marker)
│  │  ├─ recorder.py            # LIFTED from C:\Tools\whisp-rec + optional `tap`
│  │  ├─ teams_detect.py        # LIFTED verbatim
│  │  ├─ overlay.py             # LIFTED verbatim
│  │  ├─ tray.py                # LIFTED; sibling imports -> relative
│  │  ├─ config.json            # LIFTED verbatim
│  │  └─ bus.py                 # NEW: AudioBus + RingBuffer (16 kHz)
├─ tests/
│  └─ test_bus.py               # NEW
├─ requirements.txt             # OVERWRITE: capture deps + scipy + pytest
├─ .gitignore                   # APPEND runtime artefacts
└─ docs/superpowers/...
```

Dependency direction: `bus.py` depends only on numpy + scipy. `recorder.py` is standalone (gains a `tap` hook). `tray.py` imports `recorder`, `teams_detect`, `overlay` (relative). `run.pyw` imports `lma.capture.tray:main`.

The shelved diagram code (`agent.py`, `audio.py`, `transcription.py`, `llm.py`, `drawio.py`, `model.py`, old `tests/`) is left untouched.

---

## Task 1: Repo prep - package skeleton, requirements, gitignore

**Files:**
- Create: `lma/__init__.py`, `lma/capture/__init__.py`
- Overwrite: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package marker files**

Create `lma/__init__.py` with one line:

```python
"""Live Meeting Agent - unified capture core + live brain."""
```

Create `lma/capture/__init__.py` with one line:

```python
"""Capture core: recorder, Teams auto-detect, hotkey/tray, overlay, audio bus."""
```

- [ ] **Step 2: Overwrite `requirements.txt` with the M0 dependency set**

```
# Capture core (from whisp-rec)
soundcard==0.4.4
SoundFile==0.13.1
numpy<2.0
pystray==0.19.5
Pillow==10.4.0
pycaw==20240210
comtypes==1.4.5
psutil==6.0.0
pywin32==306
# Audio bus
scipy>=1.13
# Tests
pytest>=8.0
pytest-mock>=3.12
```

- [ ] **Step 3: Append runtime artefacts to `.gitignore`**

Append these lines to the existing `.gitignore`:

```gitignore
# whisp-rec runtime artefacts (now under lma/capture/)
lma/capture/whisp-rec.log
lma/capture/.whisp-rec.lock
_smoke/
*.flac
```

- [ ] **Step 4: Verify the package imports**

Run: `python -c "import lma, lma.capture; print('ok')"`
Expected: `ok` (run from the repo root; no venv needed yet for this check).

- [ ] **Step 5: Commit**

```bash
git add lma/__init__.py lma/capture/__init__.py requirements.txt .gitignore && git commit -m "chore(lma): scaffold package skeleton, M0 requirements, gitignore"
```

---

## Task 2: Lift the capture modules into `lma/capture/`

These four files move **verbatim** from `C:\Tools\whisp-rec\`; only `tray.py`'s three sibling imports change to relative. Do not refactor logic - parity is the goal.

**Files:**
- Create: `lma/capture/recorder.py` (copy of `C:\Tools\whisp-rec\recorder.py`)
- Create: `lma/capture/teams_detect.py` (copy)
- Create: `lma/capture/overlay.py` (copy)
- Create: `lma/capture/tray.py` (copy + import fix)
- Create: `lma/capture/config.json` (copy)

- [ ] **Step 1: Copy the four modules + config verbatim**

```bash
copy "C:\Tools\whisp-rec\recorder.py" "lma\capture\recorder.py"
copy "C:\Tools\whisp-rec\teams_detect.py" "lma\capture\teams_detect.py"
copy "C:\Tools\whisp-rec\overlay.py" "lma\capture\overlay.py"
copy "C:\Tools\whisp-rec\tray.py" "lma\capture\tray.py"
copy "C:\Tools\whisp-rec\config.json" "lma\capture\config.json"
```

(In PowerShell `copy` is aliased to `Copy-Item`; these one-liners work as-is.)

- [ ] **Step 2: Fix the sibling imports in `lma/capture/tray.py`**

In `lma/capture/tray.py`, replace the three module-level imports:

```python
from overlay import RecordingOverlay
from recorder import Recorder, RecorderConfig
from teams_detect import is_teams_audio_active
```

with relative imports:

```python
from .overlay import RecordingOverlay
from .recorder import Recorder, RecorderConfig
from .teams_detect import is_teams_audio_active
```

Leave everything else in `tray.py` unchanged (the `if __name__ == "__main__"` block stays; it will be run via `python -m lma.capture.tray`, where relative imports resolve).

- [ ] **Step 3: Byte-compile all four modules to catch syntax/import errors**

Run: `python -m py_compile lma\capture\recorder.py lma\capture\teams_detect.py lma\capture\overlay.py lma\capture\tray.py`
Expected: no output, exit code 0.

- [ ] **Step 4: Verify the package imports cleanly (needs the venv from Task 6; if not yet created, defer this check to after Task 6)**

Run: `python -c "from lma.capture import recorder, teams_detect, overlay; print('ok')"`
Expected: `ok`. (`tray` pulls in pystray/pycaw; verify it after the venv exists in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add lma/capture/recorder.py lma/capture/teams_detect.py lma/capture/overlay.py lma/capture/tray.py lma/capture/config.json && git commit -m "feat(lma): lift whisp-rec capture modules into lma.capture (relative imports)"
```

---

## Task 3: Add the fan-out tap to the recorder (default off = parity)

A minimal, optional hook. With `tap=None` (the default) the writer loop is identical to today, so the always-on recorder is unaffected.

**Files:**
- Modify: `lma/capture/recorder.py`

- [ ] **Step 1: Add a `tap` parameter to `Recorder.__init__`**

In `lma/capture/recorder.py`, change the `Recorder.__init__` signature and store the tap. Replace:

```python
    def __init__(self, config: RecorderConfig):
        self.config = config
        self._thread: Optional[threading.Thread] = None
```

with:

```python
    def __init__(self, config: RecorderConfig, tap: "Optional[Callable[[np.ndarray], None]]" = None):
        self.config = config
        self._tap = tap
        self._thread: Optional[threading.Thread] = None
```

Add `Callable` to the typing import at the top. Replace:

```python
from typing import Optional
```

with:

```python
from typing import Callable, Optional
```

- [ ] **Step 2: Call the tap after each write, in both the main loop and the drain loop**

In `Recorder._run`, the main loop currently has:

```python
                    frame, n = _stereo_pack(mic_data, sys_data)
                    if n:
                        out.write(frame)
```

Replace it with:

```python
                    frame, n = _stereo_pack(mic_data, sys_data)
                    if n:
                        out.write(frame)
                        self._emit_tap(frame)
```

In the same method, the drain loop currently has:

```python
                    frame, n = _stereo_pack(mic_data, sys_data)
                    if n:
                        out.write(frame)
                        drained += n
```

Replace it with:

```python
                    frame, n = _stereo_pack(mic_data, sys_data)
                    if n:
                        out.write(frame)
                        self._emit_tap(frame)
                        drained += n
```

- [ ] **Step 3: Add the `_emit_tap` helper (never lets a tap error break recording)**

Add this method to the `Recorder` class (e.g. directly above `def _run`):

```python
    def _emit_tap(self, frame: np.ndarray) -> None:
        """Forward a (N, 2) float32 capture frame to the live tap, if attached.

        Failures in the tap must never interrupt the recording, so they are
        swallowed and logged.
        """
        if self._tap is None:
            return
        try:
            self._tap(frame)
        except Exception:
            log.exception("audio tap raised; continuing recording")
```

- [ ] **Step 4: Byte-compile and confirm default behaviour is unchanged**

Run: `python -m py_compile lma\capture\recorder.py`
Expected: no output, exit 0.

Run: `python -c "from lma.capture.recorder import Recorder, RecorderConfig; from pathlib import Path; r=Recorder(RecorderConfig(output_dir=Path('.'))); print(r._tap)"`
Expected: `None` (tap defaults off → parity).

- [ ] **Step 5: Commit**

```bash
git add lma/capture/recorder.py && git commit -m "feat(recorder): add optional fan-out tap (default None = unchanged behaviour)"
```

---

## Task 4: Implement the live audio bus (TDD)

`AudioBus` is the seam between capture and the future brain. It splits the stereo capture frame (col 0 = mic, col 1 = system), downsamples each channel to 16 kHz mono, and ring-buffers the most recent audio per channel.

**Files:**
- Create: `tests/test_bus.py`
- Create: `lma/capture/bus.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bus.py`:

```python
import numpy as np
import pytest

from lma.capture.bus import AudioBus, RingBuffer


def test_ringbuffer_read_last_returns_recent_samples():
    rb = RingBuffer(capacity_seconds=1, sample_rate=16000)
    rb.write(np.arange(8000, dtype=np.float32))
    out = rb.read_last(0.25)  # last 0.25 s = 4000 samples
    assert len(out) == 4000
    assert out[-1] == 7999.0


def test_ringbuffer_overwrites_oldest_when_full():
    rb = RingBuffer(capacity_seconds=1, sample_rate=16000)
    rb.write(np.ones(20000, dtype=np.float32))  # 1.25 s into a 1 s buffer
    out = rb.read_last(10.0)  # ask for more than capacity
    assert len(out) == 16000  # capped at capacity


def test_bus_target_samplerate_is_16k():
    bus = AudioBus(source_samplerate=48000, capacity_seconds=2)
    assert bus.target_samplerate == 16000


def test_bus_push_splits_channels_and_downsamples():
    bus = AudioBus(source_samplerate=48000, capacity_seconds=2)
    n = 48000  # 1 s at 48 kHz
    frame = np.empty((n, 2), dtype=np.float32)
    frame[:, 0] = 0.5   # mic channel
    frame[:, 1] = -0.5  # system channel
    bus.push(frame)
    mic = bus.read_last("mic", 1.0)
    sysd = bus.read_last("system", 1.0)
    assert abs(len(mic) - 16000) <= 4   # ~1 s at 16 kHz
    assert abs(len(sysd) - 16000) <= 4
    assert mic.mean() == pytest.approx(0.5, abs=0.05)
    assert sysd.mean() == pytest.approx(-0.5, abs=0.05)


def test_bus_passthrough_when_source_is_16k():
    bus = AudioBus(source_samplerate=16000, capacity_seconds=2)
    frame = np.zeros((1600, 2), dtype=np.float32)
    frame[:, 0] = 1.0
    bus.push(frame)
    mic = bus.read_last("mic", 0.1)
    assert len(mic) == 1600
    assert mic.mean() == pytest.approx(1.0, abs=1e-6)


def test_bus_read_unknown_channel_raises():
    bus = AudioBus(source_samplerate=48000, capacity_seconds=2)
    with pytest.raises(ValueError):
        bus.read_last("nope", 1.0)
```

- [ ] **Step 2: Run the tests, expect failure**

Run: `python -m pytest tests/test_bus.py -v`
Expected: `ModuleNotFoundError: No module named 'lma.capture.bus'`.

- [ ] **Step 3: Implement `lma/capture/bus.py`**

```python
"""Live audio bus - the seam between the capture core and the live brain.

The recorder calls `AudioBus.push(frame)` with each (N, 2) float32 chunk at the
capture sample rate (column 0 = mic, column 1 = system). The bus splits the two
channels, downsamples each to 16 kHz mono (what whisper and pyannote want), and
keeps the most recent `capacity_seconds` per channel in a ring buffer. With no
brain attached the recorder's tap is None and `push` is never called, so this
costs nothing during a plain recording.
"""
from __future__ import annotations

import threading
from math import gcd

import numpy as np
from scipy.signal import resample_poly

TARGET_SAMPLERATE = 16000


class RingBuffer:
    """Fixed-capacity mono float32 ring buffer, newest-wins."""

    def __init__(self, capacity_seconds: float, sample_rate: int = TARGET_SAMPLERATE):
        self.sample_rate = sample_rate
        self.capacity = int(capacity_seconds * sample_rate)
        self._buf = np.zeros(self.capacity, dtype=np.float32)
        self._write = 0
        self._filled = 0
        self._lock = threading.Lock()

    def write(self, samples: np.ndarray) -> None:
        samples = np.asarray(samples, dtype=np.float32).ravel()
        with self._lock:
            n = len(samples)
            if n >= self.capacity:
                self._buf[:] = samples[-self.capacity:]
                self._write = 0
                self._filled = self.capacity
                return
            end = self._write + n
            if end <= self.capacity:
                self._buf[self._write:end] = samples
            else:
                first = self.capacity - self._write
                self._buf[self._write:] = samples[:first]
                self._buf[: n - first] = samples[first:]
            self._write = (self._write + n) % self.capacity
            self._filled = min(self._filled + n, self.capacity)

    def read_last(self, seconds: float) -> np.ndarray:
        with self._lock:
            want = min(int(seconds * self.sample_rate), self._filled)
            if want == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._write - want) % self.capacity
            if start + want <= self.capacity:
                return self._buf[start:start + want].copy()
            tail = self.capacity - start
            return np.concatenate([self._buf[start:], self._buf[: want - tail]])


def _resample(x: np.ndarray, src: int, tgt: int) -> np.ndarray:
    if src == tgt:
        return np.asarray(x, dtype=np.float32)
    g = gcd(src, tgt)
    return resample_poly(x, tgt // g, src // g).astype(np.float32)


class AudioBus:
    """Splits stereo capture frames into 16 kHz mono mic/system ring buffers."""

    def __init__(
        self,
        source_samplerate: int,
        target_samplerate: int = TARGET_SAMPLERATE,
        capacity_seconds: float = 1800.0,
    ):
        self.source_samplerate = source_samplerate
        self.target_samplerate = target_samplerate
        self._channels = {
            "mic": RingBuffer(capacity_seconds, target_samplerate),
            "system": RingBuffer(capacity_seconds, target_samplerate),
        }

    def push(self, frame: np.ndarray) -> None:
        """frame: (N, 2) float32 at source_samplerate; col 0 = mic, col 1 = system."""
        if frame.ndim != 2 or frame.shape[1] < 2 or len(frame) == 0:
            return
        mic = _resample(frame[:, 0], self.source_samplerate, self.target_samplerate)
        system = _resample(frame[:, 1], self.source_samplerate, self.target_samplerate)
        self._channels["mic"].write(mic)
        self._channels["system"].write(system)

    def read_last(self, channel: str, seconds: float) -> np.ndarray:
        if channel not in self._channels:
            raise ValueError(f"unknown channel '{channel}', expected 'mic' or 'system'")
        return self._channels[channel].read_last(seconds)
```

- [ ] **Step 4: Run the tests, expect pass**

Run: `python -m pytest tests/test_bus.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_bus.py lma/capture/bus.py && git commit -m "feat(bus): add 16 kHz live audio bus with ring buffers and channel split (TDD)"
```

---

## Task 5: Entry point `run.pyw`

`run.pyw` is what Task Scheduler launches (silent, via `pythonw.exe`). It puts the repo root on `sys.path` and calls the lifted tray's `main()`.

**Files:**
- Create: `run.pyw`

- [ ] **Step 1: Create `run.pyw` at the repo root**

```python
"""Silent entry point for the Live Meeting Agent capture core.

Launched by Task Scheduler at logon via pythonw.exe (no console window).
Run for development with:  python -m lma.capture.tray
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lma.capture.tray import main  # noqa: E402  (after sys.path setup)

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Byte-compile**

Run: `python -m py_compile run.pyw`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add run.pyw && git commit -m "feat(lma): add run.pyw silent entry point"
```

---

## Task 6: Consolidated venv

Create one fresh repo venv for the unified app. The old `.venv` (from the shelved diagram project) is removed to avoid version conflicts (e.g. numpy<2 for soundcard).

**Files:** none (environment only).

- [ ] **Step 1: Remove the stale venv if present**

Run: `if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }`
Expected: no error.

- [ ] **Step 2: Create the venv and install M0 requirements**

Run: `python -m venv .venv; .\.venv\Scripts\python.exe -m pip install --upgrade pip; .\.venv\Scripts\python.exe -m pip install -r requirements.txt`
Expected: all packages install; final line reports success. (`pywin32` may print a post-install note - that is fine.)

- [ ] **Step 3: Verify every capture module imports under the venv (including `tray`)**

Run: `.\.venv\Scripts\python.exe -c "from lma.capture import recorder, teams_detect, overlay, tray, bus; print('all import ok')"`
Expected: `all import ok`.

- [ ] **Step 4: Run the bus tests under the venv**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bus.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit (records nothing new but marks the checkpoint; skip if no tracked changes)**

No tracked files changed (`.venv` is gitignored). Proceed to Task 7.

---

## Task 7: Recorder + tap manual smoke test

Audio capture cannot be unit-tested in CI, so verify the tap end-to-end manually: record a few seconds while audio plays and confirm the tap delivered frames into an `AudioBus`.

**Files:**
- Create: `scripts/tap_smoke.py`

- [ ] **Step 1: Create `scripts/tap_smoke.py`**

```python
"""Manual smoke test: record ~6 s with a tap into an AudioBus, report capture.

Play some audio (a YouTube video / music) AND speak into the mic while this
runs, then check the printed amplitudes are non-zero for both channels.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from lma.capture.bus import AudioBus  # noqa: E402
from lma.capture.recorder import Recorder, RecorderConfig  # noqa: E402

bus = AudioBus(source_samplerate=48000, capacity_seconds=30)
rec = Recorder(RecorderConfig(output_dir=Path("./_smoke")), tap=bus.push)

print("recording 6 s - play audio and talk into the mic...")
rec.start()
time.sleep(6)
rec.stop()

mic = bus.read_last("mic", 6.0)
system = bus.read_last("system", 6.0)
print(f"mic    samples={len(mic):6d} peak={np.abs(mic).max() if len(mic) else 0:.4f}")
print(f"system samples={len(system):6d} peak={np.abs(system).max() if len(system) else 0:.4f}")
print("PASS" if len(mic) > 80000 and len(system) > 80000 else "CHECK: low sample count")
```

- [ ] **Step 2: Run it (with audio playing + talking)**

Run: `.\.venv\Scripts\python.exe scripts\tap_smoke.py`
Expected: ~`mic samples= 96000 ...`, ~`system samples= 96000 ...` (6 s at 16 kHz), both peaks non-zero, `PASS`. (A `.flac` also appears under `./_smoke/` - confirms the archive write still happens alongside the tap.)

- [ ] **Step 3: Clean up the smoke output**

Run: `Remove-Item -Recurse -Force ._smoke -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force _smoke -ErrorAction SilentlyContinue`
Expected: no error.

- [ ] **Step 4: Commit**

```bash
git add scripts/tap_smoke.py && git commit -m "test(recorder): add manual tap+bus smoke script"
```

---

## Task 8: Recorder parity verification (manual)

Confirm the lifted capture core behaves identically to `C:\Tools\whisp-rec` **before** repointing auto-start. This is manual because it exercises the tray, hotkey, Teams detection, overlay and FLAC archive.

**Files:** none.

- [ ] **Step 1: Stop the currently-running whisp-rec instance (old location)**

Run: `Get-ScheduledTask -TaskName whisp-rec | Stop-ScheduledTask; Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force`
Expected: no error. (This frees the global `Ctrl+Alt+R` hotkey and the single-instance lock so the new copy can register them.)

- [ ] **Step 2: Launch the new copy from the repo venv (console visible for logs)**

Run: `.\.venv\Scripts\python.exe -m lma.capture.tray`
Expected: a tray icon appears; the log line `hotkey registered: ctrl+alt+r` is printed. Leave it running for the checks below.

- [ ] **Step 3: Manual parity checklist** (tick each)

  - [ ] Press `Ctrl+Alt+R` -> tray turns red, REC overlay appears top-right counting up.
  - [ ] Press `Ctrl+Alt+R` again -> recording stops, overlay disappears, a new `.flac` exists under `C:\recordings\<YYYY-MM>\`.
  - [ ] Open the new `.flac` (e.g. in a player) -> audio is present; left = mic, right = system.
  - [ ] Tray menu "Hide overlay" toggles the pill while recording, without stopping.
  - [ ] Start a real (or test) Teams call -> within ~10 s the tray turns orange (auto-record); end the call -> within ~30 s it stops automatically.
  - [ ] Tray "Quit" exits cleanly (no leftover `pythonw` process).

- [ ] **Step 4: Record the result**

If every box is ticked, parity is confirmed - proceed to Task 9. If anything differs from `whisp-rec`, STOP and debug before repointing auto-start (the old install is still intact as a fallback).

No commit (manual verification only).

---

## Task 9: Repoint auto-start + archive the old tool

Update `install.ps1` for the repo layout and repoint the `whisp-rec` Task Scheduler entry to the repo venv + `run.pyw`. Only after the new auto-start is verified, archive the old folder (archive, do not delete - per Vico's work principles).

**Files:**
- Create: `install.ps1` (repo root)

- [ ] **Step 1: Create `install.ps1` at the repo root**

```powershell
# install.ps1 - setup for the Live Meeting Agent capture core.
#
# Creates the repo venv, installs dependencies, and registers a Task Scheduler
# entry that launches the capture core silently at user logon via run.pyw.
#
# Usage (normal PowerShell - admin not required):
#   .\install.ps1                # venv + deps + register auto-start
#   .\install.ps1 -SkipAutoStart # venv + deps only
#   .\install.ps1 -Uninstall     # remove the Task Scheduler entry + venv

param(
    [switch]$SkipAutoStart,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ScriptDir ".venv"
$Pythonw = Join-Path $VenvDir "Scripts\pythonw.exe"
$Entry = Join-Path $ScriptDir "run.pyw"
$TaskName = "whisp-rec"

function Find-SystemPython {
    $candidates = @(
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python311\python.exe",
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe",
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python313\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "no Python 3.11+ found. Install from https://python.org first."
}

if ($Uninstall) {
    Write-Host "uninstalling Live Meeting Agent auto-start..."
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  removed scheduled task '$TaskName'"
    }
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir; Write-Host "  removed venv" }
    Write-Host "uninstall done. Recordings under C:\recordings are kept."
    exit 0
}

Write-Host "Live Meeting Agent install starting..."

if (-not (Test-Path $VenvDir)) {
    $sysPython = Find-SystemPython
    Write-Host "  creating venv with $sysPython"
    & $sysPython -m venv $VenvDir
} else {
    Write-Host "  venv already exists at $VenvDir"
}

$Python = Join-Path $VenvDir "Scripts\python.exe"
Write-Host "  upgrading pip (non-fatal)..."
& $Python -m pip install --upgrade pip --quiet 2>$null

Write-Host "  installing requirements..."
& $Python -m pip install -r (Join-Path $ScriptDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (-not (Test-Path $Pythonw)) { throw "pythonw.exe not found at $Pythonw" }
if (-not (Test-Path $Entry)) { throw "run.pyw not found at $Entry" }

if (-not $SkipAutoStart) {
    Write-Host "  registering scheduled task '$TaskName' to run at logon..."
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    $action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Entry`"" -WorkingDirectory $ScriptDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "  scheduled task registered -> $Pythonw $Entry"
}

Write-Host ""
Write-Host "install complete. Start now without rebooting:"
Write-Host "  & `"$Pythonw`" `"$Entry`""
Write-Host "config: $ScriptDir\lma\capture\config.json"
Write-Host "log:    $ScriptDir\lma\capture\whisp-rec.log"
```

- [ ] **Step 2: Ensure the old tray is fully stopped, then run the installer**

Run: `Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force; .\install.ps1`
Expected: `scheduled task registered -> ...\.venv\Scripts\pythonw.exe ...\run.pyw` and `install complete.`

- [ ] **Step 3: Trigger the task and verify it runs from the new location**

Run: `Start-ScheduledTask -TaskName whisp-rec; Start-Sleep 4; Get-Content lma\capture\whisp-rec.log -Tail 5`
Expected: recent log lines `whisp-rec starting (pid=...)` and `hotkey registered: ctrl+alt+r`. Confirm the tray icon is present and `Ctrl+Alt+R` starts/stops a recording.

- [ ] **Step 4: Archive the old tool (only after Step 3 passes)**

Run: `Move-Item "C:\Tools\whisp-rec" "C:\Tools\_archive\whisp-rec-2026-06-07" -Force`
Expected: the folder moves. (Create `C:\Tools\_archive` first if needed: `New-Item -ItemType Directory -Force C:\Tools\_archive`.) The Task Scheduler entry now points only at the repo, so nothing references the old path.

- [ ] **Step 5: Commit**

```bash
git add install.ps1 && git commit -m "feat(lma): repo-root installer that repoints whisp-rec auto-start to run.pyw"
```

---

## Task 10: Update the repo index

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace `CLAUDE.md` with an index covering the unified package**

```markdown
# live-meeting-agent

Unified Live Meeting Agent: a capture core (lifted from whisp-rec) that records every Teams meeting, plus a live brain (added across M1-M4) that transcribes + diarizes live and answers questions in a chat UI.

## Status
- M0 (lift + parity): capture core moved into `lma/`, fan-out tap + 16 kHz audio bus added, auto-start repointed. Recorder behaves identically to the old whisp-rec.
- M1-M4: live transcript -> Q&A -> diarization -> auto-live. See the plans folder.

## Key artefacts
- Spec: `docs/superpowers/specs/2026-06-07-sparring-partner-design.md`
- M0 plan: `docs/superpowers/plans/2026-06-07-live-meeting-agent-m0-lift-parity.md`
- (Shelved) old drawio diagram generator: `agent.py`, `llm.py`, `drawio.py`, `model.py`, old `audio.py`/`transcription.py`, and `docs/superpowers/specs/2026-04-26-live-meeting-agent-design.md`.

## Architecture (capture core)
mic + system loopback (soundcard, stereo FLAC 48 kHz, L=mic R=system) -> `C:\recordings\YYYY-MM\YYMMDD_HHMMSS.flac`. Teams auto start/stop via pycaw; global hotkey Ctrl+Alt+R; tray + REC overlay. `recorder.Recorder` has an optional `tap` that feeds `lma/capture/bus.py` (AudioBus) - a 16 kHz mic/system ring buffer the live brain consumes (M1+).

## Layout
- `run.pyw` - silent entry point (Task Scheduler launches it at logon).
- `install.ps1` - venv + Task Scheduler registration (task name `whisp-rec`).
- `lma/capture/` - recorder, teams_detect, overlay, tray, bus, config.json.

## Common commands
    .\.venv\Scripts\python.exe -m lma.capture.tray          # run capture core (dev, console visible)
    .\.venv\Scripts\python.exe -m pytest                    # run tests
    .\install.ps1                                            # (re)install + repoint auto-start
    Get-Content lma\capture\whisp-rec.log -Tail 20          # tail the log

## Gotchas
- Single global hotkey: only one instance can own Ctrl+Alt+R. Stop the scheduled task before running a dev copy.
- numpy is pinned < 2.0 (soundcard/pycaw). Keep it pinned when adding brain deps.
- Runtime config/log/lock live under `lma/capture/` (SCRIPT_DIR-relative, preserved from whisp-rec). A later milestone moves config to a unified loader.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md && git commit -m "docs(lma): update index for unified package (M0)"
```

---

## Self-Review (M0 vs spec)

- **Capture parity** (spec "Current assets", "Migration plan" 1-6): Tasks 2, 8, 9 lift verbatim, verify parity before repointing, archive old folder. Covered.
- **Fan-out tap + bus** (spec components 1-3, "Migration" 2): Tasks 3 (tap, default off) + 4 (AudioBus 16 kHz, channel split, TDD). Covered. No consumer wired into the always-on app (spec: "no consumer yet"). Covered.
- **Consolidated venv** (spec "Prerequisites"): Task 6 creates one repo venv; M0 installs the capture+bus+test subset, later milestones append brain deps. Covered (staged on purpose).
- **Repoint logon task** (spec "Migration" 4, failure mode "Logon task points at old path"): Task 9 rewrites `install.ps1` and re-registers the `whisp-rec` task to the repo entry. Covered.
- **Archive over delete** (Festo work principle): Task 9 Step 4 moves, not deletes. Covered.
- **Shelved diagram code untouched**: not modified by any task. Covered.

Type/name consistency check: `Recorder(config, tap=...)`, `recorder._emit_tap`, `AudioBus.push`, `AudioBus.read_last(channel, seconds)`, `RingBuffer.read_last(seconds)`, `bus.push` used as the tap in `tap_smoke.py` and (later) M1 - consistent across tasks. No placeholders; every code/command step is concrete.

---

## Subsequent milestones (separate plans, written when reached)

Each gets its own `docs/superpowers/plans/` file, detailed just before execution so it reflects what M0 established (real venv, real bus):

- **M1 - Live transcript:** wire `AudioBus` into the app when a recording starts; `brain/transcriber.py` (chunked faster-whisper: system continuous + mic VAD-gated); `brain/merger.py` -> `.transcript.jsonl`; FastAPI + Vite/React shell showing the live transcript over WebSocket. Speakers = You vs Remote. Adds `faster-whisper`, `fastapi`, `uvicorn`, `pywebview` to requirements.
- **M2 - Reactive Q&A:** `brain/qa.py` (Claude streaming) + chat UI + presets + drawio artifact. Adds `anthropic`.
- **M3 - Rolling diarization:** `brain/diarizer.py` (pyannote + persistent registry) on the system channel; legend rename/merge. Adds `pyannote.audio`, `torch`.
- **M4 - Auto-live + hardening:** wire brain to the meeting lifecycle (auto-live), CPU-contention tuning + graceful degradation, post-meeting clean re-diarization, persistence/restore.
