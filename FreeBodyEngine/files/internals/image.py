from PIL import Image

from io import BytesIO
import struct

FBIMG_SIGNATURE = b"FBIM"

def parse_png(data: bytes):
    """
    Parses .png files into .fbimg files.
    """
    image = Image.open(BytesIO(data))
    width, height = image.width, image.height
    depth = 0
    channels = 4

    header = struct.pack("<4sIIIB", FBIMG_SIGNATURE, width, height, depth, channels)    
    raw = image.tobytes()

    return header + raw

def parse_jpeg(data: bytes):
    """
    Parses .jepg files into .fbimg files.
    """
    image = Image.open(BytesIO(data))
    width, height = image.width, image.height
    depth = 0
    channels = 4

    header = struct.pack("<4sIIIB", FBIMG_SIGNATURE, width, height, depth, channels)    
    raw = image.tobytes()

    return header + raw


def parse_webp(data: bytes):
    """
    Parses .webp files into .fbimg files.
    """
    image = Image.open(BytesIO(data))
    width, height = image.width, image.height
    depth = 0
    channels = 4

    header = struct.pack("<4sIIIB", FBIMG_SIGNATURE, width, height, depth, channels)    
    raw = image.tobytes()

    return header + raw

def parse_avif(data: bytes):
    """
    Parses .avif files into .fbimg files.
    """
    image = Image.open(BytesIO(data))
    width, height = image.width, image.height
    depth = 0
    channels = 4

    header = struct.pack("<4sIIIBx", FBIMG_SIGNATURE, width, height, depth, channels)    
    raw = image.tobytes()

    return header + raw