import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from model import MeetingState, Page, assign_ids, diff_pages
from llm import run_cycle
from drawio import to_drawio_xml, layout_new_entities, add_snapshot, archive_missing_entities


def _load_or_init_state(state_path: Path, meeting_id: str) -> MeetingState:
    if state_path.exists():
        return MeetingState.model_validate_json(state_path.read_text(encoding="utf-8"))
    return MeetingState(
        meeting_id=meeting_id,
        started_at=datetime.now().isoformat(timespec="seconds"),
        active_diagram_type="architecture",
        pages=[],
    )


def _next_seqs(state: MeetingState) -> tuple[int, int]:
    ent = max(
        (int(e.id.split("_")[1]) for p in state.pages for e in p.entities if e.id.startswith("ent_")),
        default=0,
    )
    rel = max(
        (int(r.id.split("_")[1]) for p in state.pages for r in p.relations if r.id.startswith("rel_")),
        default=0,
    )
    return ent + 1, rel + 1


def run_one_cycle(state: MeetingState, transcript_text: str, timestamp_label: str | None = None) -> MeetingState:
    before_live = next(
        (p for p in state.pages if p.role == "live" and p.type == state.active_diagram_type),
        Page(name="empty", type=state.active_diagram_type, role="live"),
    )
    updated = run_cycle(state, transcript_text)
    next_ent, next_rel = _next_seqs(updated)
    for p in updated.pages:
        if p.role == "live":
            next_ent, next_rel = assign_ids(p, next_ent, next_rel)
            layout_new_entities(p)
    after_live = next(
        (p for p in updated.pages if p.role == "live" and p.type == updated.active_diagram_type),
        None,
    )
    if after_live is not None:
        archive_missing_entities(updated, before_live, after_live)
        d = diff_pages(before_live, after_live)
        print(f"+ {d.added}  ~ {d.changed}  - {d.removed}")
    if timestamp_label:
        add_snapshot(updated, timestamp_label)
    return updated


def _parse_interval(value: str) -> float | None:
    if value.lower() == "off":
        return None
    if value.endswith("m"):
        return float(value[:-1]) * 60
    if value.endswith("s"):
        return float(value[:-1])
    return float(value)


def _live_mode(args, state: MeetingState, state_path: Path, drawio_path: Path) -> int:
    from audio import RingBuffer, CaptureThread
    from transcription import TranscriptionThread
    from triggers import IntervalTimer, register_hotkey

    ring = RingBuffer(capacity_seconds=600)
    transcript_sink: list = []
    cap = CaptureThread(ring)
    transcribe = TranscriptionThread(ring, transcript_sink)

    fire_event = threading.Event()

    def trigger():
        fire_event.set()

    interval_seconds = _parse_interval(args.interval)
    timer = IntervalTimer(interval_seconds, trigger) if interval_seconds else None
    unregister_hotkey: Callable[[], None] = lambda: None

    try:
        cap.start()
        transcribe.start()
        if timer:
            timer.start()
        unregister_hotkey = register_hotkey(args.hotkey, trigger)
        print(f"live mode: interval={args.interval}, hotkey={args.hotkey}, Ctrl+C to stop.")
        while True:
            fire_event.wait()
            fire_event.clear()
            new_segments = transcribe.drain()
            state.transcript.extend(new_segments)
            new_text = "\n".join(f"{s.t} {s.text}" for s in new_segments)
            if not new_text:
                print("(no new transcript yet, skipping cycle)")
                continue
            try:
                state = run_one_cycle(state, new_text, timestamp_label=datetime.now().strftime("%H:%M"))
                state_path.write_text(state.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
                drawio_path.write_text(to_drawio_xml(state), encoding="utf-8")
            except Exception as exc:
                print(f"cycle error: {exc!r} - skipping this update")
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        unregister_hotkey()
        cap.stop()
        transcribe.stop()
        if timer:
            timer.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent")
    parser.add_argument("name", help="meeting name (used as folder name)")
    parser.add_argument("--transcript", type=Path, help="batch mode: read this transcript file and exit")
    parser.add_argument("--output-dir", type=Path, default=Path("meetings"))
    parser.add_argument("--interval", default="5m", help="auto-update interval (e.g. 5m, 30s, off)")
    parser.add_argument("--hotkey", default="ctrl+shift+u", help="global hotkey for force-update")
    args = parser.parse_args(argv)

    out = args.output_dir / args.name
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "state.json"
    drawio_path = out / "meeting.drawio"

    state = _load_or_init_state(state_path, args.name)

    if args.transcript:
        text = args.transcript.read_text(encoding="utf-8")
        state = run_one_cycle(state, text, timestamp_label=datetime.now().strftime("%H:%M"))
        state_path.write_text(state.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        drawio_path.write_text(to_drawio_xml(state), encoding="utf-8")
        return 0

    return _live_mode(args, state, state_path, drawio_path)


if __name__ == "__main__":
    raise SystemExit(main())
