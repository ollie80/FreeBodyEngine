"""In-process data producer for the external `freebody profile` tool (see
cli/profiler/ - a separate, standalone FreeBodyEngine app with its own
window, built with the engine's own UI, that connects here to render live
graphs/lists and write logs to disk).

Any running FreeBodyEngine app opts in by registering one of these like
any other service, after 'window'/'renderer' already exist:

    fb.register_service(fb.core.profiler_server.ProfilerServer())

It then listens on a local TCP socket (127.0.0.1:47821 by default) and
streams one JSON snapshot per frame - CPU (the same per-phase/per-
callback timing FreeBodyEngine.core.perf_profiler's in-app HUD uses, see
UpdateCoordinator.last_frame_timings), GPU (a timer-query-based
milliseconds figure where the driver supports it, plus a draw-call count
always available regardless), and process memory - to whichever profiler
processes are currently connected. Nothing is sent (and the per-frame
snapshot isn't even built) while nothing is connected, so an app pays
almost nothing for having this registered but unused.

Distinct from FreeBodyEngine.core.perf_profiler.PerformanceProfiler (an
in-app HUD overlay, toggled with F3, drawn with the profiled app's own
UI) - that one is for a quick glance while playing; this one is for a
dedicated, external tool with room for real graphs, historical logs, and
GPU/memory alongside CPU, without competing for space or draw budget with
whatever it's profiling.
"""
import json
import socket
import threading
import sys

from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_main, get_service, service_exists, warning
from FreeBodyEngine.core.update import UpdatePhase

try:
    import resource
except ImportError:
    resource = None  # Windows has no POSIX resource module - memory_mb reads as None there.

DEFAULT_PORT = 47821


class ProfilerServer(Service):
    """See this module's own docstring. Depends on nothing by name (CPU
    timing needs only the always-present updater; GPU/draw-call timing
    and memory are both read defensively, degrading to None rather than
    requiring 'renderer' to exist)."""

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__('profiler_server')
        self.port = port
        self._sock: socket.socket = None
        self._clients: list[socket.socket] = []
        self._clients_lock = threading.Lock()
        self._accept_thread: threading.Thread = None
        self._running = False
        self._frame_index = 0
        self._last_draw_calls = 0

    def on_initialize(self):
        self._running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(("127.0.0.1", self.port))
        except OSError as e:
            # Doesn't raise - a profiling feature failing to bind (another
            # instance of this same app already running, say) shouldn't
            # take down the app it's meant to be observing. Just never
            # accepts a connection; every update() call below finds no
            # clients and does nothing.
            warning(f"ProfilerServer: could not bind 127.0.0.1:{self.port} ({e}) - is this app already being profiled?")
            self._sock = None
            return

        self._sock.listen(1)
        self._sock.settimeout(0.5)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="ProfilerServer-accept")
        self._accept_thread.start()

        get_main().updater.profiling_enabled = True
        # Highest priority in DRAW (runs first among DRAW callbacks) to
        # bracket the *whole* draw phase's GPU work, not just whatever
        # happened to register after this - see update()'s own matching
        # end_gpu_query() call, in LATE (which always runs after every
        # DRAW callback regardless of priority, so it correctly closes
        # out a query no matter how many other DRAW callbacks exist or
        # what order they're in).
        register_service_update(UpdatePhase.DRAW, self._begin_gpu_query, priority=100000)
        register_service_update(UpdatePhase.LATE, self.update, priority=-1000)

    def on_destroy(self):
        self._running = False
        unregister_service_update(UpdatePhase.DRAW, self._begin_gpu_query)
        unregister_service_update(UpdatePhase.LATE, self.update)
        get_main().updater.profiling_enabled = False
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except OSError:
                    pass
            self._clients = []
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def _accept_loop(self):
        while self._running and self._sock is not None:
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.setblocking(False)
            with self._clients_lock:
                self._clients.append(conn)

    def _begin_gpu_query(self):
        if service_exists('renderer'):
            renderer = get_service('renderer')
            if hasattr(renderer, 'begin_gpu_query'):
                renderer.begin_gpu_query()

    @staticmethod
    def _memory_mb():
        if resource is None:
            return None
        # ru_maxrss is KB on Linux, bytes on macOS - the same platform
        # quirk core/perf_profiler-adjacent code elsewhere in this engine
        # already has to account for (see e.g. content_scale's own
        # platform-specific handling for a similar reason).
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return raw / (1024.0 * 1024.0) if sys.platform == "darwin" else raw / 1024.0

    def update(self):
        self._frame_index += 1

        renderer = get_service('renderer') if service_exists('renderer') else None
        if renderer is not None and hasattr(renderer, 'end_gpu_query'):
            renderer.end_gpu_query()

        with self._clients_lock:
            has_clients = bool(self._clients)
        if not has_clients:
            # Nothing connected - don't even build the snapshot. The GPU
            # query above still has to run every frame regardless (its
            # own pool/pending-state has to keep advancing whether or not
            # anyone's listening), but the JSON build + per-client send
            # below is the part actually worth skipping when unused.
            return

        main = get_main()
        timings = main.updater.last_frame_timings
        phases = {
            phase.name: [[label, seconds] for label, seconds in entries]
            for phase, entries in timings.items()
        }

        draw_calls = None
        gpu_ms = None
        if renderer is not None:
            total = getattr(renderer, 'total_draw_calls', None)
            if total is not None:
                draw_calls = total - self._last_draw_calls
                self._last_draw_calls = total
            gpu_ms = getattr(renderer, 'last_gpu_ms', None)

        snapshot = {
            "frame": self._frame_index,
            "time": main.time.get_time(),
            "fps": main.time.get_fps(),
            "tps": main.time.get_tps(),
            "phases": phases,
            "memory_mb": self._memory_mb(),
            "draw_calls": draw_calls,
            "gpu_ms": gpu_ms,
        }
        payload = (json.dumps(snapshot) + "\n").encode("utf-8")

        with self._clients_lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(payload)
                except (BlockingIOError, OSError):
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
                try:
                    c.close()
                except OSError:
                    pass
