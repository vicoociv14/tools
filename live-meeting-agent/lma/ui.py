"""Thin pywebview window pointing at the live-meeting-agent server.

Run as its own process (pywebview needs the GUI main thread, which the tray icon
also wants). The tray spawns this on meeting start:

  pythonw -m lma.ui --port 8731
"""
from __future__ import annotations

import argparse


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8731)
    ap.add_argument("--title", default="Live Meeting Agent")
    args = ap.parse_args(argv)

    import webview

    webview.create_window(args.title, f"http://127.0.0.1:{args.port}", width=520, height=820)
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
