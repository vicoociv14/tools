"""FastAPI server for the Meeting Archive (runs on its own port, e.g. 8732).

Reuses the transcript format and the Foundry-Claude Q&A engine. Serves the
archive UI (archive.html) at /.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..brain import qa
from ..brain.state import Segment, Transcript
from . import index as idx
from . import titler

log = logging.getLogger(__name__)


class AskBody(BaseModel):
    question: str


def _transcript_for(jsonl_path) -> Transcript:
    t = Transcript()
    for s in idx.read_segments(Path(jsonl_path)):
        t.add(Segment(
            start=float(s.get("start", 0.0)), end=float(s.get("end", 0.0)),
            text=s.get("text", ""), speaker=s.get("speaker", ""), channel=s.get("channel", ""),
        ))
    return t


def create_archive_app(recordings_dir, config: dict, static_dir=None) -> FastAPI:
    recordings_dir = Path(recordings_dir)
    static_dir = Path(static_dir) if static_dir else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        def _bf():
            try:
                n = titler.backfill(recordings_dir, config)
                if n:
                    log.info("archive: titled %d meeting(s) on startup", n)
            except Exception:
                log.exception("archive backfill failed")
        threading.Thread(target=_bf, name="archive-backfill", daemon=True).start()
        yield

    app = FastAPI(title="Meeting Archive", lifespan=lifespan)

    def _find(mid: str):
        for p in idx.iter_transcripts(recordings_dir):
            if idx.meeting_id(p) == mid:
                return p
        return None

    @app.get("/api/meetings")
    def meetings():
        return JSONResponse([asdict(m) for m in idx.build_index(recordings_dir)])

    @app.get("/api/meetings/{mid}")
    def meeting(mid: str):
        p = _find(mid)
        if p is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        meta = titler.ensure_meta(p, config)
        return JSONResponse({"meta": meta, "segments": idx.read_segments(p)})

    @app.post("/api/meetings/{mid}/ask")
    def ask(mid: str, body: AskBody):
        p = _find(mid)
        if p is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        transcript = _transcript_for(p)

        def gen():
            try:
                client, model = qa.build_client(config)
                yield from qa.ask_stream(transcript, body.question, client=client, model=model)
            except Exception as e:  # surface to the chat instead of a 500
                yield f"\n[Q&A error: {type(e).__name__}: {e}]"
        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    @app.get("/api/search")
    def search(q: str = ""):
        ql = q.strip().lower()
        if not ql:
            return JSONResponse([])
        out = []
        for m in idx.build_index(recordings_dir):
            hay = (m.title + " " + m.summary + " " + " ".join(m.topics)).lower()
            hit = ql in hay
            if not hit:
                for s in idx.read_segments(Path(m.transcript_path)):
                    if ql in s.get("text", "").lower():
                        hit = True
                        break
            if hit:
                out.append(asdict(m))
        return JSONResponse(out)

    if static_dir is not None and static_dir.exists():
        @app.get("/")
        def root():
            archive_html = static_dir / "archive.html"
            return FileResponse(str(archive_html if archive_html.exists() else static_dir / "index.html"))
        app.mount("/", StaticFiles(directory=str(static_dir)), name="static")

    return app
