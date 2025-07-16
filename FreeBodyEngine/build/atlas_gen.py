from PIL import Image
import os

# binary tree packing implementation with PIL images

class Node:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.used = False
        self.right = None
        self.down = None

    def insert(self, img: Image.Image):
        iw, ih = img.size

        if self.used:
            right_insert = self.right.insert(img) if self.right else None
            down_insert = self.down.insert(img) if self.down else None
            return right_insert or down_insert
        
        if iw > self.w or ih > self.h:
            return None

        if iw == self.w and ih == self.h:
            self.used = True
            return self

        self.used = True
        self.down = Node(self.x, self.y + ih, self.w, self.h - ih)
        self.right = Node(self.x + iw, self.y, self.w - iw, ih)
        return self


class AtlasGen:
    def __init__(self, paths: dict[str, str] = None, images: dict[str, Image.Image] = None, atlas_size=1024):
        self.images: dict[str, Image.Image] = {}
        if paths:
            for path in paths:
                self.images[paths[path]] = Image.open(os.path.abspath(path))

        if images:
            self.images.update(images)

        if not self.images:
            raise ValueError('No images provided to atlas generator.')

        self.atlas_size = atlas_size
        self.positions: dict[str, tuple[int, int, int, int]] = {}

    def prepare_images(self):
        self.images = dict(sorted(self.images.items(), key=lambda item: max(item[1].width, item[1].height), reverse=True))

    def build_atlas(self) -> Image.Image:
        self.prepare_images()
        while True:
            atlas = Image.new("RGBA", (self.atlas_size, self.atlas_size))
            root = Node(0, 0, self.atlas_size, self.atlas_size)
            self.positions.clear()

            success = True
            for name, img in self.images.items():
                node = root.insert(img)
                if node is None:
                    success = False
                    break
                atlas.paste(img, (node.x, node.y))
                self.positions[name] = (node.x / self.atlas_size, node.y / self.atlas_size, img.width / self.atlas_size, img.height / self.atlas_size)

            if success:
                return atlas
            else:
                self.atlas_size *= 2

    def save(self, path: str, metadata_path: str = None):
        atlas = self.build_atlas()
        atlas.save(path)

        if metadata_path:
            import json
            with open(metadata_path, "w") as f:
                json.dump(self.positions, f, indent=4)


