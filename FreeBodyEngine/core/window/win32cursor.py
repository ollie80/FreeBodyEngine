import io
import ctypes
import struct
from PIL import Image

user32 = ctypes.windll.user32
LR_DEFAULTSIZE = 0x00000040

def rgba_to_bitmap_and_mask(img: Image.Image):
    """
    Convert RGBA image to raw BMP AND mask format.
    Returns (bmp_bits, and_mask_bits)
    """

    width, height = img.size
    pixels = img.load()

    row_size = ((width + 31) // 32) * 4
    and_mask = bytearray(row_size * height)

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, height - 1 - y]
            if a == 0:
                byte_index = y * row_size + (x // 8)
                bit_index = 7 - (x % 8)
                and_mask[byte_index] |= (1 << bit_index)

    bmp_bits = bytearray()
    for y in reversed(range(height)):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            bmp_bits.extend([b, g, r, 0])

    return bmp_bits, and_mask

def build_cursor_from_pil(img: Image.Image, hotspot=(0, 0)):
    img = img.convert("RGBA")
    width, height = img.size

    biSize = 40
    biWidth = width
    biHeight = height * 2  # height * 2 because includes XOR + AND masks
    biPlanes = 1
    biBitCount = 32
    biCompression = 0  # BI_RGB = uncompressed
    biSizeImage = width * height * 4  # bytes for XOR bitmap
    biXPelsPerMeter = 0
    biYPelsPerMeter = 0
    biClrUsed = 0
    biClrImportant = 0

    header = struct.pack("<IiiHHIIiiII",
        biSize, biWidth, biHeight, biPlanes, biBitCount, biCompression,
        biSizeImage, biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant)

    bmp_bits, and_mask = rgba_to_bitmap_and_mask(img)

    # Reserved (2 bytes), must be 0
    # Type (2 bytes), 2 for cursor
    # Count (2 bytes), number of images (1)
    icondir = struct.pack("<HHH", 0, 2, 1)
    

    # Step 4: ICONDIRENTRY (16 bytes)
    bWidth = width if width < 256 else 0
    bHeight = height if height < 256 else 0
    bColorCount = 0
    bReserved = 0
    wHotspotX, wHotspotY = hotspot
    dwBytesInRes = 6 + 16 + len(header) + len(bmp_bits) + len(and_mask)  # size of entire resource (icon header + image)
    dwImageOffset = 6 + 16  # offset to image data after ICONDIR + ICONDIRENTRY

    icondirentry = struct.pack("<BBBBHHII",
        bWidth,
        bHeight,
        bColorCount,
        bReserved,
        wHotspotX,
        wHotspotY,
        dwBytesInRes,
        dwImageOffset
    )

    cur_data = bytearray()
    cur_data += icondir
    cur_data += icondirentry
    cur_data += header
    cur_data += bmp_bits
    cur_data += and_mask

    buffer = ctypes.create_string_buffer(bytes(cur_data))

    hcursor = user32.CreateIconFromResourceEx(
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        len(cur_data),
        False,           # fIcon = False for cursor
        0x00030000,      # version
        0, 0,            # use default size
        LR_DEFAULTSIZE
    )
    if not hcursor:
        raise ctypes.WinError(ctypes.get_last_error())

    return hcursor

