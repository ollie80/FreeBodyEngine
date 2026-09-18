"""A tiny local HTTP server for `fb run --web` (see dev/run.py) - just
enough to serve a `dev/web/` build's static files (index.html, bootstrap.py,
vendor.zip/project.zip, the vendored Pyodide runtime) to a browser tab.
Plain `http.server` is genuinely sufficient here: nothing this engine's web
backend uses (fetch, WebGL2, requestAnimationFrame) needs the special
cross-origin-isolation headers (COOP/COEP) that only matter for
SharedArrayBuffer-based multithreading, which this backend doesn't use."""
import http.server
import mimetypes
import socket
import threading


def find_free_port() -> int:
    """Returns a currently-unused TCP port on localhost, by asking the OS
    for one (bind to port 0) and immediately releasing it - the standard
    "ask the kernel" trick, since anything picked by hand risks colliding
    with whatever else happens to be running on this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_handler(directory: str):
    """Returns a SimpleHTTPRequestHandler subclass rooted at `directory`,
    with `.wasm` registered as `application/wasm` - Python's `mimetypes`
    doesn't know that extension out of the box, and Pyodide's own loader
    checks the response's Content-Type before using the faster
    `WebAssembly.compileStreaming` path instead of falling back to a
    slower buffered compile."""
    mimetypes.add_type("application/wasm", ".wasm")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, format, *args):
            # The default implementation writes every single request to
            # stderr - Pyodide's own package-loading fetches alone are
            # dozens of requests, which would otherwise bury `fb run
            # --web`'s own output in a browser boot's incidental noise.
            pass

    return Handler


def serve_forever_in_background(directory: str, port: int) -> http.server.ThreadingHTTPServer:
    """Starts a ThreadingHTTPServer rooted at `directory` on `port`, on a
    daemon background thread, and returns it (so the caller can
    `server.shutdown()` later, e.g. on Ctrl+C) - `fb run --web` needs to
    keep its own foreground thread free to print status/wait for
    interruption, not block inside `serve_forever()` itself."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(directory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
