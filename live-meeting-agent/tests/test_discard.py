from lma.capture.tray import is_trivial_recording


def test_short_clip_is_trivial():
    # under max_seconds -> trivial regardless of how many segments
    assert is_trivial_recording(8.0, 50, 15, 10) is True


def test_sparse_short_clip_is_trivial():
    # 30s with only 4 segments (and < 4x max) -> trivial
    assert is_trivial_recording(30.0, 4, 15, 10) is True


def test_real_meeting_kept():
    # 10 min with lots said -> keep
    assert is_trivial_recording(600.0, 120, 15, 10) is False


def test_long_but_sparse_is_kept():
    # 10 min but few segments -> still kept (never auto-delete a long recording)
    assert is_trivial_recording(600.0, 3, 15, 10) is False


def test_boundaries():
    assert is_trivial_recording(14.9, 99, 15, 10) is True   # just under -> trivial
    assert is_trivial_recording(15.0, 99, 15, 10) is False  # exactly max, many segs -> keep
