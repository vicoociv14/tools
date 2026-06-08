from fastapi.testclient import TestClient

from lma.server.server import create_app
from lma.server.hub import TranscriptHub
from lma.brain.state import Segment, Transcript


def _build():
    transcript = Transcript()
    transcript.add(Segment(0.0, 1.0, "hello", "You", "mic"))
    hub = TranscriptHub()
    app = create_app(transcript, hub)
    return app, transcript, hub


def test_api_transcript_returns_segments():
    app, _, _ = _build()
    client = TestClient(app)
    r = client.get("/api/transcript")
    assert r.status_code == 200
    data = r.json()
    assert data[0]["text"] == "hello" and data[0]["speaker"] == "You"


def test_ws_sends_catchup_then_live():
    app, transcript, hub = _build()
    client = TestClient(app)
    with client.websocket_connect("/ws/transcript") as ws:
        first = ws.receive_json()       # catch-up of the existing segment
        assert first["text"] == "hello"
        hub._fanout(Segment(1.0, 2.0, "world", "Remote", "system"))
        nxt = ws.receive_json()
        assert nxt["text"] == "world" and nxt["speaker"] == "Remote"


def test_ask_streams_answer():
    transcript = Transcript()
    hub = TranscriptHub()
    app = create_app(transcript, hub, ask_fn=lambda q: iter(["hel", "lo ", q]))
    client = TestClient(app)
    r = client.post("/api/ask", json={"question": "summary"})
    assert r.status_code == 200
    assert r.text == "hello summary"
