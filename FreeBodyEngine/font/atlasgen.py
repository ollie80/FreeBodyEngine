from FreeBodyEngine.font.msdfgen import generate_char, get_global_metadata
import freetype
from PIL import Image
import math
import os
import time

def generate_atlas(path_or_stream: str, size: int):
    metadata = {}

    face = freetype.Face(path_or_stream)
    ascender, descender, line_height = get_global_metadata(face, size)

    metadata["ascender"] = ascender
    metadata["descender"] = descender
    metadata["line_height"] = line_height

    printable_chars = [chr(i) for i in range(32, 127) if face.get_char_index(i) != 0]
    num_images = len(printable_chars)

    images_per_row = math.ceil(math.sqrt(num_images))
    rows = math.ceil(num_images / images_per_row)

    atlas_width = images_per_row * size
    atlas_height = rows * size

    atlas = Image.new('RGBA', (atlas_width, atlas_height))

    for i, char in enumerate(printable_chars):
        char_str = printable_chars[i]
        if char_str != " ":
            img, char_data = generate_char(char_str, face, size)
            metadata[char_str] = char_data
            x = (i % images_per_row) * size
            y = (i // images_per_row) * size
            atlas.paste(img, (x, y))

    return atlas, metadata

if __name__ == "__main__":
    FONT_PATH = os.path.abspath("./FreeBodyEngine/engine_assets/font/JetBrainsMono.ttf")
    image, data = generate_atlas(FONT_PATH, 16)
    print(data)
    