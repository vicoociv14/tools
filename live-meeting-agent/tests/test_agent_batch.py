import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY",
)


def test_batch_run_produces_drawio_and_state(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    output_root = tmp_path / "meetings"
    cmd = [
        sys.executable, "agent.py", "smoketest",
        "--transcript", "tests/fixtures/transcript_architecture.txt",
        "--output-dir", str(output_root),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    out = output_root / "smoketest"
    assert (out / "meeting.drawio").exists()
    assert (out / "state.json").exists()
    drawio = (out / "meeting.drawio").read_text(encoding="utf-8")
    assert "<mxfile" in drawio
