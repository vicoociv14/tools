import json

from lma.archive import index as idx


def _make(tmp_path, mid="260608_073714", titled=False):
    d = tmp_path / "2026-06"
    d.mkdir(parents=True, exist_ok=True)
    jl = d / f"{mid}.transcript.jsonl"
    jl.write_text(
        json.dumps({"start": 0.0, "end": 2.0, "text": "hallo", "speaker": "You", "channel": "mic"}) + "\n"
        + json.dumps({"start": 2.0, "end": 5.0, "text": "ok", "speaker": "Speaker 1", "channel": "system"}) + "\n",
        encoding="utf-8",
    )
    if titled:
        (d / f"{mid}.meta.json").write_text(
            json.dumps({
                "title": "Greeting", "summary": "s", "topics": ["t"],
                "started_at": "2026-06-08T07:37:14", "duration_s": 5.0,
                "speakers": ["You", "Speaker 1"], "segments": 2,
            }),
            encoding="utf-8",
        )
    return jl


def test_meeting_id_and_meta_path(tmp_path):
    jl = _make(tmp_path)
    assert idx.meeting_id(jl) == "260608_073714"
    assert idx.meta_path(jl).name == "260608_073714.meta.json"


def test_parse_started_at():
    assert idx.parse_started_at("260608_073714").startswith("2026-06-08T07:37:14")
    assert idx.parse_started_at("garbage") is None


def test_derive_basic(tmp_path):
    jl = _make(tmp_path)
    b = idx.derive_basic(jl)
    assert b["segments"] == 2
    assert b["duration_s"] == 5.0
    assert b["speakers"] == ["You", "Speaker 1"]


def test_build_index_untitled_has_placeholder(tmp_path):
    _make(tmp_path)
    metas = idx.build_index(tmp_path)
    assert len(metas) == 1
    m = metas[0]
    assert m.id == "260608_073714"
    assert m.titled is False
    assert m.title  # placeholder, not empty


def test_build_index_titled(tmp_path):
    _make(tmp_path, titled=True)
    m = idx.build_index(tmp_path)[0]
    assert m.titled is True
    assert m.title == "Greeting"
    assert m.topics == ["t"]
