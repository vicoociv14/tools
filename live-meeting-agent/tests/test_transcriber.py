import numpy as np
from lma.brain.transcriber import ChannelTranscriber
from lma.brain.state import Segment

SR = 16000


def _stub_transcribe(audio, sr):
    return [(0.0, len(audio) / sr, "hello world")]


def _speech(seconds, level=0.2):
    return np.full(int(seconds * SR), level, dtype=np.float32)


def _silence(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_emits_segment_after_complete_utterance():
    out = []
    ct = ChannelTranscriber("mic", speaker="You", emit=out.append, transcribe_fn=_stub_transcribe)
    ct.feed(_speech(1.0))
    ct.feed(_silence(0.8))
    ct.process()
    assert len(out) == 1
    seg = out[0]
    assert isinstance(seg, Segment)
    assert seg.speaker == "You" and seg.channel == "mic"
    assert seg.text == "hello world"
    assert abs(seg.start - 0.0) < 0.05


def test_no_emit_without_pause():
    out = []
    ct = ChannelTranscriber("system", speaker="Remote", emit=out.append, transcribe_fn=_stub_transcribe)
    ct.feed(_speech(1.0))
    ct.process()
    assert out == []


def test_second_utterance_gets_absolute_offset():
    out = []
    ct = ChannelTranscriber("mic", speaker="You", emit=out.append, transcribe_fn=_stub_transcribe)
    ct.feed(_speech(1.0)); ct.feed(_silence(0.8)); ct.process()
    ct.feed(_speech(1.0)); ct.feed(_silence(0.8)); ct.process()
    assert len(out) == 2
    assert out[1].start > out[0].end - 0.01
