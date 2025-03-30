import struct
from dataclasses import dataclass, field
import sys
from typing import Dict, List, Tuple
import os
import moderngl
import pygame
import numpy as np
glyph_index = 65

@dataclass
class Glyph:
    glyph_index: int
    num_contours: int
    xmin: int
    ymin: int
    xmax: int
    ymax: int
    end_pts_of_contours: List[int]
    instructions: bytes
    flags: List[int]
    on_curve_points: List[Tuple[int, int]]
    controll_points: list[tuple[int, int]]
    is_composite: bool 

@dataclass
class Font:
    name: str
    num_glyphs: int
    units_per_em: int
    tables: Dict[str, int] = field(default_factory=dict)
    cmap: Dict[int, int] = field(default_factory=dict)
    glyphs: Dict[int, Glyph] = field(default_factory=dict)

def read_ushort(data, offset):
    return struct.unpack(">H", data[offset:offset + 2])[0]

def read_short(data, offset):
    return struct.unpack(">h", data[offset:offset + 2])[0]

def read_uint32(data, offset):
    return struct.unpack(">I", data[offset:offset + 4])[0]

def parse_cmap(font_data, cmap_offset):
    cmap = {}
    num_tables = read_ushort(font_data, cmap_offset + 2)
    best_subtable_offset = None

    for i in range(num_tables):
        platform_id = read_ushort(font_data, cmap_offset + 4 + i * 8)
        encoding_id = read_ushort(font_data, cmap_offset + 6 + i * 8)
        subtable_offset = read_uint32(font_data, cmap_offset + 8 + i * 8)

        if platform_id == 3 and encoding_id == 1:
            best_subtable_offset = cmap_offset + subtable_offset

    if best_subtable_offset is None:
        return {}

    format_type = read_ushort(font_data, best_subtable_offset)
    if format_type == 4:
        seg_count = read_ushort(font_data, best_subtable_offset + 6) // 2
        end_codes_offset = best_subtable_offset + 14
        start_codes_offset = end_codes_offset + seg_count * 2 + 2
        id_deltas_offset = start_codes_offset + seg_count * 2
        id_range_offsets_offset = id_deltas_offset + seg_count * 2
        glyph_id_array_offset = id_range_offsets_offset + seg_count * 2

        for i in range(seg_count):
            start_code = read_ushort(font_data, start_codes_offset + i * 2)
            end_code = read_ushort(font_data, end_codes_offset + i * 2)
            id_delta = read_ushort(font_data, id_deltas_offset + i * 2)
            id_range_offset = read_ushort(font_data, id_range_offsets_offset + i * 2)

            for code in range(start_code, end_code + 1):
                glyph_index = (code + id_delta) % 65536 if id_range_offset == 0 else read_ushort(font_data, glyph_id_array_offset + id_range_offset + 2 * (code - start_code))
                cmap[code] = glyph_index

    return cmap

def parse_glyph(font_data, glyf_offset, loca_offset, glyph_index):
    glyph_start = read_ushort(font_data, loca_offset + glyph_index * 2) * 2
    next_glyph_start = read_ushort(font_data, loca_offset + (glyph_index + 1) * 2) * 2

    if glyph_start == next_glyph_start:
        return None

    glyph_offset = glyf_offset + glyph_start
    num_contours = read_short(font_data, glyph_offset)
    xmin = read_short(font_data, glyph_offset + 2)
    ymin = read_short(font_data, glyph_offset + 4)
    xmax = read_short(font_data, glyph_offset + 6)
    ymax = read_short(font_data, glyph_offset + 8)

    is_composite = num_contours < 0  # Composite glyphs have negative num_contours

    if is_composite:
        return Glyph(glyph_index, num_contours, xmin, ymin, xmax, ymax, [], b"", [], [], [], True)

    # Regular glyph parsing continues here...
    offset = glyph_offset + 10
    end_pts_of_contours = [read_ushort(font_data, offset + i * 2) for i in range(num_contours)]
    offset += num_contours * 2

    instruction_length = read_ushort(font_data, offset)
    offset += 2
    instructions = font_data[offset:offset + instruction_length]
    offset += instruction_length

    num_points = end_pts_of_contours[-1] + 1 if end_pts_of_contours else 0
    flags = []
    coordinates = []

    while len(flags) < num_points:
        flag = font_data[offset]
        offset += 1
        flags.append(flag)
        if flag & 0x08:
            repeat_count = font_data[offset]
            offset += 1
            flags.extend([flag] * repeat_count)

    x_coords = []
    y_coords = []
    x = 0
    y = 0

    for flag in flags:
        if flag & 0x02:
            dx = font_data[offset]
            offset += 1
            x += dx if flag & 0x10 else -dx
        elif not (flag & 0x10):
            x += read_short(font_data, offset)
            offset += 2
        x_coords.append(x)

    for flag in flags:
        if flag & 0x04:
            dy = font_data[offset]
            offset += 1
            y += dy if flag & 0x20 else -dy
        elif not (flag & 0x20):
            y += read_short(font_data, offset)
            offset += 2
        y_coords.append(y)

    coordinates = list(zip(x_coords, y_coords))
    on_curve_points = []
    control_points = []

    for i, (x, y) in enumerate(coordinates):
        if flags[i] & 0x01:  # Bit 0 is set → On-curve point
            on_curve_points.append((x, y))
        else:  # Control point (off-curve)
            control_points.append((x, y))

    pruned_controll_points = []

    i = 0

    for point in control_points:
        if i < len(control_points)-1:
            if iseven(i):
                x = (point[0] + control_points[i + 1][0]) / 2
                y = (point[1] + control_points[i + 1][1]) / 2
                pruned_controll_points.append((x, y))
        i += 1
    i = 0
    for point in on_curve_points:
        on_curve_points[i] = ((point[0] / (xmax/2))-1, (point[1] / (ymax/2))-1) 
        i += 1

    return Glyph(glyph_index, num_contours, xmin, ymin, xmax, ymax, end_pts_of_contours, instructions, flags, on_curve_points, pruned_controll_points, is_composite)

def get_character_index(font: Font, unicode: int):
    return font.cmap[unicode]

def get_glyph(font: Font, unicode: int):
    return font.glyphs[unicode]

def iseven(x):
    return x % 2 == 0

def get_glyph_mesh(glyph: Glyph, program, ctx: moderngl.Context) -> moderngl.VertexArray:
    points = np.array(glyph.on_curve_points, dtype=np.float32)
    int_points = np.array(glyph.on_curve_points, np.uint32)
    # Convert to 1D array for Earcut
    flattened_points = points.flatten()

    # Triangulate the shape
    indices = earcut.triangulate_float32(flattened_points)

    # Convert to vertex buffer
    vertex_data = points[indices]

    
    # Create VAO
    return ctx.vertex_array(program, vertex_data, 'vert', 'texCoord')


def parse_ttf(font_path: str) -> Font:
    with open(font_path, "rb") as file:
        font_data = file.read()

    num_tables = read_ushort(font_data, 4)
    tables = {}
    offset = 12

    for _ in range(num_tables):
        tag = font_data[offset:offset + 4].decode()
        table_offset = read_uint32(font_data, offset + 8)
        tables[tag] = table_offset
        offset += 16

    cmap = parse_cmap(font_data, tables["cmap"])
    glyphs = {i: parse_glyph(font_data, tables["glyf"], tables["loca"], i) for i in range(len(cmap))}

    return Font(name="Custom Font", num_glyphs=len(glyphs), units_per_em=1000, tables=tables, cmap=cmap, glyphs=glyphs)

def gl_setup():
    
    flags = pygame.DOUBLEBUF | pygame.OPENGL
    screen = pygame.display.set_mode((800, 800), flags)
    ctx = moderngl.get_context()
    scale = 100

    text_vert = """
    #version 330 core

    in vec3 vert;
    in vec2 texCoord;
    out vec2 uv;

    void main() {
        uv = texCoord;

        gl_Position = vec4(vert, 1.0);
    }
    """

    text_frag = """
    #version 330 core

    in vec2 uv;
    out vec4 f_color;

    void main() {

        f_color = vec4(uv, 1.0, 1.0);
    }
    """


    program = ctx.program(text_vert, text_frag)
    return get_glyph_mesh(glyph, program, ctx)

def create_fullscreen_quad(ctx, shader):
    quad_vertices = np.array([
        -1.0, -1.0,  0.0, 0.0,  # Bottom-left
         1.0, -1.0,  1.0, 0.0,  # Bottom-right
         1.0,  1.0,  1.0, 1.0,  # Top-right
        -1.0,  1.0,  0.0, 1.0   # Top-left
    ], dtype="f4")

    indices = np.array([
        0, 1, 2,  # First triangle
        2, 3, 0   # Second triangle
    ], dtype="i4")

    vbo = ctx.buffer(quad_vertices)
    ibo = ctx.buffer(indices)

    vao = ctx.vertex_array(
        shader,
        [(vbo, "2f 2f", "vert", "texCoord")],  # Bind attributes
        ibo
    )

    return vao

def gl_render():
    mesh.render(moderngl.TRIANGLE_STRIP)

def sdl_setup():
    flags = pygame.DOUBLEBUF
    return pygame.display.set_mode((800, 800), flags)
    
def sdl_render(glyph):
    for point in glyph.on_curve_points:
        pygame.draw.aacircle(screen, "#FF0000", (point[0] * glyph.xmax/scale+300, (point[1] * glyph.ymax/scale)+300), 2)

def draw_glyph(glyph):
    for i in range(0, len(glyph.on_curve_points)- 1):
        point = glyph.on_curve_points[i]
        next_point = glyph.on_curve_points[i + 1]
        pygame.draw.line(screen, "#0000FF", (point[0] * glyph.xmax/scale+300, (point[1] * glyph.ymax/scale)+300), (next_point[0] * glyph.xmax/scale+300, (next_point[1] * glyph.ymax/scale)+300))


def event_loop():
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

if __name__ == "__main__":
    scale = 3

    font_path = os.path.abspath("game/assets/graphics/fonts/rubik.ttf")
    font = parse_ttf(font_path)

    glyph_index = 65

    pygame.init()

    screen = sdl_setup()
    clock = pygame.Clock()
    time = 0
    timer = 1
    global line_index
    line_index = 0

def event_loop():
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()


def cycle(dir: str):
    if dir == "left":
        glyph_index -= 1
        glyph =  get_glyph(glyph_index)
        while glyph.is_composite:
            glyph_index -= 1
            glyph = get_glyph(glyph_index)

    if dir == "right":
        glyph_index += 1
        glyph =  get_glyph(glyph_index)
        while glyph.is_composite:
            glyph_index += 1
            glyph = get_glyph(glyph_index)
        
    print(glyph)
    screen.fill("#000000")
    draw_glyph()
    sdl_render()

def input():
    print('input')
    keys = pygame.key.get_pressed()
    
    if keys[pygame.K_LEFT]:
        print("hello")
        cycle('left')
    if keys[pygame.K_RIGHT]:
        cycle('right')

while True:
    event_loop()
    dt = clock.tick(2) / 500
    
    input()
    

    pygame.display.flip()

