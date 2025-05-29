"""
System to generate texture altases to remove the need for constant movement of textures in and out of texture slots.
"""

from PIL import Image
from rectpack import newPacker
import time

class AtlasGen:
    def __init__(self, max_size=(8192,8192)):
        self.max_size = max_size

    def generate(self, paths: list[str], atlas_name_prefix="atlas"):
        start = time.time()
        images = [(path, Image.open(path)) for path in paths]
        rects = [(img.width, img.height) for _, img in images]

        packer = newPacker()

        for i, (w, h) in enumerate(rects):
            packer.add_rect(w, h, i)

        packer.add_bin(self.max_size[0], self.max_size[1], float("inf"))

        packer.pack()

        atlas_images = []
        metadata = {}

        for atlas_index, abin in enumerate(packer):
            atlas_img = Image.new('RGBA', (self.max_size[0], self.max_size[1]), (0, 0, 0, 0))

            for rect in abin:
                x, y = rect.x, rect.y
                w, h = rect.width, rect.height
                idx = rect.rid
                path, img = images[idx]

                # Paste image into atlas
                atlas_img.paste(img, (x, y))

                # Store metadata
                metadata[path] = {
                    "atlas": atlas_index,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "uv": [x / self.max_size[0], y / self.max_size[1], (x + w) / self.max_size[0], (y + h) / self.max_size[1]]
                }

            atlas_filename = f"{atlas_name_prefix}_{atlas_index}.png"
            atlas_img.save(atlas_filename)
            atlas_images.append(atlas_filename)
            print(f"Saved {atlas_filename}")

        print("TIME: ", start - time.time())
        return atlas_images, metadata