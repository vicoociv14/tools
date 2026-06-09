import json

from fastapi.testclient import TestClient

from lma.archive.server import create_archive_app
from lma.brain import qa


def _seed(tmp_path, mid="260608_073714"):
    d = tmp_path / "2026-06"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mid}.transcript.jsonl").write_text(
        json.dumps({"start": 0.0, "end": 2.0, "text": "wir nehmen Variante C", "speaker": "You", "channel": "mic"}) + "\n",
        encoding="utf-8",
    )
    # seed a title sidecar so the startup backfill never calls Claude
    (d / f"{mid}.meta.json").write_text(
        json.dumps({
            "id": mid, "title": "Variante C", "summary": "sum", "topics": ["routing"],
            "started_at": "2026-06-08T07:37:14", "duration_s": 2.0, "speakers": ["You"], "segments": 1,
        }),
        encoding="utf-8",
    )
    return mid


def test_meetings_list_and_detail(tmp_path):
    mid = _seed(tmp_path)
    with TestClient(create_archive_app(tmp_path, {})) as c:
        data = c.get("/api/meetings").json()
        assert len(data) == 1 and data[0]["title"] == "Variante C"
        detail = c.get(f"/api/meetings/{mid}").json()
        assert detail["meta"]["title"] == "Variante C"
        assert detail["segments"][0]["text"] == "wir nehmen Variante C"


def test_search(tmp_path):
    _seed(tmp_path)
    with TestClient(create_archive_app(tmp_path, {})) as c:
        assert len(c.get("/api/search?q=routing").json()) == 1     # topic
        assert len(c.get("/api/search?q=variante").json()) == 1     # title/transcript
        assert len(c.get("/api/search?q=zzz").json()) == 0


def test_ask_streams(tmp_path, monkeypatch):
    mid = _seed(tmp_path)
    monkeypatch.setattr(qa, "build_client", lambda cfg: (object(), "m"))
    monkeypatch.setattr(qa, "ask_stream", lambda t, q, **k: iter(["ans ", q]))
    with TestClient(create_archive_app(tmp_path, {})) as c:
        r = c.post(f"/api/meetings/{mid}/ask", json={"question": "summary"})
        assert r.status_code == 200
        assert r.text == "ans summary"
