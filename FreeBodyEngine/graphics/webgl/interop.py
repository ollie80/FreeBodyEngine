"""Shared helpers for crossing the Pyodide JS<->Python boundary with real
binary data (vertex/index/uniform/texture bytes) - every other webgl/*.py
module goes through `to_typed_array()`/`to_js_matrix()` instead of building
JS typed arrays inline, so there's exactly one place that encodes how
Pyodide's default argument conversion actually behaves for buffer-protocol
objects, rather than that assumption scattered across mesh/shader/texture/
framebuffer code.

Pyodide's documented default conversion turns a Python `bytes`/`bytearray`
argument into a JS `Uint8Array` automatically the moment it crosses into a
JS call - there is no direct "numpy array -> Float32Array" conversion, so
every helper here goes through `.tobytes()` first, then reinterprets that
Uint8Array's backing `ArrayBuffer` as whichever typed array WebGL2 actually
wants (`Float32Array`/`Uint16Array`/`Uint32Array`/...). This is the
standard, if slightly roundabout, way to hand real binary data to a WebGL
call from Pyodide.
"""
import numpy as np
import js

_DTYPE_TO_JS_CTOR = {
    np.dtype(np.float32): "Float32Array",
    np.dtype(np.uint8): "Uint8Array",
    np.dtype(np.uint16): "Uint16Array",
    np.dtype(np.uint32): "Uint32Array",
    np.dtype(np.int32): "Int32Array",
}


def to_typed_array(array: np.ndarray, dtype=np.float32):
    """Converts `array` (any array-like) into a JS typed array of the JS
    type matching `dtype`, going through raw bytes - see this module's own
    docstring for why. `array` is copied into a fresh, C-contiguous buffer
    of `dtype` first (`np.ascontiguousarray`), so a non-contiguous view or
    a different source dtype (e.g. float64) is always handled correctly,
    not just the already-perfectly-laid-out common case."""
    contiguous = np.ascontiguousarray(array, dtype=dtype)
    ctor_name = _DTYPE_TO_JS_CTOR[np.dtype(dtype)]
    ctor = getattr(js, ctor_name)
    byte_view = js.Uint8Array.new(contiguous.tobytes())
    return ctor.new(byte_view.buffer)


def to_js_matrix(matrix: np.ndarray):
    """Converts a numpy matrix (row-major, as this engine stores every
    transform/view/projection matrix) into the flat column-major
    Float32Array `uniformMatrix*fv` expects - WebGL2 (like desktop GL)
    reads a matrix uniform's flat data in column-major order regardless of
    how the source array is laid out, so this transposes before
    flattening rather than relying on `transpose=true` (which real
    WebGL2/GLES3 drivers are allowed to reject for anything but `false` -
    unlike desktop GL, which tolerates GL_TRUE)."""
    return to_typed_array(matrix.T, dtype=np.float32)
