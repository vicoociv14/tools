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

    bus.push(_stereo(0.2, 0.0, 1.0))
    bus.push(_stereo(0.0, 0.0, 0.8))
    brain.process_once()
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
