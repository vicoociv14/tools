"""Decide whether a recording was accidental and should be discarded."""
from __future__ import annotations


def is_trivial_recording(duration: float, seg_count: int, max_seconds: float, max_segments: int) -> bool:
    """An accidental recording: too short, or almost nothing said in a short clip.
    Clips shorter than max_seconds are always trivial; the 'few messages' rule only
    applies to clips under 4x that, so a long real meeting is never auto-deleted."""
    short = duration < max_seconds
    sparse = seg_count <= max_segments and duration < max_seconds * 4
    return short or sparse
