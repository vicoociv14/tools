"""Launch the Meeting Archive desktop window.

  python -m lma.archive [--port 8732]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lma.archive.server import create_archive_app  # noqa: E402
from lma.server.shell import run_window            # noqa: E402

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "server" / "frontend" / "dist"


class ArchiveApi:
    """Exposed to the archive UI as window.pywebview.api. Lets the page save a
    transcript to a user-chosen location via the native OS Save dialog."""

    def save_text_file(self, suggested_filename: str, content: str):
        import webview
        try:
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=suggested_filename or "transcript.txt",
                file_types=("Text files (*.txt)", "Markdown (*.md)", "All files (*.*)"),
            )
        except Exception:
            return None
        if not result:
            return None
        path = result if isinstance(result, str) else result[0]
        try:
            Path(path).write_text(content, encoding="utf-8")
            return path
        except Exception:
            return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8732)
    args = ap.parse_args(argv)
    cfg_path = Path(__file__).resolve().parents[1] / "capture" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    app = create_archive_app(cfg["output_dir"], cfg, static_dir=FRONTEND_DIST)
    print(f"Meeting Archive on http://127.0.0.1:{args.port}")
    run_window(app, port=args.port, title="Meeting Archive", js_api=ArchiveApi(), width=1100, height=780)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
