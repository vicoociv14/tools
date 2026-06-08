# Live Meeting Agent - M1 Part B (Live Transcript UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Checkbox steps.
>
> **Commit note:** commit only on Vico's go-ahead (he's authorised continuous execution this session).
>
> **Daily-driver safety:** Part B is a **standalone, manually-launched** UI (`serve` entrypoint) fed by a live capture session OR a file-replay. It does **not** touch the always-on tray/recorder. Wiring the UI into the auto-recording tray (auto-live) stays **M4**.

**Goal:** A desktop window that shows the live transcript streaming in, colour-coded by speaker (You vs Remote), launched with one command against either a live mic+system capture or a replayed recording.

**Architecture:** A `TranscriptHub` bridges the `Brain`'s `broadcast` (called from worker threads) to async WebSocket clients via `loop.call_soon_threadsafe`. A FastAPI app serves a built Vite+React SPA and a `/ws/transcript` socket (full catch-up on connect, then live segments). A `serve` entrypoint wires `AudioBus` -> source (live `Recorder` tap or `feed_file_to_bus`) -> `Brain(broadcast=hub.publish)` -> `Transcript` jsonl, runs uvicorn in a thread, and opens a `pywebview` window at the local URL.

**Tech Stack:** FastAPI, uvicorn[standard], pywebview 6.2.1, Vite + React (TypeScript), Node 22 / npm 10. Builds on M1 Part A (`Brain`, `Transcript`, `AudioBus`, `feed_file_to_bus`).

**Spec:** `docs/superpowers/specs/2026-06-07-sparring-partner-design.md`

---

## File Structure (Part B)

```
lma/
├─ server/
│  ├─ __init__.py        # NEW
│  ├─ hub.py             # NEW: TranscriptHub (thread -> async fan-out)
│  ├─ server.py          # NEW: FastAPI app factory (WS + /api + static)
│  ├─ shell.py           # NEW: pywebview window + uvicorn-in-thread
│  └─ frontend/          # NEW: Vite + React SPA (built -> frontend/dist)
│     ├─ index.html, package.json, vite.config.ts, tsconfig*.json
│     └─ src/ (main.tsx, App.tsx, App.css, useTranscript.ts)
├─ serve.py              # NEW: entrypoint wiring source -> brain -> hub -> server -> webview
tests/
├─ test_hub.py          # NEW
└─ test_server.py       # NEW (FastAPI TestClient: /api + WS)
scripts/ (none new)
```

Dependency direction: `hub` depends on `brain.state`. `server` depends on `hub` + `brain.state`. `shell` depends on `server`. `serve` wires `capture`/`brain`/`server`/`shell`. Frontend is independent (talks to the server over HTTP/WS).

---

## Task 1: Part B Python dependencies

**Files:** Modify `requirements.txt`

- [ ] **Step 1: Append to `requirements.txt`**

```
# Live UI (M1 Part B)
fastapi>=0.115
uvicorn[standard]>=0.30
pywebview>=6.2
```

- [ ] **Step 2: Install**

Run: `.\.venv\Scripts\python.exe -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pywebview>=6.2"`
Expected: installs fastapi, uvicorn, starlette, pywebview (+ pythonnet/clr on Windows for the Edge WebView2 backend). Ends `Successfully installed ...`.

- [ ] **Step 3: Verify imports**

Run: `.\.venv\Scripts\python.exe -c "import fastapi, uvicorn, webview; print('ui deps ok')"`
Expected: `ui deps ok`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt && git commit -m "chore(server): add fastapi, uvicorn, pywebview for the live UI"
```

---

## Task 2: TranscriptHub (thread -> async fan-out)

**Files:** Create `lma/server/__init__.py`, `lma/server/hub.py`, `tests/test_hub.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_hub.py`:

```python
import asyncio
import pytest
from lma.server.hub import TranscriptHub
from lma.brain.state import Segment


def _seg(t):
    return Segment(start=t, end=t + 1, text=f"s{t}", speaker="You", channel="mic")


def test_fanout_delivers_to_all_subscribers():
    hub = TranscriptHub()
    q1, q2 = hub.add_subscriber(), hub.add_subscriber()
    hub._fanout(_seg(1))  # direct fan-out (no loop needed)
    assert q1.get_nowait().text == "s1"
    assert q2.get_nowait().text == "s1"


def test_unsubscribe_stops_delivery():
    hub = TranscriptHub()
    q = hub.add_subscriber()
    hub.remove_subscriber(q)
    hub._fanout(_seg(1))
    assert q.empty()


def test_publish_without_loop_is_noop():
    hub = TranscriptHub()
    hub.publish(_seg(1))  # no loop bound -> must not raise


@pytest.mark.asyncio
async def test_publish_threadsafe_reaches_subscriber():
    hub = TranscriptHub()
    hub.bind_loop(asyncio.get_running_loop())
    q = hub.add_subscriber()
    # simulate a brain worker thread publishing
    import threading
    threading.Thread(target=lambda: hub.publish(_seg(7))).start()
    seg = await asyncio.wait_for(q.get(), timeout=2)
    assert seg.text == "s7"
```

Add `pytest-asyncio` for the async test. (If unavailable, the first three tests still cover the core; the async one is the integration check.)

- [ ] **Step 2: Install pytest-asyncio + run (expect import failure first)**

Run: `.\.venv\Scripts\python.exe -m pip install "pytest-asyncio>=0.23" --quiet`
Then add to `requirements.txt` under tests: `pytest-asyncio>=0.23`.
Run: `.\.venv\Scripts\python.exe -m pytest tests/test_hub.py -q`
Expected: `ModuleNotFoundError: No module named 'lma.server'`.

- [ ] **Step 3: Implement**

Write `lma/server/__init__.py`:

```python
"""Live UI server: WebSocket transcript hub + FastAPI app + pywebview shell."""
```

Write `lma/server/hub.py`:

```python
from __future__ import annotations

import asyncio
import logging
import queue
from typing import Optional

from ..brain.state import Segment

log = logging.getLogger(__name__)


class TranscriptHub:
    """Bridges Segments published from Brain worker threads to async WebSocket
    clients. `publish` is thread-safe; `add_subscriber` returns a queue the WS
    handler drains."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: set[queue.SimpleQueue] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add_subscriber(self) -> "queue.SimpleQueue":
        q: queue.SimpleQueue = queue.SimpleQueue()
        self._subscribers.add(q)
        return q

    def remove_subscriber(self, q: "queue.SimpleQueue") -> None:
        self._subscribers.discard(q)

    def _fanout(self, seg: Segment) -> None:
        for q in list(self._subscribers):
            q.put_nowait(seg)

    def publish(self, seg: Segment) -> None:
        """Thread-safe: schedule a fan-out on the server event loop."""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._fanout, seg)
        except RuntimeError:
            log.debug("hub publish after loop close", exc_info=True)
```

(Note: subscribers use `queue.SimpleQueue` so `publish` from any thread is safe and the WS handler polls with a short async sleep - see server.py. This avoids binding `asyncio.Queue` across threads.)

- [ ] **Step 4: Run, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_hub.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add lma/server/__init__.py lma/server/hub.py tests/test_hub.py requirements.txt && git commit -m "feat(server): TranscriptHub bridging brain threads to async clients (TDD)"
```

---

## Task 3: FastAPI app (WS + API + static)

**Files:** Create `lma/server/server.py`, `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_server.py`:

```python
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
        first = ws.receive_json()       # catch-up of existing segment
        assert first["text"] == "hello"
        # publish a new one; hub loop is the TestClient's loop
        hub._fanout(Segment(1.0, 2.0, "world", "Remote", "system"))
        nxt = ws.receive_json()
        assert nxt["text"] == "world" and nxt["speaker"] == "Remote"
```

- [ ] **Step 2: Run, expect failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_server.py -q`
Expected: `ModuleNotFoundError: No module named 'lma.server.server'`.

- [ ] **Step 3: Implement**

Write `lma/server/server.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..brain.state import Transcript
from .hub import TranscriptHub

POLL_S = 0.1


def create_app(transcript: Transcript, hub: TranscriptHub, static_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="Live Meeting Agent")

    @app.on_event("startup")
    async def _bind():
        hub.bind_loop(asyncio.get_running_loop())

    @app.get("/api/transcript")
    def get_transcript():
        return JSONResponse([asdict(s) for s in transcript.segments()])

    @app.websocket("/ws/transcript")
    async def ws_transcript(ws: WebSocket):
        await ws.accept()
        for seg in transcript.segments():            # catch-up
            await ws.send_json(asdict(seg))
        q = hub.add_subscriber()
        try:
            while True:
                try:
                    seg = q.get_nowait()
                except Exception:
                    await asyncio.sleep(POLL_S)
                    continue
                await ws.send_json(asdict(seg))
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove_subscriber(q)

    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
```

(The WS drains the thread-safe `SimpleQueue` with a short poll - simple and robust across the thread/async boundary. `queue.SimpleQueue.get_nowait` raises `queue.Empty`; we catch broadly to keep it dependency-light.)

- [ ] **Step 4: Run, expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_server.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lma/server/server.py tests/test_server.py && git commit -m "feat(server): FastAPI app - /api/transcript + /ws/transcript catch-up+live (TDD)"
```

---

## Task 4: Vite + React frontend

**Files:** Create `lma/server/frontend/` (Vite scaffold + custom `src`)

- [ ] **Step 1: Scaffold a Vite React-TS app (non-interactive)**

Run from `lma/server`:
`Set-Location C:\Tools\live-meeting-agent\lma\server; npm create vite@latest frontend -- --template react-ts`
Then: `Set-Location frontend; npm install`
Expected: project created in `lma/server/frontend`, dependencies installed.

- [ ] **Step 2: Set the Vite config for relative base + API/WS dev proxy**

Overwrite `lma/server/frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./", // assets resolve when served by FastAPI at any root
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8731",
      "/ws": { target: "ws://127.0.0.1:8731", ws: true },
    },
  },
  build: { outDir: "dist" },
});
```

- [ ] **Step 3: Write the WebSocket hook**

Overwrite `lma/server/frontend/src/useTranscript.ts`:

```ts
import { useEffect, useRef, useState } from "react";

export type Segment = {
  start: number; end: number; text: string; speaker: string; channel: string;
};

export function useTranscript() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws/transcript`;
    let stop = false;

    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!stop) setTimeout(connect, 1000); // auto-reconnect
      };
      ws.onmessage = (ev) => {
        const seg: Segment = JSON.parse(ev.data);
        setSegments((prev) => [...prev, seg].sort((a, b) => a.start - b.start));
      };
    }
    connect();
    return () => { stop = true; wsRef.current?.close(); };
  }, []);

  return { segments, connected };
}
```

- [ ] **Step 4: Write the App component**

Overwrite `lma/server/frontend/src/App.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { useTranscript, Segment } from "./useTranscript";
import "./App.css";

function fmt(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function speakerClass(sp: string): string {
  if (sp === "You") return "you";
  if (sp === "Remote") return "remote";
  return "other";
}

export default function App() {
  const { segments, connected } = useTranscript();
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [segments.length]);

  return (
    <div className="app">
      <header>
        <h1>Live Meeting Agent</h1>
        <span className={connected ? "dot on" : "dot off"} />
        <span className="status">{connected ? "live" : "reconnecting…"}</span>
        <span className="count">{segments.length} segments</span>
      </header>
      <main className="transcript">
        {segments.length === 0 && <p className="empty">Waiting for speech…</p>}
        {segments.map((s: Segment, i: number) => (
          <div key={i} className={`seg ${speakerClass(s.speaker)}`}>
            <span className="meta">{fmt(s.start)} · {s.speaker}</span>
            <span className="text">{s.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Write the styles**

Overwrite `lma/server/frontend/src/App.css`:

```css
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body, html, #root { margin: 0; height: 100%; }
.app { display: flex; flex-direction: column; height: 100vh; font-family: "Segoe UI", system-ui, sans-serif; background: #14161a; color: #e8e8e8; }
header { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid #262a31; }
header h1 { font-size: 15px; margin: 0; font-weight: 600; }
.dot { width: 9px; height: 9px; border-radius: 50%; }
.dot.on { background: #3fb950; } .dot.off { background: #d29922; }
.status { font-size: 12px; color: #9aa4b2; }
.count { margin-left: auto; font-size: 12px; color: #6e7681; }
.transcript { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }
.empty { color: #6e7681; font-style: italic; }
.seg { display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; border-radius: 8px; max-width: 80%; }
.seg .meta { font-size: 11px; opacity: 0.7; }
.seg.you { align-self: flex-end; background: #1f6feb33; border: 1px solid #1f6feb55; }
.seg.remote { align-self: flex-start; background: #2d333b; border: 1px solid #3a414b; }
.seg.other { align-self: flex-start; background: #5a3a8a33; border: 1px solid #6e54a655; }
.seg .text { font-size: 14px; line-height: 1.35; }
```

- [ ] **Step 6: Strip the default index.html branding (optional title)**

Edit `lma/server/frontend/index.html`: set `<title>Live Meeting Agent</title>`.

- [ ] **Step 7: Build**

Run: `Set-Location C:\Tools\live-meeting-agent\lma\server\frontend; npm run build`
Expected: `dist/` produced with `index.html` + hashed assets, no TS errors.

- [ ] **Step 8: Gitignore node_modules; commit source + built dist**

Append to repo `.gitignore`: `lma/server/frontend/node_modules/`.
(We DO commit `dist/` so the app runs without a Node build on every checkout.)

```bash
git add .gitignore lma/server/frontend && git commit -m "feat(ui): Vite+React live transcript SPA (you/remote bubbles, autoscroll, reconnect)"
```

---

## Task 5: pywebview shell + serve entrypoint

**Files:** Create `lma/server/shell.py`, `lma/serve.py`

- [ ] **Step 1: Implement the shell (uvicorn in a thread + pywebview window)**

Write `lma/server/shell.py`:

```python
from __future__ import annotations

import logging
import threading
import time

import uvicorn

log = logging.getLogger(__name__)


class ServerThread(threading.Thread):
    def __init__(self, app, host: str = "127.0.0.1", port: int = 8731):
        super().__init__(daemon=True, name="lma-server")
        self.host = host
        self.port = port
        self._server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))

    def run(self) -> None:
        self._server.run()

    def stop(self) -> None:
        self._server.should_exit = True

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def run_window(app, host: str = "127.0.0.1", port: int = 8731, title: str = "Live Meeting Agent") -> None:
    """Start the server in a thread and open a pywebview window at its URL.
    Blocks until the window is closed."""
    server = ServerThread(app, host, port)
    server.start()
    time.sleep(0.8)  # let uvicorn bind
    import webview
    webview.create_window(title, server.url, width=520, height=820)
    webview.start()
    server.stop()
```

- [ ] **Step 2: Implement the serve entrypoint**

Write `lma/serve.py`:

```python
"""Launch the live-transcript UI.

  # replay a recording into the UI (no meeting needed):
  python -m lma.serve --source "C:\\Tools\\live-meeting-agent\\recordings\\<file>.flac"

  # live: capture mic+system now and show the transcript:
  python -m lma.serve --source live

Writes <name>.transcript.jsonl next to the source (replay) or under recordings/ (live).
"""
from __future__ import annotations

import argparse
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lma.brain.brain import Brain                       # noqa: E402
from lma.brain.state import Transcript                  # noqa: E402
from lma.brain.whisper_engine import make_transcribe_fn  # noqa: E402
from lma.capture.bus import AudioBus                    # noqa: E402
from lma.server.hub import TranscriptHub                # noqa: E402
from lma.server.server import create_app                # noqa: E402
from lma.server.shell import run_window                 # noqa: E402

FRONTEND_DIST = Path(__file__).resolve().parent / "server" / "frontend" / "dist"


def _drive_replay(brain: Brain) -> None:
    while True:
        before = brain.mic._buf.size + brain.system._buf.size   # noqa: SLF001
        brain.process_once()
        after = brain.mic._buf.size + brain.system._buf.size     # noqa: SLF001
        if after == before:
            break
    brain.mic.flush()
    brain.system.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="'live' or a path to a .flac/.wav")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--model", default="small")
    ap.add_argument("--port", type=int, default=8731)
    args = ap.parse_args(argv)

    hub = TranscriptHub()
    transcribe_fn = make_transcribe_fn(args.lang, args.model)

    if args.source == "live":
        from lma.capture.recorder import Recorder, RecorderConfig
        out_dir = Path(__file__).resolve().parent.parent / "recordings" / datetime.now().strftime("%Y-%m")
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl = out_dir / (datetime.now().strftime("%y%m%d_%H%M%S") + ".transcript.jsonl")
        transcript = Transcript(jsonl_path=jsonl)
        bus = AudioBus(source_samplerate=48000, capacity_seconds=3600)
        brain = Brain(bus, transcript, transcribe_fn, broadcast=hub.publish)
        brain.attach()
        rec = Recorder(RecorderConfig(output_dir=out_dir.parent), tap=bus.push)
        rec.start()
        brain.start()
        app = create_app(transcript, hub, static_dir=FRONTEND_DIST)
        print(f"live UI on http://127.0.0.1:{args.port}  ->  {jsonl}")
        try:
            run_window(app, port=args.port)
        finally:
            rec.stop()
            brain.stop()
        return 0

    # replay mode
    import soundfile as sf
    from lma.capture.replay import feed_file_to_bus
    src = Path(args.source)
    info = sf.info(str(src))
    jsonl = src.with_suffix(".transcript.jsonl")
    transcript = Transcript(jsonl_path=jsonl)
    bus = AudioBus(source_samplerate=info.samplerate, capacity_seconds=info.duration + 60)
    brain = Brain(bus, transcript, transcribe_fn, broadcast=hub.publish)
    brain.attach()
    app = create_app(transcript, hub, static_dir=FRONTEND_DIST)
    # feed + transcribe in the background so the window shows segments appear
    feed_file_to_bus(src, bus)
    threading.Thread(target=_drive_replay, args=(brain,), daemon=True, name="replay-drive").start()
    print(f"replay UI on http://127.0.0.1:{args.port}  ->  {jsonl}")
    run_window(app, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Byte-compile**

Run: `.\.venv\Scripts\python.exe -m py_compile lma\server\shell.py lma\serve.py`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add lma/server/shell.py lma/serve.py && git commit -m "feat(server): pywebview shell + serve entrypoint (replay + live sources)"
```

---

## Task 6: End-to-end - replay into the window

**Files:** none (manual verification).

- [ ] **Step 1: Headless server smoke (no window) - confirm the app serves the built UI**

Run:
`.\.venv\Scripts\python.exe -c "from pathlib import Path; from lma.server.server import create_app; from lma.server.hub import TranscriptHub; from lma.brain.state import Transcript; from fastapi.testclient import TestClient; d=Path('lma/server/frontend/dist'); c=TestClient(create_app(Transcript(), TranscriptHub(), static_dir=d)); r=c.get('/'); print('index', r.status_code, 'has root div:', 'id=\"root\"' in r.text)"`
Expected: `index 200 has root div: True`.

- [ ] **Step 2: Visual E2E (user at the keyboard)** - replay a clip into the window:

`.\.venv\Scripts\python.exe -m lma.serve --source "C:\Tools\live-meeting-agent\recordings\260515_092957.flac"`

Expected: a desktop window opens titled "Live Meeting Agent"; within a few seconds, **You** (right, blue) and **Remote** (left, grey) bubbles stream in with timestamps; the status dot is green ("live"); segment count climbs. Close the window to exit.

- [ ] **Step 3: (Optional) live test:** `python -m lma.serve --source live`, speak / play audio, watch bubbles appear, close window.

**End of M1 Part B.** Tag: `git tag M1b`.

---

## Self-Review (M1 Part B vs spec)

- **Local web UI in a desktop window** (spec "App shell" = web UI + pywebview): Tasks 4 (React SPA) + 5 (pywebview shell). Covered.
- **Live transcript over WebSocket, colour-coded by speaker** (spec UI panes): Task 3 (WS) + Task 4 (you/remote bubbles, autoscroll, status). Covered.
- **Fed by live capture OR replay** (spec testing "file-replay enabler"): Task 5 serve `--source live|<file>`. Covered.
- **Daily-driver-safe**: standalone `serve`; no tray change. Auto-live wiring deferred to M4 (per spec). Covered.
- **React/Vite stack** (Vico's pick): Task 4. Covered.

Type/name consistency: `TranscriptHub.add_subscriber/remove_subscriber/_fanout/publish/bind_loop`, `create_app(transcript, hub, static_dir)`, `run_window(app, host, port, title)`, `Brain(..., broadcast=hub.publish)`, `feed_file_to_bus`, frontend `Segment{start,end,text,speaker,channel}` matches the jsonl schema. No placeholders; all code/commands concrete.

## Deferred (later milestones)
- M2: Claude Q&A over the transcript (chat box + presets + drawio artifact) in the same UI.
- M3: pyannote diarization -> "Speaker 1/2/3" replacing "Remote"; speaker legend with rename/merge.
- M4: wire the brain+UI into the auto-recording tray (auto-live), CPU-contention tuning, post-meeting clean re-diarization.
