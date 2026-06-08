"""Headless end-to-end test of the Azure Speech backend (no tray, no GUI).

Replays a recorded .flac through AzureBrain (the same path used live) and prints
the speaker-attributed transcript Azure streams back.

  set LMA_SPEECH_KEY=<resource key>   (or LMA_FOUNDRY_API_KEY - same resource)
  python scripts/azure_brain_test.py recordings/2026-06/<file>.flac
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf

from lma.brain.azure_stt import AzureBrain
from lma.brain.state import Transcript
from lma.capture.bus import AudioBus
from lma.capture.replay import feed_file_to_bus

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: azure_brain_test.py <path-to.flac>")
        return 2
    src = Path(argv[0])
    if not src.is_absolute():
        src = REPO_ROOT / src
    info = sf.info(str(src))
    print(f"streaming {src.name} ({info.duration:.1f}s) to Azure Speech...")

    transcript = Transcript()

    def show(seg):
        print(f"  + [{seg.start:5.1f}-{seg.end:5.1f}] {seg.speaker}: {seg.text}")

    key = os.environ.get("LMA_SPEECH_KEY") or os.environ.get("LMA_FOUNDRY_API_KEY")
    bus = AudioBus(source_samplerate=info.samplerate, capacity_seconds=info.duration + 60)
    brain = AzureBrain(
        bus, transcript, broadcast=show, key=key,
        region=os.environ.get("LMA_SPEECH_REGION", "swedencentral"),
        diarize_system=True,
    )
    brain.attach()
    brain.start()
    feed_file_to_bus(src, bus)
    time.sleep(min(info.duration, 90) + 15)  # let cloud recognition catch up
    brain.stop()

    print("\n===== FINAL TRANSCRIPT =====")
    print(transcript.text() or "(empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
