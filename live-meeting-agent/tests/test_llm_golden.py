import os
import pytest
from pathlib import Path
from llm import run_cycle
from model import MeetingState

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY",
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_cycle_extracts_architecture_entities():
    transcript = (FIXTURES / "transcript_architecture.txt").read_text(encoding="utf-8")
    initial = MeetingState(
        meeting_id="test",
        started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[],
    )
    updated = run_cycle(initial, transcript)
    assert updated.active_diagram_type == "architecture"
    assert len(updated.pages) >= 1
    live = next(p for p in updated.pages if p.role == "live")
    labels = {e.label.lower() for e in live.entities}
    expected_keywords = {"d365", "mt proxy", "translator"}
    matched = sum(1 for kw in expected_keywords if any(kw in l for l in labels))
    assert matched >= 2, f"expected at least 2 of {expected_keywords} in {labels}"
