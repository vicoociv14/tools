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
