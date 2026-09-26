"""The consumer half of FreeBodyEngine.core.profiler_server - connects to
a running app's ProfilerServer over TCP and hands its stream of per-frame
JSON snapshots to whatever's actually reading them (app.py's GUI)."""
import json
import queue
import socket
import threading

from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.profiler_server import DEFAULT_PORT


class ProfilerClient(Service):
    """Connects to `host:port` (a target app's ProfilerServer) in a
    background thread, decoding newline-delimited JSON snapshots into
    `self.queue` as they arrive - app.py's own per-frame update() drains
    it via poll(), never blocking the render loop on network I/O.

    Reconnects automatically (with a short backoff) if the connection
    drops or was never up in the first place - the target app might not
    be running yet when this starts, or might restart mid-session (a
    `fb run` dev-loop rebuild, say), and this should just keep trying
    rather than giving up once."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        super().__init__('profiler_client')
        self.host = host
        self.port = port
        self.queue: "queue.Queue[dict]" = queue.Queue()
        self.connected = False
        self._running = False
        self._thread: threading.Thread = None
        self._sock: socket.socket = None

    def on_initialize(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ProfilerClient")
        self._thread.start()

    def on_destroy(self):
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def _run_loop(self):
        while self._running:
            try:
                self._sock = socket.create_connection((self.host, self.port), timeout=2)
            except OSError:
                self.connected = False
                threading.Event().wait(1.0)
                continue

            self.connected = True
            buf = b""
            try:
                while self._running:
                    chunk = self._sock.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            self.queue.put(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass
            finally:
                self.connected = False
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    def poll(self, max_items: int = 256) -> list:
        """Drains up to `max_items` queued snapshots (oldest first) -
        called once per frame from the main thread. Bounded so a GUI
        that's fallen behind (window unfocused for a while, say) can't
        be forced to process an unbounded backlog in one frame; anything
        left over is simply picked up on a later call."""
        items = []
        for _ in range(max_items):
            try:
                items.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return items
