"""One-off e2e: archive server lists + lazily titles a meeting via Foundry Claude.

  set LMA_FOUNDRY_API_KEY=...
  python scripts/archive_e2e.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from lma.archive.server import create_archive_app

cfg = json.loads((Path(__file__).resolve().parents[1] / "lma" / "capture" / "config.json").read_text(encoding="utf-8"))
root = Path(tempfile.mkdtemp())
d = root / "2026-06"
d.mkdir(parents=True)
(d / "260608_090000.transcript.jsonl").write_text(
    "\n".join([
        json.dumps({"start": 0, "end": 3, "text": "Wir besprechen das Routing fuer Festo und nehmen Variante C.", "speaker": "You", "channel": "mic"}),
        json.dumps({"start": 3, "end": 6, "text": "Einverstanden, ich kuemmere mich um die Queue-Konfiguration.", "speaker": "Speaker 1", "channel": "system"}),
    ]) + "\n",
    encoding="utf-8",
)

app = create_archive_app(root, cfg)
with TestClient(app) as c:
    meetings = c.get("/api/meetings").json()
    print("meetings listed:", len(meetings))
    det = c.get("/api/meetings/260608_090000").json()
    print("TITLE   :", det["meta"]["title"])
    print("SUMMARY :", det["meta"]["summary"])
    print("TOPICS  :", det["meta"]["topics"])
