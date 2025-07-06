from FreeBodyEngine.font.msdfgen import generate_char
import freetype
from PIL import Image
import math
import os
import time

def generate_atlas(path_or_stream: str, size: int):
    
    face = freetype.Face(path_or_stream)

    # Use printable ASCII range as an example (you can expand this)
    printable_chars = [chr(i) for i in range(32, 127) if face.get_char_index(i) != 0]
    print(printable_chars)
    num_images = len(printable_chars)

    images_per_row = math.ceil(math.sqrt(num_images))
    rows = math.ceil(num_images / images_per_row)

    atlas_width = images_per_row * size
    atlas_height = rows * size

    atlas = Image.new('RGBA', (atlas_width, atlas_height))

    for i, char in enumerate(printable_chars):
        char_str = printable_chars[i]
        if char_str != " ":
            img = generate_char(char_str, face, size)
            x = (i % images_per_row) * size
            y = (i // images_per_row) * size
            atlas.paste(img, (x, y))

    return atlas

if __name__ == "__main__":
    FONT_PATH = os.path.abspath("./FreeBodyEngine/engine_assets/font/JetBrainsMono.ttf")
    start_time = time.time()
    generate_atlas(FONT_PATH, 16).save('atlas.png')
    elapsed = time.time() - start_time

    print(f"Elapsed time: {elapsed:.3f} seconds")
    