import json
from lma.brain.state import Segment, Transcript


def test_segment_fields():
    s = Segment(start=1.0, end=2.5, text="hi", speaker="You", channel="mic")
    assert s.speaker == "You" and s.channel == "mic"


def test_transcript_orders_by_start():
    t = Transcript()
    t.add(Segment(2.0, 3.0, "second", "Remote", "system"))
    t.add(Segment(0.0, 1.0, "first", "You", "mic"))
    assert [s.text for s in t.segments()] == ["first", "second"]


def test_transcript_text_render():
    t = Transcript()
    t.add(Segment(0.0, 1.0, "hello", "You", "mic"))
    t.add(Segment(1.0, 2.0, "world", "Remote", "system"))
    assert t.text() == "[You] hello\n[Remote] world"


def test_transcript_writes_jsonl(tmp_path):
    p = tmp_path / "m" / "transcript.jsonl"
    t = Transcript(jsonl_path=p)
    t.add(Segment(0.0, 1.0, "hi", "You", "mic"))
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec == {"start": 0.0, "end": 1.0, "text": "hi", "speaker": "You", "channel": "mic"}
