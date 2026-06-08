from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..brain import qa
from ..brain.state import Transcript
from .hub import TranscriptHub


class AskBody(BaseModel):
    question: str

POLL_S = 0.1


def create_app(transcript: Transcript, hub: TranscriptHub, static_dir: Optional[Path] = None, ask_fn=None, config: Optional[dict] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        hub.bind_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(title="Live Meeting Agent", lifespan=lifespan)

    if ask_fn is not None:
        _ask = ask_fn
    else:
        _client_cache: dict = {}

        def _ask(q: str):
            # Build the backend client lazily and stream errors into the chat,
            # so a misconfigured Q&A backend never 500s or breaks the transcript.
            def gen():
                try:
                    if "cm" not in _client_cache:
                        _client_cache["cm"] = qa.build_client(config or {})
                    client, model = _client_cache["cm"]
                    yield from qa.ask_stream(transcript, q, client=client, model=model)
                except Exception as e:
                    yield f"\n[Q&A error: {type(e).__name__}: {e}]"

            return gen()

    @app.get("/api/transcript")
    def get_transcript():
        return JSONResponse([asdict(s) for s in transcript.segments()])

    @app.post("/api/ask")
    def ask(body: AskBody):
        return StreamingResponse(_ask(body.question), media_type="text/plain; charset=utf-8")

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
