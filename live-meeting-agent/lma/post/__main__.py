"""Post-meeting transcription job - spawned by the tray when a recording ends.

  python -m lma.post <path-to.flac>

Pipeline: transcribe both channels via Azure fast transcription -> write
<id>.transcript.jsonl (ordered, speaker-attributed, timestamped) -> discard the
whole recording if it turns out trivial (almost nothing said) -> generate the
archive title/summary/topics sidecar so the meeting shows up fully labeled.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lma.post.discard import is_trivial_recording  # noqa: E402
from lma.post.fast_stt import transcribe_recording  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "lma" / "capture" / "whisp-rec.log"

log = logging.getLogger("lma.post")


def _setup_logging() -> None:
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main(argv=None) -> int:
    _setup_logging()
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m lma.post <recording.flac>")
        return 2
    flac = Path(argv[0])
    if not flac.exists():
        log.error("post: recording not found: %s", flac)
        return 2

    cfg_path = REPO_ROOT / "lma" / "capture" / "config.json"
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    key = os.environ.get("LMA_SPEECH_KEY") or os.environ.get("LMA_FOUNDRY_API_KEY")
    if not key:
        log.error("post: no LMA_FOUNDRY_API_KEY / LMA_SPEECH_KEY in environment")
        return 3

    jsonl = flac.with_name(flac.stem + ".transcript.jsonl")
    meta = flac.with_name(flac.stem + ".meta.json")

    log.info("post: transcribing %s", flac.name)
    try:
        segments = transcribe_recording(flac, config, key=key)
    except Exception:
        log.exception("post: transcription failed for %s (recording kept)", flac.name)
        return 1

    import soundfile as sf
    duration = sf.info(str(flac)).duration

    # Sparse-discard: the tray already deleted ultra-short clips; here we catch
    # short accidental recordings where almost nothing was actually said.
    if config.get("discard_trivial", True) and is_trivial_recording(
        duration, len(segments),
        float(config.get("discard_max_seconds", 15)),
        int(config.get("discard_max_segments", 10)),
    ):
        for f in (flac, jsonl, meta):
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                log.exception("post: could not delete %s", f)
        log.info("post: discarded trivial recording %s (%.1f s, %d segments)",
                 flac.name, duration, len(segments))
        return 0

    with jsonl.open("w", encoding="utf-8") as f:
        for s in segments:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    log.info("post: wrote %s (%d segments)", jsonl.name, len(segments))

    # Drop any stale sidecar (e.g. titled from an older transcript) so the title
    # is regenerated from this authoritative transcript.
    try:
        if meta.exists():
            meta.unlink()
    except Exception:
        log.exception("post: could not remove stale meta %s", meta)

    # Title immediately so the archive shows a labeled meeting right away.
    try:
        from lma.archive.titler import ensure_meta
        m = ensure_meta(jsonl, config)
        log.info("post: titled '%s'", m.get("title", ""))
    except Exception:
        log.exception("post: titling failed (archive will retry lazily)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
