"""Headless end-to-end check of the live pipeline (no tray, no GUI).

Replays a recorded .flac through the same Brain used live, prints the resulting
speaker-attributed transcript, then runs a Q&A turn through the configured
backend (Foundry or Anthropic). Proves transcription + Q&A without a Teams call.

Usage:
  set LMA_FOUNDRY_API_KEY=...   (if qa_backend=foundry)
  python scripts/headless_live_test.py recordings/2026-06/<file>.flac
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf

from lma.brain.brain import Brain
from lma.brain.qa import ask_stream, build_client
from lma.brain.state import Transcript
from lma.brain.whisper_engine import make_transcribe_fn
from lma.capture.bus import AudioBus
from lma.capture.replay import feed_file_to_bus

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: headless_live_test.py <path-to.flac>")
        return 2
    src = Path(argv[0])
    if not src.is_absolute():
        src = REPO_ROOT / src
    info = sf.info(str(src))
    print(f"source: {src.name}  ({info.duration:.1f}s @ {info.samplerate} Hz)")

    transcript = Transcript()
    fn = make_transcribe_fn(None, "small")
    bus = AudioBus(source_samplerate=info.samplerate, capacity_seconds=info.duration + 60)
    brain = Brain(bus, transcript, fn, broadcast=lambda seg: None)
    brain.attach()

    feed_file_to_bus(src, bus)
    while True:
        before = brain.mic._buf.size + brain.system._buf.size      # noqa: SLF001
        brain.process_once()
        after = brain.mic._buf.size + brain.system._buf.size        # noqa: SLF001
        if after == before:
            break
    brain.mic.flush()
    brain.system.flush()

    print("\n===== TRANSCRIPT =====")
    print(transcript.text() or "(empty - no speech transcribed)")

    cfg = json.loads((REPO_ROOT / "lma" / "capture" / "config.json").read_text(encoding="utf-8"))
    print(f"\n===== Q&A (summary via qa_backend={cfg.get('qa_backend', 'anthropic')}) =====")
    try:
        client, model = build_client(cfg)
        print("".join(ask_stream(transcript, "summary", client=client, model=model)))
    except Exception as e:  # noqa: BLE001
        print(f"[Q&A error: {type(e).__name__}: {e}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
