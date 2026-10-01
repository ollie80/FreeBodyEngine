"""`.fbimg` - an image stored the way the GPU wants it.

A PNG or JPEG has to be decoded before it can be uploaded, and that
decode is the single largest cost in loading anything with textures in
it: measured at 3.8 seconds of a 4.2 second glTF load, and at 240ms
for four images. None of that work depends on anything only known at
runtime, so a build can do it once and store the result.

What makes this worth a format rather than just "a PNG we decoded" is
that the bytes are already final. They are RGBA, in the orientation
the engine samples standalone textures at (see decode_image_bytes), so
loading one is a read, a zlib inflate and an upload - no decoder, no
colour conversion, no rotation, no second copy.

Lossless, deliberately. The alternative is a GPU block format like BC7
or ASTC, which would be smaller again and skip even the upload
conversion, but those are lossy and most source textures are PNGs that
currently aren't. Shrinking the engine's own storage should not be the
thing that quietly degrades somebody's artwork; if that trade is ever
wanted it belongs behind a per-project flag, not here.

zlib rather than zstd or lz4 because it is in the standard library and
this has to work on every platform the engine runs on, Android and web
included. It roughly halves the raw size and still unpacks faster than
a PNG decode - measured 1.8x on real textures. A faster codec is a
drop-in change if one is ever worth a dependency.
"""
import struct
import zlib

import numpy as np

MAGIC = b"FBIM"
VERSION = 1

# struct: magic, version, flags, width, height, channels, payload length
_HEADER = "<4sHHIIHI"
HEADER_SIZE = struct.calcsize(_HEADER)

FLAG_ZLIB = 1 << 0

# Level 1. The point is to load quickly, and higher levels cost build
# time and inflate time for a few per cent of size on data that is
# already mostly incompressible.
_ZLIB_LEVEL = 1

# Below this, compressing is not worth the inflate on the way back.
_MIN_COMPRESS_BYTES = 4096


def is_fbimg(data) -> bool:
    """Whether `data` looks like one of these, cheaply enough to ask on
    every image the engine loads."""
    return len(data) >= 4 and bytes(data[:4]) == MAGIC


def encode(pixels: np.ndarray, compress: bool = True) -> bytes:
    """Packs an (h, w, channels) uint8 array into a `.fbimg` blob.

    `pixels` must already be in the orientation and channel order the
    engine uploads - this format stores final bytes and does no
    conversion of its own, which is the entire reason it is fast to
    read."""
    array = np.ascontiguousarray(pixels, dtype=np.uint8)
    if array.ndim != 3:
        raise ValueError(f"fbimg expects (height, width, channels), got {array.shape}")
    height, width, channels = array.shape

    raw = array.tobytes()
    flags = 0
    payload = raw
    if compress and len(raw) >= _MIN_COMPRESS_BYTES:
        candidate = zlib.compress(raw, _ZLIB_LEVEL)
        # Only if it actually helped - already-compressed-looking data
        # can come out larger, and then the inflate would be pure cost.
        if len(candidate) < len(raw):
            payload, flags = candidate, flags | FLAG_ZLIB

    header = struct.pack(_HEADER, MAGIC, VERSION, flags, width, height, channels, len(payload))
    return header + payload


def decode(data) -> tuple:
    """Unpacks a `.fbimg` blob to (pixels, width, height).

    Returns a plain (h, w, channels) uint8 array, ready to upload as-is.
    """
    if not is_fbimg(data):
        raise ValueError("Not a .fbimg blob")
    if len(data) < HEADER_SIZE:
        raise ValueError("Truncated .fbimg header")

    _, version, flags, width, height, channels, length = struct.unpack_from(_HEADER, data, 0)
    if version != VERSION:
        raise ValueError(f"Unsupported .fbimg version {version} (this build reads {VERSION})")

    payload = bytes(data[HEADER_SIZE:HEADER_SIZE + length])
    if len(payload) != length:
        raise ValueError("Truncated .fbimg payload")

    raw = zlib.decompress(payload) if flags & FLAG_ZLIB else payload
    expected = width * height * channels
    if len(raw) != expected:
        raise ValueError(f".fbimg claims {width}x{height}x{channels} but holds {len(raw)} bytes")

    pixels = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, channels)
    return pixels, width, height


def encode_image_bytes(data) -> bytes:
    """Converts an encoded image (PNG/JPEG/...) into a `.fbimg` blob.

    Decodes through the same path the runtime would have used, so what
    is stored is exactly what that path would have produced - which is
    what makes substituting one for the other invisible.
    """
    from FreeBodyEngine.graphics.texture import decode_image_bytes
    pixels, _, _ = decode_image_bytes(data)
    return encode(pixels)


# How much larger than its source a baked image may be and still be
# worth storing.
#
# Measured over 67 real textures from three models. The ratio turns out
# to predict the speedup almost perfectly, without needing to know
# anything about the source format: everything at or under 2x was a PNG
# and loaded 1.5-3.0x faster, while everything above 3.5x was a JPEG,
# where zlib'd RGBA is five to twelve times the size and inflating it is
# frequently *slower* than just decoding the JPEG (measured as low as
# 0.43x - i.e. less than half the speed, for twelve times the bytes).
#
# At this threshold, those 67 images bake 27 of themselves, save 1.03s
# of load time and cost 28MB. Raising it to 3x buys 70ms more for
# another 2MB and starts admitting images that lose time; lowering it to
# 1.5x gives up 385ms of real gains. The skipped images forgo 52ms
# between them, which is the price of not having to guess.
MAX_SIZE_RATIO = 2.0


def should_bake(source: bytes, baked: bytes) -> bool:
    """Whether storing `baked` in place of `source` is worth it.

    Purely a size comparison, which sounds like the wrong question and
    is the right one: a source that compresses far better than zlib
    manages on raw pixels is a source whose own decoder is fast and
    whose payload is small, and inflating several times the bytes to
    avoid it does not pay. See MAX_SIZE_RATIO.
    """
    return len(source) > 0 and len(baked) <= len(source) * MAX_SIZE_RATIO


def bake_image_bytes(data: bytes) -> bytes | None:
    """`data` as a `.fbimg`, or None if it should stay as it is.

    None means "keep the original" - either because it could not be
    decoded, or because baking it would cost more space than it saves
    in time.
    """
    if is_fbimg(data):
        return None  # already baked
    try:
        baked = encode_image_bytes(data)
    except Exception:
        return None
    return baked if should_bake(data, baked) else None
