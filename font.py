import pygame
import moderngl

import FreeBodyEngine as engine

import numpy as np
import json

from pygame.locals import DOUBLEBUF, OPENGL
from pygame import Vector2 as vector
from dataclasses import dataclass
from pathlib import Path

VERTEX_SHADER = """
#version 330
in vec4 vertex;
out vec2 TexCoords;

uniform float rotation;
uniform mat4 projection;

void main() {
    gl_Position = projection * vec4(vertex.xy, 0.0, 1.0);
    TexCoords = vertex.zw;
}
"""

FRAGMENT_SHADER = """
#version 330

in vec2 TexCoords;
out vec4 FragColor;

uniform float pxRange;
uniform sampler2D tex;
uniform vec3 textColor;
uniform vec4 outline_color;
uniform float outline_width;

float median(float r, float g, float b) {
    return max(min(r, g), min(max(r, g), b));
}

void main() {
    vec3 sdf = texture(tex, TexCoords).rgb;
    float sigDist = median(sdf.r, sdf.g, sdf.b);
    float screenPxDist = pxRange * (sigDist - 0.5);
    float alpha = clamp(screenPxDist + 0.5, 0.0, 1.0);
    FragColor = vec4(textColor, alpha);
}

"""

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

class TextRenderer:
    def __init__(self, graphics: engine.graphics.Graphics):
        self.graphics = graphics

        self.tex_key = "__ENGINE_font"
        self.program = self.graphics.scene.ctx.program(VERTEX_SHADER, FRAGMENT_SHADER)
        self.vbo = self.graphics.ctx.buffer(reserve=6 * 4 * 4)
        vao_content = [(self.vbo, '4f', 'vertex')]
        self.vao = self.graphics.ctx.vertex_array(self.program, vao_content)
        

    def render_text(self, font: Font, text: str, pos: vector, scale: int, color: tuple, rotation: float, outline_width: int, outline_color: engine.graphics.Color):
        vec = pos.copy()
        
        self.program['textColor'].value = color
        self.program['rotation'] = rotation
        self.program['outline_width'] = outline_width
        self.program['outline_color'] = outline_color.float_normalized_a
        self.program['pxRange'].value = font.pxrange

        key = self.graphics.scene.texture_locker.add(self.tex_key)
        font.tex.use(key)
        self.program["tex"] = key
        
        self.graphics.scene.texture_locker.remove(self.tex_key)

        for c in text:
            ch = font.chars.get(c)
            if not ch:
                continue

            xpos = vec.x + ch.bearing.x * scale
            ypos = vec.y + ch.bearing.y * scale
            w = ch.size.x * scale
            h = ch.size.y * scale
            vertices = np.array([
                xpos,     ypos,     ch.uv_min.x, ch.uv_min.y,
                xpos,     ypos+h,   ch.uv_min.x, ch.uv_max.y,
                xpos+w,   ypos+h,   ch.uv_max.x, ch.uv_max.y,

                xpos,     ypos,     ch.uv_min.x, ch.uv_min.y,
                xpos+w,   ypos+h,   ch.uv_max.x, ch.uv_max.y,
                xpos+w,   ypos,     ch.uv_max.x, ch.uv_min.y
            ], dtype='f4')

            self.vbo.write(vertices.tobytes())
            self.vao.render(moderngl.TRIANGLES)
            vec.x += ch.advance * scale