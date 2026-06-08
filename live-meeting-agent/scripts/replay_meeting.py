"""Replay a recorded FLAC through the live-transcript pipeline -> transcript.jsonl.

Usage:
  .\\.venv\\Scripts\\python.exe scripts\\replay_meeting.py "C:\\Tools\\live-meeting-agent\\recordings\\2026-06\\xxxx.flac" [--lang de]
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
    feed_file_to_bus(args.audio, bus)   # push all frames into the bus
    # Drive synchronously to completion (no inter-utterance waits).
    while True:
        before = brain.mic._buf.size + brain.system._buf.size   # noqa: SLF001
        brain.process_once()
        after = brain.mic._buf.size + brain.system._buf.size     # noqa: SLF001
        if after == before:
            break  # nothing more could be cut into an utterance; only tails remain
    brain.mic.flush()                   # flush remaining speech tails
    brain.system.flush()
    print(f"done in {time.time() - t0:.0f}s -> {out_path}")
    print(f"segments: {len(transcript.segments())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
