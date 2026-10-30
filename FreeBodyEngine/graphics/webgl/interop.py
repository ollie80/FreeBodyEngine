"""Shared helpers for crossing the Pyodide JS<->Python boundary with real
binary data (vertex/index/uniform/texture bytes) - every other webgl/*.py
module goes through `to_typed_array()`/`to_js_matrix()` instead of building
JS typed arrays inline, so there's exactly one place that encodes how
Pyodide's default argument conversion actually behaves for buffer-protocol
objects, rather than that assumption scattered across mesh/shader/texture/
framebuffer code.

There is no direct "numpy array -> Float32Array" conversion, so these
allocate the typed array JS-side and fill it with `assign()`, which does a
bulk memcpy out of any Python buffer.

Not `Ctor.new(some_bytes)`, which looks equivalent and is the obvious way
to write it: Pyodide treats a Python `bytes` argument as an *iterable* there
and converts it one element at a time. For the 2 MB of an on-screen overlay
that is **952 ms**, against 0.15 ms for the same copy through `assign()` -
measured under Pyodide 0.26.4, a factor of about six thousand. Every mesh
and every texture in a web build goes through this function, so that one
line was most of what a browser spent its time doing.
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
    out = ctor.new(contiguous.size)
    out.assign(memoryview(contiguous))
    return out


def to_js_matrix(matrix: np.ndarray):
    """Converts a numpy matrix into the flat Float32Array
    `uniformMatrix*fv` takes, in the matrix's own row-major memory order -
    exactly the bytes GL33Shader hands glUniformMatrix4fv with GL_FALSE,
    which is what the engine's matrices and shaders are written against
    (model matrices keep their translation in the last row and rely on
    that upload to land it in GL's last column).

    This used to transpose first. Every matrix then reached the shader
    transposed relative to desktop: a model matrix's translation ended up
    in the w row, so each vertex got w = 1 - tx*x - ty*y and every sprite
    was clipped away - the WebGL build drew nothing but its clear colour.
    `transpose=true` is still avoided either way: WebGL2 rejects it."""
    return to_typed_array(matrix, dtype=np.float32)
