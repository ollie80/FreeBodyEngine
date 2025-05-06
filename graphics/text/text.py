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