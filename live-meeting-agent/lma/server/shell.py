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
        # log_config=None: do NOT let uvicorn run its default logging dictConfig.
        # That config installs a StreamHandler on sys.stderr, which is None under
        # pythonw.exe (the silent tray) and raises "Unable to configure formatter
        # 'default'", killing the live server. With it off, uvicorn's loggers just
        # propagate to the root logger (our FileHandler). access_log off = quieter.
        self._server = uvicorn.Server(
            uvicorn.Config(
                app, host=host, port=port,
                log_level="warning", log_config=None, access_log=False,
            )
        )

    def run(self) -> None:
        self._server.run()

    def stop(self) -> None:
        self._server.should_exit = True

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def run_window(app, host: str = "127.0.0.1", port: int = 8731, title: str = "Live Meeting Agent",
               js_api=None, width: int = 520, height: int = 820) -> None:
    """Start the server in a thread and open a pywebview window at its URL.
    Blocks until the window is closed. `js_api` is exposed to the page as
    window.pywebview.api (the archive uses it for native 'Save As' export)."""
    server = ServerThread(app, host, port)
    server.start()
    time.sleep(0.8)  # let uvicorn bind
    import webview
    webview.create_window(title, server.url, width=width, height=height, js_api=js_api)
    webview.start()
    server.stop()
