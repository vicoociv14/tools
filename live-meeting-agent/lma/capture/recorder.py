"""Audio recorder: WASAPI loopback (system audio) + microphone, streamed to FLAC.

Design notes:
- Shared-mode WASAPI: never locks devices, never blocks other apps (Teams keeps the mic, Spotify keeps the speaker).
- Mic is mono, system is downmixed to mono. We pack them into a stereo file:
  L = mic, R = system. This preserves the speaker hint without inflating storage.
- Streaming write to disk: a crash loses at most one chunk (~50 ms), never the whole recording.
- Native device sample rate (typically 48 kHz). No realtime resampling cost.
- FLAC via libsndfile (soundfile package). Compresses ~50% of WAV.

Concurrency model (this matters for Bluetooth HFP, where driver jitter can cause buffer underruns):
- Each device runs in its own reader thread, pulling 50 ms chunks into a queue continuously.
- A writer thread pulls one chunk from each queue, stereo-packs them, writes to FLAC.
- Per-device WASAPI buffer is sized at 500 ms so transient slowness on either side never drops samples.
- No serial blocking: mic and system are NEVER waiting on each other.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import soundcard as sc
import soundfile as sf

log = logging.getLogger(__name__)

CHUNK_SECONDS = 0.05       # 50 ms per device read; fast iteration, low write latency
WASAPI_BUFFER_SECONDS = 0.5  # 500 ms ring buffer per device; absorbs jitter
QUEUE_MAX = 400            # ~20 s of buffering at 50 ms; safety against slow writer


@dataclass
class RecorderConfig:
    output_dir: Path
    samplerate: int = 48000
    fmt: str = "FLAC"
    subtype: str = "PCM_16"
    max_recording_minutes: int = 240


class _DeviceReader(threading.Thread):
    """Pull fixed-size chunks from one WASAPI device into a queue, continuously."""

    def __init__(
        self,
        device,
        channels: int,
        samplerate: int,
        chunk_frames: int,
        blocksize: int,
        out_queue: queue.Queue,
        stop_event: threading.Event,
        label: str,
    ):
        super().__init__(name=f"whisp-rec-{label}", daemon=True)
        self.device = device
        self.channels = channels
        self.samplerate = samplerate
        self.chunk_frames = chunk_frames
        self.blocksize = blocksize
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.label = label
        self.error: Optional[BaseException] = None

    def run(self) -> None:
        try:
            with self.device.recorder(
                samplerate=self.samplerate,
                channels=self.channels,
                blocksize=self.blocksize,
            ) as rec:
                while not self.stop_event.is_set():
                    data = rec.record(numframes=self.chunk_frames)
                    try:
                        self.out_queue.put(data, timeout=1)
                    except queue.Full:
                        log.warning("%s queue full, dropping chunk", self.label)
        except Exception as exc:
            self.error = exc
            log.exception("%s reader crashed", self.label)
        finally:
            log.debug("%s reader exit", self.label)


def _stereo_pack(mic_data: np.ndarray, sys_data: np.ndarray) -> tuple[np.ndarray, int]:
    """Pack mic (mono) + system (mono or downmixed) into a stereo (N, 2) float32 buffer."""
    n = min(len(mic_data), len(sys_data))
    if n == 0:
        return np.zeros((0, 2), dtype=np.float32), 0

    mic_mono = mic_data[:n, 0]
    if sys_data.ndim == 2 and sys_data.shape[1] > 1:
        sys_mono = sys_data[:n].mean(axis=1)
    else:
        sys_mono = sys_data[:n, 0]

    frame = np.empty((n, 2), dtype=np.float32)
    frame[:, 0] = np.clip(mic_mono, -1.0, 1.0)
    frame[:, 1] = np.clip(sys_mono, -1.0, 1.0)
    return frame, n


class Recorder:
    """Thread-safe start/stop recorder. Only one recording at a time."""

    def __init__(self, config: RecorderConfig, tap: "Optional[Callable[[np.ndarray], None]]" = None):
        self.config = config
        self._tap = tap
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._current_path: Optional[Path] = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None

    def set_tap(self, tap) -> None:
        """Set or clear the live audio tap. Call only while not recording."""
        self._tap = tap

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_path(self) -> Optional[Path]:
        return self._current_path

    @property
    def elapsed_seconds(self) -> float:
        return (time.time() - self._started_at) if self._started_at else 0.0

    def start(self) -> Path:
        with self._lock:
            if self.is_recording:
                log.info("recorder already running at %s", self._current_path)
                return self._current_path  # type: ignore[return-value]

            now = datetime.now()
            month_folder = self.config.output_dir / now.strftime("%Y-%m")
            month_folder.mkdir(parents=True, exist_ok=True)
            ext = self.config.fmt.lower()
            filename = now.strftime("%y%m%d_%H%M%S") + f".{ext}"
            self._current_path = month_folder / filename

            self._stop_event.clear()
            self._started_at = time.time()
            self._thread = threading.Thread(
                target=self._run,
                name="whisp-rec-writer",
                daemon=True,
            )
            self._thread.start()
            log.info("recording started: %s", self._current_path)
            return self._current_path

    def stop(self) -> Optional[Path]:
        with self._lock:
            if not self.is_recording:
                log.debug("stop called but not recording")
                return None
            path = self._current_path
            self._stop_event.set()

        # Wait for writer thread (which also waits for readers) outside the lock.
        if self._thread is not None:
            self._thread.join(timeout=15)
        self._thread = None
        self._started_at = None
        log.info("recording stopped: %s", path)
        return path

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

    # internal --------------------------------------------------------------

    def _run(self) -> None:
        cfg = self.config
        path = self._current_path
        if path is None:
            return

        try:
            mic = sc.default_microphone()
            speaker = sc.default_speaker()
            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            log.info("recording: mic='%s', loopback-of='%s'", mic.name, speaker.name)
        except Exception:
            log.exception("failed to enumerate audio devices")
            return

        chunk_frames = int(cfg.samplerate * CHUNK_SECONDS)
        wasapi_buffer = int(cfg.samplerate * WASAPI_BUFFER_SECONDS)
        max_seconds = cfg.max_recording_minutes * 60

        mic_q: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
        sys_q: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)

        mic_reader = _DeviceReader(
            device=mic, channels=1, samplerate=cfg.samplerate,
            chunk_frames=chunk_frames, blocksize=wasapi_buffer,
            out_queue=mic_q, stop_event=self._stop_event, label="mic",
        )
        sys_reader = _DeviceReader(
            device=loopback, channels=2, samplerate=cfg.samplerate,
            chunk_frames=chunk_frames, blocksize=wasapi_buffer,
            out_queue=sys_q, stop_event=self._stop_event, label="sys",
        )

        try:
            with sf.SoundFile(
                str(path),
                mode="w",
                samplerate=cfg.samplerate,
                channels=2,
                format=cfg.fmt,
                subtype=cfg.subtype,
            ) as out:
                mic_reader.start()
                sys_reader.start()

                # Main loop: pull paired chunks from both queues, write stereo to FLAC.
                while not self._stop_event.is_set():
                    try:
                        mic_data = mic_q.get(timeout=0.5)
                        sys_data = sys_q.get(timeout=0.5)
                    except queue.Empty:
                        if mic_reader.error or sys_reader.error:
                            log.error("reader crashed; aborting. mic=%s sys=%s",
                                      mic_reader.error, sys_reader.error)
                            break
                        continue

                    frame, n = _stereo_pack(mic_data, sys_data)
                    if n:
                        out.write(frame)
                        self._emit_tap(frame)

                    if self.elapsed_seconds >= max_seconds:
                        log.warning("max recording length %s min reached, stopping",
                                    cfg.max_recording_minutes)
                        break

                # Stop requested: tell readers to exit and wait for them.
                self._stop_event.set()
                mic_reader.join(timeout=3)
                sys_reader.join(timeout=3)

                # Drain anything still buffered so the tail of the recording isn't lost.
                drained = 0
                while True:
                    try:
                        mic_data = mic_q.get_nowait()
                        sys_data = sys_q.get_nowait()
                    except queue.Empty:
                        break
                    frame, n = _stereo_pack(mic_data, sys_data)
                    if n:
                        out.write(frame)
                        self._emit_tap(frame)
                        drained += n
                if drained:
                    log.debug("drained %d frames after stop", drained)
        except Exception:
            log.exception("writer crashed")
        finally:
            self._stop_event.set()
            log.debug("writer thread exited; mic_qsize=%d sys_qsize=%d",
                      mic_q.qsize(), sys_q.qsize())


def list_devices() -> str:
    """Return a human-readable summary of detected mics/speakers (for diagnostics)."""
    lines = []
    try:
        lines.append(f"default mic:     {sc.default_microphone().name}")
        lines.append(f"default speaker: {sc.default_speaker().name}")
        lines.append("--- all mics ---")
        for m in sc.all_microphones(include_loopback=True):
            lines.append(f"  {m.name}  loopback={getattr(m, 'isloopback', False)}")
        lines.append("--- all speakers ---")
        for s in sc.all_speakers():
            lines.append(f"  {s.name}")
    except Exception as e:
        lines.append(f"error: {e}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Manual smoke test: record 5 seconds to ./_smoke.flac
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print(list_devices())
    rec = Recorder(RecorderConfig(output_dir=Path("./_smoke")))
    p = rec.start()
    print(f"recording 5s to {p}")
    time.sleep(5)
    rec.stop()
    print("done")
