from lma.post.fast_stt import diarized_to_segments, phrases_to_segments


def _p(offset_ms, dur_ms, text, speaker=None):
    p = {"offsetMilliseconds": offset_ms, "durationMilliseconds": dur_ms, "text": text}
    if speaker is not None:
        p["speaker"] = speaker
    return p


def test_phrases_to_segments_fixed_speaker():
    segs = phrases_to_segments([_p(1000, 2000, "hallo"), _p(4000, 1000, "test")],
                               speaker="You", channel="mic")
    assert segs == [
        {"start": 1.0, "end": 3.0, "text": "hallo", "speaker": "You", "channel": "mic"},
        {"start": 4.0, "end": 5.0, "text": "test", "speaker": "You", "channel": "mic"},
    ]


def test_phrases_to_segments_skips_empty_text():
    segs = phrases_to_segments([_p(0, 100, "  "), _p(200, 100, "ok")], speaker="You", channel="mic")
    assert len(segs) == 1 and segs[0]["text"] == "ok"


def test_diarized_speaker_normalization_first_appearance_order():
    # Azure ids are arbitrary ints; labels must be Speaker 1..N by first appearance
    segs = diarized_to_segments(
        [_p(0, 500, "a", speaker=3), _p(1000, 500, "b", speaker=1), _p(2000, 500, "c", speaker=3)],
        channel="system",
    )
    assert [s["speaker"] for s in segs] == ["Speaker 1", "Speaker 2", "Speaker 1"]


def test_diarized_without_speaker_falls_back_to_remote():
    segs = diarized_to_segments([_p(0, 500, "x")], channel="system")
    assert segs[0]["speaker"] == "Remote"


def test_merged_ordering():
    mic = phrases_to_segments([_p(5000, 1000, "mic late")], speaker="You", channel="mic")
    sys_ = diarized_to_segments([_p(1000, 1000, "sys early", speaker=1)], channel="system")
    merged = sorted(mic + sys_, key=lambda s: s["start"])
    assert [s["text"] for s in merged] == ["sys early", "mic late"]
