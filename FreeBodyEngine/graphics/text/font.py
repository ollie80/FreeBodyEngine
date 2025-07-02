import pygame
import moderngl

import FreeBodyEngine as engine

import numpy as np
import json

from pygame.locals import DOUBLEBUF, OPENGL
from pygame import Vector2 as vector
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Character:
    uv_min: vector
    uv_max: vector
    size: vector
    bearing: vector
    advance: float

@dataclass
class Font:
    tex: moderngl.Texture
    chars: dict[str, Character]
    pxrange: int

def create_msdf_font(ctx, image_path: str, data_path: str):
    chars = {}
    image = pygame.image.load(image_path).convert_alpha()
    atlas_width, atlas_height = image.get_size()
    image_data = pygame.image.tostring(image, "RGBA", 1)
    tex = ctx.texture((atlas_width, atlas_height), 4, image_data)
    tex.repeat_x = False
    tex.repeat_y = False
    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

    with open(data_path, 'r') as f:
        data = json.load(f)

    for glyph in data["glyphs"]:
        codepoint = glyph["unicode"]
        char = chr(codepoint)
        advance = glyph.get("advance", 0.0)

        if "planeBounds" not in glyph or "atlasBounds" not in glyph:
            if char == " ":
                chars[char] = Character(
                    uv_min=vector(0, 0),
                    uv_max=vector(0, 0),
                    size=vector(0, 0),
                    bearing=vector(0, 0),
                    advance=advance
                )
            else:
                print(f"[!] Skipping unsupported or control character: U+{codepoint:04X} ({repr(char)})")
            continue

        pb = glyph["planeBounds"]
        ab = glyph["atlasBounds"]

        size = vector(pb["right"] - pb["left"], pb["top"] - pb["bottom"])
        bearing = vector(pb["left"], pb["bottom"])
        uv_min = vector(ab["left"] / atlas_width, ab["bottom"] / atlas_height)
        uv_max = vector(ab["right"] / atlas_width, ab["top"] / atlas_height)

        chars[char] = Character(
            uv_min=uv_min,
            uv_max=uv_max,
            size=size,
            bearing=bearing,
            advance=advance
        )

    return Font(tex, chars, data["atlas"]["distanceRange"])
