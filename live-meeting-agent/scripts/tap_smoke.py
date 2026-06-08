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
mic_peak = float(np.abs(mic).max()) if len(mic) else 0.0
sys_peak = float(np.abs(system).max()) if len(system) else 0.0
print(f"mic    samples={len(mic):6d} peak={mic_peak:.4f}")
print(f"system samples={len(system):6d} peak={sys_peak:.4f}")

# ~1 s of startup/teardown latency is normal, so 6 s wall -> ~4.5-5 s captured.
plumbing_ok = len(mic) > 64000 and len(system) > 64000 and abs(len(mic) - len(system)) < 1600
print("PLUMBING OK (tap delivers both channels to the bus)" if plumbing_ok
      else "CHECK: low/uneven sample count")
print("audio detected on at least one channel" if max(mic_peak, sys_peak) > 1e-3
      else "no audio during run (peaks ~0) - expected if nothing was playing/spoken")
