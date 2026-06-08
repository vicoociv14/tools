import time

import numpy as np

from lma.server.session import LiveSession


def _stub(audio, sr):
    return [(0.0, len(audio) / sr, "x")]


def test_session_start_feeds_transcript_then_stops(tmp_path):
    cfg = {"samplerate": 48000, "server_port": 8799, "ui_auto_open": False}
    s = LiveSession(cfg, transcribe_fn=_stub)
    rec = tmp_path / "m.flac"
    s.start(rec)
    try:
        assert s.brain is not None and s.server is not None
        # 1 s of system "speech" + 0.8 s pause -> one completed utterance
        frame = np.zeros((48000, 2), dtype=np.float32)
        frame[:, 1] = 0.2
        s.bus.push(frame)
        s.bus.push(np.zeros((int(0.8 * 48000), 2), dtype=np.float32))
        jsonl = rec.with_suffix(".transcript.jsonl")
        for _ in range(50):  # brain threads poll ~1 s; wait up to ~5 s
            if jsonl.exists() and jsonl.read_text(encoding="utf-8").strip():
                break
            time.sleep(0.1)
        assert jsonl.exists() and jsonl.read_text(encoding="utf-8").strip(), "no transcript produced"
    finally:
        s.stop()
    assert s.brain is None and s.server is None
