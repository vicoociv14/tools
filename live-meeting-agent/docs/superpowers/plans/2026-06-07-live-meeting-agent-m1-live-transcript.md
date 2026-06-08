# Live Meeting Agent - M1 (Live Transcript) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (or executing-plans) to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **Commit note:** Vico's rule is "never commit unless explicitly asked." Commit steps are checkpoints - pause and commit only on his go-ahead.
>
> **Daily-driver safety:** M1 Part A is **headless and developed via file-replay** - it does NOT change the running tray/recorder. The live brain is only wired into the recorder lifecycle in Part B, behind the `live_brain` config flag (default off). So building/testing M1 never destabilises the everyday recorder.

**Goal:** Turn a meeting's audio (live tap or a replayed FLAC) into a live, speaker-channel-attributed transcript (`You` = mic, `Remote` = system) written to a `.transcript.jsonl` sidecar - the foundation the Q&A (M2) and diarization (M3) build on.

**Architecture:** The M0 `AudioBus` gains a `subscribe()` fan-out. A `Brain` subscribes two `ChannelTranscriber`s (mic + system). Each accumulates its channel's 16 kHz audio, cuts complete utterances on trailing silence (pure `segmenter` logic), runs chunked `faster-whisper` on each utterance, and emits `Segment`s tagged with `You`/`Remote`. A `Merger` orders them into a thread-safe `Transcript` and appends to `.transcript.jsonl`. A file-replay path feeds a recorded FLAC through the same bus for deterministic, no-meeting-needed testing.

**Tech Stack:** Python 3.11, faster-whisper (live `small` model, CPU/int8/beam1/VAD), numpy<2, soundfile, scipy, pytest. (FastAPI/uvicorn/React/pywebview arrive in Part B.)

**Spec:** `docs/superpowers/specs/2026-06-07-sparring-partner-design.md`
**Builds on:** M0 (`lma/capture/bus.py` `AudioBus`/`RingBuffer`, `recorder.Recorder` tap).

---

## File Structure (Part A)

```
lma/
├─ capture/
│  ├─ bus.py            # MODIFY: add subscribe() fan-out
│  └─ replay.py         # NEW: feed a FLAC into an AudioBus (offline/testing)
├─ brain/
│  ├─ __init__.py       # NEW
│  ├─ state.py          # NEW: Segment + Transcript (jsonl persistence)
│  ├─ segmenter.py      # NEW: pure utterance-boundary detection
│  ├─ whisper_engine.py # NEW: faster-whisper wrapper (small, cpu)
│  ├─ transcriber.py    # NEW: ChannelTranscriber (feed/process, injectable transcribe_fn)
│  ├─ merger.py         # NEW: Merger (collect -> Transcript + broadcast hook)
│  └─ brain.py          # NEW: Brain orchestrator (bus -> 2 transcribers -> merger)
scripts/
└─ replay_meeting.py    # NEW: CLI - FLAC -> transcript.jsonl using real whisper
tests/
├─ test_state.py        # NEW
├─ test_segmenter.py    # NEW
├─ test_transcriber.py  # NEW (stub transcribe_fn, no model)
├─ test_brain.py        # NEW (stub transcribe_fn over a bus)
└─ test_bus.py          # MODIFY: add subscribe tests
```

Dependency direction: `segmenter` is pure numpy. `state` is stdlib. `transcriber` imports `segmenter`. `brain` imports `transcriber`, `merger`, `state`. `whisper_engine` is imported only by the real `transcribe_fn` wiring (`brain.py` default + `replay_meeting.py`), never by unit tests.

---

## Task 1: Add faster-whisper dependency

**Files:** Modify `requirements.txt`

- [ ] **Step 1: Append faster-whisper to `requirements.txt`**

Add under the existing list (after `scipy>=1.13`):

```
# Live transcription (M1)
faster-whisper==1.2.1
```

- [ ] **Step 2: Install into the repo venv**

Run: `.\.venv\Scripts\python.exe -m pip install faster-whisper==1.2.1`
Expected: installs faster-whisper + ctranslate2 + tokenizers + huggingface-hub; ends with `Successfully installed ...`. (numpy stays <2.)

- [ ] **Step 3: Verify import**

Run: `.\.venv\Scripts\python.exe -c "import faster_whisper, ctranslate2; print('fw ok', faster_whisper.__version__)"`
Expected: `fw ok 1.2.1`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt && git commit -m "chore(brain): add faster-whisper for live transcription"
```

---

## Task 2: Transcript state model

**Files:** Create `lma/brain/__init__.py`, `lma/brain/state.py`, `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_state.py`:

```python
import json
from lma.brain.state import Segment, Transcript


def test_segment_fields():
    s = Segment(start=1.0, end=2.5, text="hi", speaker="You", channel="mic")
    assert s.speaker == "You" and s.channel == "mic"


def test_transcript_orders_by_start():
    t = Transcript()
    t.add(Segment(2.0, 3.0, "second", "Remote", "system"))
    t.add(Segment(0.0, 1.0, "first", "You", "mic"))
    assert [s.text for s in t.segments()] == ["first", "second"]


def test_transcript_text_render():
    t = Transcript()
    t.add(Segment(0.0, 1.0, "hello", "You", "mic"))
    t.add(Segment(1.0, 2.0, "world", "Remote", "system"))
    assert t.text() == "[You] hello\n[Remote] world"


def test_transcript_writes_jsonl(tmp_path):
    p = tmp_path / "m" / "transcript.jsonl"
    t = Transcript(jsonl_path=p)
    t.add(Segment(0.0, 1.0, "hi", "You", "mic"))
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec == {"start": 0.0, "end": 1.0, "text": "hi", "speaker": "You", "channel": "mic"}
```

- [ ] **Step 2: Run, expect failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_state.py -v`
Expected: `ModuleNotFoundError: No module named 'lma.brain'`.

- [ ] **Step 3: Implement**

Write `lma/brain/__init__.py`:

```python
"""Live brain: transcription, diarization (M3), and Q&A (M2)."""
```

Write `lma/brain/state.py`:

```python
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Segment:
    start: float          # absolute seconds since meeting start
    end: float
    text: str
    speaker: str          # "You" | "Remote" | (M3) "Speaker 1"...
    channel: str          # "mic" | "system"


class Transcript:
    """Thread-safe, start-ordered transcript with optional jsonl persistence."""

    def __init__(self, jsonl_path: Optional[Path] = None):
        self._segments: list[Segment] = []
        self._lock = threading.Lock()
        self._jsonl_path = Path(jsonl_path) if jsonl_path else None
        if self._jsonl_path is not None:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, seg: Segment) -> None:
        with self._lock:
            self._segments.append(seg)
            self._segments.sort(key=lambda s: s.start)
            if self._jsonl_path is not None:
                with self._jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(seg), ensure_ascii=False) + "\n")

    def segments(self) -> list[Segment]:
        with self._lock:
            return list(self._segments)

    def text(self) -> str:
        with self._lock:
            return "\n".join(f"[{s.speaker}] {s.text}" for s in self._segments)
```

- [ ] **Step 4: Run, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_state.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add lma/brain/__init__.py lma/brain/state.py tests/test_state.py && git commit -m "feat(brain): Segment + thread-safe Transcript with jsonl persistence (TDD)"
```

---

## Task 3: Utterance segmenter (pure logic)

**Files:** Create `lma/brain/segmenter.py`, `tests/test_segmenter.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_segmenter.py`:

```python
import numpy as np
from lma.brain.segmenter import find_utterance_end

SR = 16000


def _speech(seconds, level=0.2):
    return np.full(int(seconds * SR), level, dtype=np.float32)


def _silence(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_all_silence_returns_none():
    assert find_utterance_end(_silence(2.0), SR) is None


def test_speech_then_silence_cuts_after_speech():
    audio = np.concatenate([_speech(1.0), _silence(0.8)])
    cut = find_utterance_end(audio, SR)
    assert cut is not None
    # cut should land near the end of the 1.0 s of speech
    assert abs(cut - SR) <= int(0.1 * SR)


def test_speech_without_trailing_silence_returns_none():
    audio = _speech(1.0)  # no pause yet, under max
    assert find_utterance_end(audio, SR) is None


def test_too_short_speech_ignored():
    audio = np.concatenate([_speech(0.2), _silence(0.8)])  # < min_speech
    assert find_utterance_end(audio, SR) is None


def test_force_cut_at_max_utterance():
    audio = _speech(21.0)  # exceeds max_utterance_s default 20
    cut = find_utterance_end(audio, SR)
    assert cut == len(audio)
```

- [ ] **Step 2: Run, expect failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_segmenter.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Write `lma/brain/segmenter.py`:

```python
from __future__ import annotations

import numpy as np


def find_utterance_end(
    audio: np.ndarray,
    sample_rate: int,
    *,
    silence_rms: float = 0.005,
    min_silence_s: float = 0.6,
    min_speech_s: float = 0.4,
    max_utterance_s: float = 20.0,
    frame_s: float = 0.05,
) -> int | None:
    """Return the sample index where a complete utterance ends, or None.

    Scan in `frame_s` frames. Once at least `min_speech_s` of speech (frame RMS
    >= `silence_rms`) has accumulated AND `min_silence_s` of trailing silence is
    seen, cut at the end of the last speech frame. If the buffer reaches
    `max_utterance_s` with enough speech but no pause, force a cut at the end
    (bounds latency).
    """
    n = len(audio)
    if n == 0:
        return None
    frame = max(1, int(sample_rate * frame_s))
    min_speech = int(min_speech_s * sample_rate)
    min_silence = int(min_silence_s * sample_rate)
    speech_samples = 0
    silence_run = 0
    last_speech_end = 0
    for start in range(0, n - frame + 1, frame):
        chunk = audio[start:start + frame]
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        if rms >= silence_rms:
            speech_samples += frame
            silence_run = 0
            last_speech_end = start + frame
        else:
            silence_run += frame
            if speech_samples >= min_speech and silence_run >= min_silence:
                return last_speech_end
    if n >= int(max_utterance_s * sample_rate) and speech_samples >= min_speech:
        return n
    return None
```

- [ ] **Step 4: Run, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_segmenter.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add lma/brain/segmenter.py tests/test_segmenter.py && git commit -m "feat(brain): pure silence-based utterance segmenter (TDD)"
```

---

## Task 4: AudioBus fan-out (subscribe)

**Files:** Modify `lma/capture/bus.py`, `tests/test_bus.py`

- [ ] **Step 1: Append failing tests to `tests/test_bus.py`**

```python
def test_bus_subscribe_receives_both_channels():
    bus = AudioBus(source_samplerate=16000, capacity_seconds=2)
    got = []
    bus.subscribe(lambda channel, samples: got.append((channel, len(samples))))
    frame = np.zeros((1600, 2), dtype=np.float32)
    bus.push(frame)
    channels = {c for c, _ in got}
    assert channels == {"mic", "system"}
    assert all(n == 1600 for _, n in got)


def test_bus_subscriber_error_does_not_break_push():
    bus = AudioBus(source_samplerate=16000, capacity_seconds=2)
    bus.subscribe(lambda channel, samples: (_ for _ in ()).throw(RuntimeError("boom")))
    frame = np.zeros((1600, 2), dtype=np.float32)
    bus.push(frame)  # must not raise
    assert len(bus.read_last("mic", 0.1)) == 1600  # ring still written
```

- [ ] **Step 2: Run, expect failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bus.py -k subscribe -v`
Expected: `AttributeError: 'AudioBus' object has no attribute 'subscribe'`.

- [ ] **Step 3: Implement - add subscribe + fan-out in `AudioBus`**

In `lma/capture/bus.py`, in `AudioBus.__init__`, add a subscribers list. Change:

```python
        self._channels = {
            "mic": RingBuffer(capacity_seconds, target_samplerate),
            "system": RingBuffer(capacity_seconds, target_samplerate),
        }
```

to:

```python
        self._channels = {
            "mic": RingBuffer(capacity_seconds, target_samplerate),
            "system": RingBuffer(capacity_seconds, target_samplerate),
        }
        self._subscribers = []
```

Add a method (after `__init__`):

```python
    def subscribe(self, fn) -> None:
        """Register fn(channel: str, samples: np.ndarray) called on every push.

        Lets streaming consumers (the live brain) receive audio as it arrives,
        in addition to the on-demand ring buffers. A subscriber that raises is
        logged and skipped - it must never break capture.
        """
        self._subscribers.append(fn)
```

In `push`, after writing the rings, fan out. Change:

```python
        self._channels["mic"].write(mic)
        self._channels["system"].write(system)
```

to:

```python
        self._channels["mic"].write(mic)
        self._channels["system"].write(system)
        for fn in self._subscribers:
            try:
                fn("mic", mic)
                fn("system", system)
            except Exception:
                log.exception("audio bus subscriber raised; skipping")
```

Add logging import at the top of `bus.py` (after `from math import gcd`):

```python
import logging
```

and below the imports:

```python
log = logging.getLogger(__name__)
```

- [ ] **Step 4: Run all bus tests, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bus.py -v`
Expected: 8 passed (6 original + 2 new).

- [ ] **Step 5: Commit**

```bash
git add lma/capture/bus.py tests/test_bus.py && git commit -m "feat(bus): add subscribe() fan-out for streaming consumers (TDD)"
```

---

## Task 5: ChannelTranscriber

**Files:** Create `lma/brain/transcriber.py`, `tests/test_transcriber.py`

The transcriber is unit-tested with a **stub** transcribe function - no model, fully deterministic.

- [ ] **Step 1: Write failing tests**

Write `tests/test_transcriber.py`:

```python
import numpy as np
from lma.brain.transcriber import ChannelTranscriber
from lma.brain.state import Segment

SR = 16000


def _stub_transcribe(audio, sr):
    # one segment spanning the clip, fixed text
    return [(0.0, len(audio) / sr, "hello world")]


def _speech(seconds, level=0.2):
    return np.full(int(seconds * SR), level, dtype=np.float32)


def _silence(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_emits_segment_after_complete_utterance():
    out = []
    ct = ChannelTranscriber("mic", speaker="You", emit=out.append, transcribe_fn=_stub_transcribe)
    ct.feed(_speech(1.0))
    ct.feed(_silence(0.8))
    ct.process()
    assert len(out) == 1
    seg = out[0]
    assert isinstance(seg, Segment)
    assert seg.speaker == "You" and seg.channel == "mic"
    assert seg.text == "hello world"
    assert abs(seg.start - 0.0) < 0.05


def test_no_emit_without_pause():
    out = []
    ct = ChannelTranscriber("system", speaker="Remote", emit=out.append, transcribe_fn=_stub_transcribe)
    ct.feed(_speech(1.0))
    ct.process()
    assert out == []


def test_second_utterance_gets_absolute_offset():
    out = []
    ct = ChannelTranscriber("mic", speaker="You", emit=out.append, transcribe_fn=_stub_transcribe)
    ct.feed(_speech(1.0)); ct.feed(_silence(0.8)); ct.process()   # first utterance ~[0,1]
    ct.feed(_speech(1.0)); ct.feed(_silence(0.8)); ct.process()   # second utterance later
    assert len(out) == 2
    assert out[1].start > out[0].end - 0.01  # second starts after the first consumed audio
```

- [ ] **Step 2: Run, expect failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_transcriber.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Write `lma/brain/transcriber.py`:

```python
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

from .segmenter import find_utterance_end
from .state import Segment

log = logging.getLogger(__name__)

# (audio16k_mono, sample_rate) -> list of (start_s, end_s, text)
TranscribeFn = Callable[[np.ndarray, int], list]
EmitFn = Callable[[Segment], None]


class ChannelTranscriber:
    """Accumulates one channel's 16 kHz audio, cuts utterances on silence, and
    transcribes each completed utterance into absolute-time Segments."""

    def __init__(
        self,
        channel: str,
        speaker: str,
        emit: EmitFn,
        transcribe_fn: TranscribeFn,
        *,
        sample_rate: int = 16000,
        poll_s: float = 1.0,
    ):
        self.channel = channel
        self.speaker = speaker
        self.emit = emit
        self.transcribe_fn = transcribe_fn
        self.sample_rate = sample_rate
        self.poll_s = poll_s
        self._buf = np.zeros(0, dtype=np.float32)
        self._consumed_s = 0.0          # absolute time at buf[0]
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def feed(self, samples: np.ndarray) -> None:
        with self._lock:
            self._buf = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32)])

    def process(self) -> None:
        """Cut + transcribe at most one completed utterance from the buffer."""
        with self._lock:
            buf = self._buf
            base = self._consumed_s
        cut = find_utterance_end(buf, self.sample_rate)
        if cut is None:
            return
        utterance = buf[:cut]
        try:
            results = self.transcribe_fn(utterance, self.sample_rate)
        except Exception:
            log.exception("transcribe failed on %s channel", self.channel)
            results = []
        for (s, e, text) in results:
            self.emit(Segment(
                start=base + s, end=base + e, text=text,
                speaker=self.speaker, channel=self.channel,
            ))
        with self._lock:
            self._buf = self._buf[cut:]
            self._consumed_s += cut / self.sample_rate

    def flush(self) -> None:
        """Force-transcribe whatever speech remains (call on stop)."""
        with self._lock:
            buf = self._buf
            base = self._consumed_s
        if len(buf) == 0:
            return
        try:
            results = self.transcribe_fn(buf, self.sample_rate)
        except Exception:
            log.exception("flush transcribe failed on %s channel", self.channel)
            results = []
        for (s, e, text) in results:
            self.emit(Segment(
                start=base + s, end=base + e, text=text,
                speaker=self.speaker, channel=self.channel,
            ))
        with self._lock:
            self._consumed_s += len(self._buf) / self.sample_rate
            self._buf = np.zeros(0, dtype=np.float32)

    def run(self) -> None:
        while not self._stop.is_set():
            self.process()
            self._stop.wait(self.poll_s)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name=f"transcriber-{self.channel}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.flush()
```

- [ ] **Step 4: Run, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_transcriber.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lma/brain/transcriber.py tests/test_transcriber.py && git commit -m "feat(brain): ChannelTranscriber - utterance cut + chunked transcribe to Segments (TDD)"
```

---

## Task 6: Merger + Brain orchestrator

**Files:** Create `lma/brain/merger.py`, `lma/brain/brain.py`, `tests/test_brain.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_brain.py`:

```python
import numpy as np
from lma.capture.bus import AudioBus
from lma.brain.brain import Brain
from lma.brain.state import Transcript

SR_SRC = 16000


def _stub_transcribe(audio, sr):
    return [(0.0, len(audio) / sr, "utterance")]


def _stereo(mic_level, sys_level, seconds):
    n = int(seconds * SR_SRC)
    f = np.zeros((n, 2), dtype=np.float32)
    f[:, 0] = mic_level
    f[:, 1] = sys_level
    return f


def test_brain_routes_channels_to_you_and_remote(tmp_path):
    bus = AudioBus(source_samplerate=SR_SRC, capacity_seconds=30)
    transcript = Transcript(jsonl_path=tmp_path / "transcript.jsonl")
    brain = Brain(bus, transcript, transcribe_fn=_stub_transcribe)
    brain.attach()

    # mic talks (system silent): one utterance + pause
    bus.push(_stereo(0.2, 0.0, 1.0))
    bus.push(_stereo(0.0, 0.0, 0.8))
    brain.process_once()
    # system talks (mic silent): one utterance + pause
    bus.push(_stereo(0.0, 0.2, 1.0))
    bus.push(_stereo(0.0, 0.0, 0.8))
    brain.process_once()

    speakers = {s.speaker for s in transcript.segments()}
    assert speakers == {"You", "Remote"}
    assert len(transcript.segments()) == 2


def test_brain_broadcasts_segments():
    bus = AudioBus(source_samplerate=SR_SRC, capacity_seconds=30)
    transcript = Transcript()
    seen = []
    brain = Brain(bus, transcript, transcribe_fn=_stub_transcribe, broadcast=seen.append)
    brain.attach()
    bus.push(_stereo(0.2, 0.0, 1.0)); bus.push(_stereo(0.0, 0.0, 0.8))
    brain.process_once()
    assert len(seen) == 1 and seen[0].speaker == "You"
```

- [ ] **Step 2: Run, expect failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_brain.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement merger**

Write `lma/brain/merger.py`:

```python
from __future__ import annotations

from typing import Callable, Optional

from .state import Segment, Transcript


class Merger:
    """Collects Segments from the transcribers into one Transcript and (optionally)
    broadcasts each to a sink (the WebSocket layer in Part B)."""

    def __init__(self, transcript: Transcript, broadcast: Optional[Callable[[Segment], None]] = None):
        self.transcript = transcript
        self.broadcast = broadcast

    def on_segment(self, seg: Segment) -> None:
        self.transcript.add(seg)
        if self.broadcast is not None:
            self.broadcast(seg)
```

- [ ] **Step 4: Implement brain**

Write `lma/brain/brain.py`:

```python
from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np

from ..capture.bus import AudioBus
from .merger import Merger
from .state import Segment, Transcript
from .transcriber import ChannelTranscriber, TranscribeFn

log = logging.getLogger(__name__)


class Brain:
    """Wires an AudioBus to two ChannelTranscribers (mic='You', system='Remote')
    feeding a Merger/Transcript. `attach()` subscribes to the bus; `start()` runs
    the transcriber threads; `process_once()` drives one pass synchronously (tests)."""

    def __init__(
        self,
        bus: AudioBus,
        transcript: Transcript,
        transcribe_fn: TranscribeFn,
        *,
        broadcast: Optional[Callable[[Segment], None]] = None,
    ):
        self.bus = bus
        self.merger = Merger(transcript, broadcast)
        self.mic = ChannelTranscriber("mic", "You", self.merger.on_segment, transcribe_fn)
        self.system = ChannelTranscriber("system", "Remote", self.merger.on_segment, transcribe_fn)
        self._by_channel = {"mic": self.mic, "system": self.system}

    def attach(self) -> None:
        self.bus.subscribe(self._dispatch)

    def _dispatch(self, channel: str, samples: np.ndarray) -> None:
        t = self._by_channel.get(channel)
        if t is not None:
            t.feed(samples)

    def process_once(self) -> None:
        self.mic.process()
        self.system.process()

    def start(self) -> None:
        self.mic.start()
        self.system.start()

    def stop(self) -> None:
        self.mic.stop()
        self.system.stop()
```

- [ ] **Step 5: Run, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_brain.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run the whole suite (no regressions)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bus.py tests/test_state.py tests/test_segmenter.py tests/test_transcriber.py tests/test_brain.py -v`
Expected: all pass (16 + new).

- [ ] **Step 7: Commit**

```bash
git add lma/brain/merger.py lma/brain/brain.py tests/test_brain.py && git commit -m "feat(brain): Merger + Brain orchestrator wiring bus to You/Remote transcribers (TDD)"
```

---

## Task 7: faster-whisper engine wrapper

**Files:** Create `lma/brain/whisper_engine.py`, `tests/test_whisper_engine.py`

- [ ] **Step 1: Implement the engine**

Write `lma/brain/whisper_engine.py`:

```python
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_model = None
_model_size: Optional[str] = None


def _get_model(model_size: str, device: str = "cpu", compute_type: str = "int8"):
    global _model, _model_size
    if _model is None or _model_size != model_size:
        from faster_whisper import WhisperModel  # lazy: keep import cost off unit tests
        log.info("loading faster-whisper model '%s' (%s/%s)", model_size, device, compute_type)
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_size = model_size
    return _model


def transcribe_array(
    audio: np.ndarray,
    sample_rate: int,
    *,
    language: Optional[str] = None,
    model_size: str = "small",
) -> list:
    """Transcribe a 16 kHz mono float32 clip -> [(start_s, end_s, text), ...]."""
    if sample_rate != 16000:
        raise ValueError(f"expected 16 kHz audio, got {sample_rate}")
    model = _get_model(model_size)
    segments, _info = model.transcribe(audio, language=language, beam_size=1, vad_filter=True)
    out = []
    for s in segments:
        text = s.text.strip()
        if text:
            out.append((float(s.start), float(s.end), text))
    return out


def make_transcribe_fn(language: Optional[str] = None, model_size: str = "small"):
    """Return a TranscribeFn bound to a language/model, for ChannelTranscriber/Brain."""
    def _fn(audio, sr):
        return transcribe_array(audio, sr, language=language, model_size=model_size)
    return _fn
```

- [ ] **Step 2: Write a gated integration test**

Write `tests/test_whisper_engine.py`:

```python
import os
import numpy as np
import pytest

# Real-model test: opt in with RUN_WHISPER=1 (downloads the 'small' model on first run).
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_WHISPER") != "1",
    reason="set RUN_WHISPER=1 to run the real faster-whisper test",
)


def test_transcribe_silence_returns_list():
    from lma.brain.whisper_engine import transcribe_array
    audio = np.zeros(16000, dtype=np.float32)  # 1 s silence
    result = transcribe_array(audio, 16000)
    assert isinstance(result, list)  # silence -> usually empty, must not error


def test_rejects_non_16k():
    from lma.brain.whisper_engine import transcribe_array
    with pytest.raises(ValueError):
        transcribe_array(np.zeros(8000, dtype=np.float32), 8000)
```

- [ ] **Step 3: Run (gated test is skipped by default)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_whisper_engine.py -v`
Expected: 2 skipped (no `RUN_WHISPER`).

Optional real check: `$env:RUN_WHISPER=1; .\.venv\Scripts\python.exe -m pytest tests/test_whisper_engine.py -v` -> downloads `small`, 2 passed. Unset after: `Remove-Item Env:RUN_WHISPER`.

- [ ] **Step 4: Commit**

```bash
git add lma/brain/whisper_engine.py tests/test_whisper_engine.py && git commit -m "feat(brain): faster-whisper engine wrapper (small/cpu/int8/beam1/vad) + gated test"
```

---

## Task 8: File replay + end-to-end offline run

**Files:** Create `lma/capture/replay.py`, `scripts/replay_meeting.py`

This is the key M1 deliverable: turn an existing `C:\recordings\...flac` into a `.transcript.jsonl` using the real pipeline, with no live meeting.

- [ ] **Step 1: Implement the replay feeder**

Write `lma/capture/replay.py`:

```python
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import soundfile as sf

from .bus import AudioBus


def feed_file_to_bus(
    path: Path,
    bus: AudioBus,
    *,
    chunk_seconds: float = 0.05,
    realtime: bool = False,
) -> None:
    """Read a stereo FLAC/WAV (L=mic, R=system) and push it through `bus` as
    capture frames. `realtime=False` pushes as fast as possible (tests/offline);
    `realtime=True` paces to wall-clock (demo)."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.column_stack([data[:, 0], data[:, 0]])
    chunk = max(1, int(sr * chunk_seconds))
    for start in range(0, len(data), chunk):
        frame = data[start:start + chunk]
        # bus expects (N, 2) at its source samplerate; set bus.source_samplerate=sr
        bus.push(frame)
        if realtime:
            time.sleep(len(frame) / sr)
```

- [ ] **Step 2: Implement the CLI**

Write `scripts/replay_meeting.py`:

```python
"""Replay a recorded FLAC through the live-transcript pipeline -> transcript.jsonl.

Usage:
  .\\.venv\\Scripts\\python.exe scripts\\replay_meeting.py "C:\\recordings\\2026-06\\xxxx.flac" [--lang de]
Writes <audio>.transcript.jsonl next to the input.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf  # noqa: E402

from lma.capture.bus import AudioBus  # noqa: E402
from lma.capture.replay import feed_file_to_bus  # noqa: E402
from lma.brain.brain import Brain  # noqa: E402
from lma.brain.state import Transcript  # noqa: E402
from lma.brain.whisper_engine import make_transcribe_fn  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--model", default="small")
    args = ap.parse_args(argv)

    info = sf.info(str(args.audio))
    out_path = args.audio.with_suffix(".transcript.jsonl")
    transcript = Transcript(jsonl_path=out_path)
    bus = AudioBus(source_samplerate=info.samplerate, capacity_seconds=info.duration + 60)
    brain = Brain(bus, transcript, transcribe_fn=make_transcribe_fn(args.lang, args.model))
    brain.attach()

    print(f"replaying {args.audio.name} ({info.duration:.0f}s) ...")
    t0 = time.time()
    feed_file_to_bus(args.audio, bus)   # push all frames
    brain.start()                       # transcribe accumulated audio
    # drive to completion: process until both buffers drained
    while brain.mic._buf.size or brain.system._buf.size:  # noqa: SLF001
        time.sleep(0.5)
    brain.stop()                        # flush tails
    print(f"done in {time.time() - t0:.0f}s -> {out_path}")
    print(f"segments: {len(transcript.segments())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Byte-compile**

Run: `.\.venv\Scripts\python.exe -m py_compile lma\capture\replay.py scripts\replay_meeting.py`
Expected: exit 0.

- [ ] **Step 4: Real end-to-end run on an existing recording**

Pick a recent recording with speech (e.g. one where you talked). Run:

`.\.venv\Scripts\python.exe scripts\replay_meeting.py "C:\recordings\2026-06\<file>.flac" --lang de`

Expected: prints `replaying ...`, then (after the `small` model loads/downloads on first use) `done ... -> <file>.transcript.jsonl` and a non-zero segment count. Open the `.transcript.jsonl` - each line is `{"start":..,"end":..,"text":"..","speaker":"You|Remote","channel":"mic|system"}`. Your speech should appear as `You`, the remote audio as `Remote`.

- [ ] **Step 5: Commit**

```bash
git add lma/capture/replay.py scripts/replay_meeting.py && git commit -m "feat(brain): file-replay path + replay_meeting CLI (FLAC -> transcript.jsonl)"
```

**End of M1 Part A.** You now have a working live-transcript pipeline, validated offline. Tag: `git tag M1a`.

---

## Part B - Live UI + lifecycle wiring (separate plan, written next)

Detailed just before building, on top of Part A. Scope:

- **`server/server.py`** - FastAPI: serve the SPA, `WS /ws/transcript` (broadcast each `Segment` + status), `GET /export`. The `Brain` is constructed with `broadcast=<ws push>`. Tested with FastAPI `TestClient` websockets.
- **`server/frontend/`** - Vite + React SPA: live colour-coded transcript (You vs Remote), auto-scroll, status bar; built to static, served by FastAPI; dev via Vite proxy. Deps: `fastapi`, `uvicorn[standard]`, `pywebview`.
- **`server/shell.py`** - pywebview window opened from the tray ("Open live transcript").
- **Lifecycle wiring (gated)** - in `tray.py`, behind `live_brain` config (default `off`): on recording start, create an `AudioBus`, set it as the recorder tap, `attach()`+`start()` the Brain pointed at `<recording>.transcript.jsonl`; on stop, `brain.stop()`. Keeps the daily-driver recorder unchanged until the flag is flipped. (Auto-live polish + CPU-contention tuning land in M4.)

Deferred to later milestones: pyannote diarization replacing You/Remote with Speaker 1/2/3 (M3), Claude Q&A over the transcript (M2), post-meeting clean re-diarization (M4).

---

## Self-Review (M1 Part A vs spec)

- **Live transcript pipeline** (spec components 1-7, milestone M1): bus fan-out (T4) -> ChannelTranscriber (T5) -> Brain/Merger (T6) -> Transcript jsonl (T2), utterance cutting (T3), faster-whisper (T7). Covered.
- **mic='You' / system='Remote'** (spec audio model; diarization deferred to M3): Brain hard-maps channels. Covered.
- **Offline testability via file-replay** (spec testing strategy "file-replay source is the key enabler"): T8. Covered.
- **Daily-driver safety**: no change to recorder/tray in Part A; live wiring is Part B behind `live_brain` flag. Covered.
- **Low-CPU live model = small** (Vico's choice): whisper_engine default `small`, beam=1, vad. Covered.

Type/name consistency: `Segment(start,end,text,speaker,channel)`, `Transcript.add/segments/text`, `AudioBus.subscribe(fn(channel,samples))`, `ChannelTranscriber(channel,speaker,emit,transcribe_fn).feed/process/flush/start/stop`, `Brain(bus,transcript,transcribe_fn,broadcast).attach/process_once/start/stop`, `make_transcribe_fn`, `feed_file_to_bus` - consistent across tasks. No placeholders; every code/command step is concrete. The `_buf` access in `replay_meeting.py` is the one internal reference (acknowledged with noqa) - acceptable for the CLI driver.
