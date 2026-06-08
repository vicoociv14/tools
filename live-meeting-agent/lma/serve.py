"""Launch the live-transcript UI.

  # replay a recording into the UI (no meeting needed):
  python -m lma.serve --source "C:\\Tools\\live-meeting-agent\\recordings\\<file>.flac"

  # live: capture mic+system now and show the transcript:
  python -m lma.serve --source live

Writes <name>.transcript.jsonl next to the source (replay) or under recordings/ (live).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lma.brain.brain import Brain                        # noqa: E402
from lma.brain.state import Transcript                   # noqa: E402
from lma.brain.whisper_engine import make_transcribe_fn  # noqa: E402
from lma.capture.bus import AudioBus                     # noqa: E402
from lma.server.hub import TranscriptHub                 # noqa: E402
from lma.server.server import create_app                 # noqa: E402
from lma.server.shell import run_window                  # noqa: E402

FRONTEND_DIST = Path(__file__).resolve().parent / "server" / "frontend" / "dist"


def _drive_replay(brain: Brain) -> None:
    while True:
        before = brain.mic._buf.size + brain.system._buf.size   # noqa: SLF001
        brain.process_once()
        after = brain.mic._buf.size + brain.system._buf.size     # noqa: SLF001
        if after == before:
            break
    brain.mic.flush()
    brain.system.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="'live' or a path to a .flac/.wav")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--model", default="small")
    ap.add_argument("--port", type=int, default=8731)
    args = ap.parse_args(argv)

    cfg_path = Path(__file__).resolve().parent / "capture" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}

    hub = TranscriptHub()
    transcribe_fn = make_transcribe_fn(args.lang, args.model)

    if args.source == "live":
        from lma.capture.recorder import Recorder, RecorderConfig
        rec_root = Path(__file__).resolve().parent.parent / "recordings"
        out_dir = rec_root / datetime.now().strftime("%Y-%m")
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl = out_dir / (datetime.now().strftime("%y%m%d_%H%M%S") + ".transcript.jsonl")
        transcript = Transcript(jsonl_path=jsonl)
        bus = AudioBus(source_samplerate=48000, capacity_seconds=3600)
        brain = Brain(bus, transcript, transcribe_fn, broadcast=hub.publish)
        brain.attach()
        rec = Recorder(RecorderConfig(output_dir=rec_root), tap=bus.push)
        rec.start()
        brain.start()
        app = create_app(transcript, hub, static_dir=FRONTEND_DIST, config=cfg)
        print(f"live UI on http://127.0.0.1:{args.port}  ->  {jsonl}")
        try:
            run_window(app, port=args.port)
        finally:
            rec.stop()
            brain.stop()
        return 0

    # replay mode
    import soundfile as sf
    from lma.capture.replay import feed_file_to_bus
    src = Path(args.source)
    info = sf.info(str(src))
    jsonl = src.with_suffix(".transcript.jsonl")
    transcript = Transcript(jsonl_path=jsonl)
    bus = AudioBus(source_samplerate=info.samplerate, capacity_seconds=info.duration + 60)
    brain = Brain(bus, transcript, transcribe_fn, broadcast=hub.publish)
    brain.attach()
    app = create_app(transcript, hub, static_dir=FRONTEND_DIST)
    feed_file_to_bus(src, bus)
    threading.Thread(target=_drive_replay, args=(brain,), daemon=True, name="replay-drive").start()
    print(f"replay UI on http://127.0.0.1:{args.port}  ->  {jsonl}")
    run_window(app, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
