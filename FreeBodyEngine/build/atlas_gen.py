from PIL import Image
import os

# binary tree packing implementation with PIL images

class Node:
    """A rectangular free region of the atlas being packed (a binary-tree/
    guillotine bin packer) - `insert()` either places an image directly into
    this region or recurses into its already-split children."""

    def __init__(self, x, y, w, h):
        """A `w` x `h` free region at atlas position `(x, y)`, not yet split or occupied."""
        self.x, self.y, self.w, self.h = x, y, w, h
        self.used = False
        self.right = None
        self.down = None

    def insert(self, img: Image.Image):
        """Attempts to place `img` into this region, or - once split - into
        whichever child region has room. Returns the `Node` `img` was placed
        at (its `(x, y)` is where the caller should paste it), or None if it
        doesn't fit anywhere under this node.

        Placing an image that doesn't exactly fill the region splits it into
        a `right` child (same height as `img`, covering the leftover width)
        and a `down` child (full width, covering the leftover height), so
        the remaining space stays available for later images."""
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
    """Packs a set of named images into one square texture atlas, using
    `Node`'s binary-tree packer and growing the atlas (doubling its size)
    whenever the current size can't fit everything."""

    def __init__(self, paths: dict[str, str] = None, images: dict[str, Image.Image] = None, atlas_size=1024):
        """Builds the set of images to pack, from `paths` (a
        `{disk_path: atlas_name}` map - each opened lazily here) and/or an
        already-loaded `images` (`{atlas_name: Image}`) map. At least one
        must yield a non-empty set of images.

        Raises:
            ValueError: if no images were provided by either argument."""
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
        """Sorts images largest-first (by the longer of width/height), so
        the packer places the hardest-to-fit images before smaller ones -
        packing smallest-first tends to fragment free space and fail to fit
        large images later."""
        self.images = dict(sorted(self.images.items(), key=lambda item: max(item[1].width, item[1].height), reverse=True))

    def build_atlas(self) -> Image.Image:
        """Packs every image into a single square atlas, doubling
        `self.atlas_size` and repacking from scratch whenever the current
        size fails to fit them all. Fills `self.positions` with each
        image's `{name: (x, y, w, h)}` placement, as fractions of the final
        atlas size (ready to use as UV rects). Returns the packed atlas as
        an RGBA `Image`."""
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
        """Builds the atlas and saves it to `path`; if `metadata_path` is
        given, also writes `self.positions` there as JSON."""
        atlas = self.build_atlas()
        atlas.save(path)

        if metadata_path:
            import json
            with open(metadata_path, "w") as f:
                json.dump(self.positions, f, indent=4)


