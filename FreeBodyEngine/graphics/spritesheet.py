from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from FreeBodyEngine.graphics.texture import slice_texture_cell

if TYPE_CHECKING:
    from FreeBodyEngine.graphics.texture import Texture


@dataclass
class Spritesheet:
    """The parsed contents of a `.fbsheet` file: a `cols x rows` grid shared
    across one or more whole-image texture maps (e.g. `albedo`, `normal`)."""
    maps: dict[str, 'Texture']
    size: tuple[int, int]

    def get_cell(self, pos: list, map_name: str = 'albedo') -> Optional['Texture']:
        """Slices out the texture for one `[col, row]` cell of `map_name`."""
        texture = self.maps.get(map_name)
        if texture is None:
            return None

        return slice_texture_cell(texture, pos, self.size)
