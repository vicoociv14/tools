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
        bus.push(frame)
        if realtime:
            time.sleep(len(frame) / sr)
