"""Python implementation of a Multi-Signed Distance Field Font Generator. https://github.com/Chlumsky/msdfgen"""
import freetype
import numpy as np
from PIL import Image
import math
import os


def get_outline(face, char):
    face.load_char(char, freetype.FT_LOAD_NO_BITMAP)
    outline = face.glyph.outline
    points = np.array(outline.points, dtype=np.float32)
    tags = outline.tags
    contours = outline.contours
    return points, tags, contours

def extract_edges(points, contours):
    edges = []
    start = 0
    for end in contours:
        contour = points[start:end + 1]
        for i in range(len(contour)):
            a = contour[i]
            b = contour[(i + 1) % len(contour)]
            edges.append((a, b))
        start = end + 1
    return edges

def normalize_edges(edges, size, padding):
    all_points = np.vstack([np.array([a, b]) for a, b in edges])
    min_pt = all_points.min(axis=0)
    max_pt = all_points.max(axis=0)
    bbox = max_pt - min_pt
    scale = (size - 2 * padding) / np.max(bbox)
    offset = (np.array([size, size]) - bbox * scale) / 2 - min_pt * scale

    new_edges = []
    for a, b in edges:
        a_new = a * scale + offset
        b_new = b * scale + offset
        new_edges.append((a_new, b_new))
    return new_edges

# signed distance to a line segment
def signed_distance(p, a, b):
    pa = p - a
    ba = b - a
    h = np.clip(np.dot(pa, ba) / np.dot(ba, ba), 0.0, 1.0)
    proj = a + h * ba
    dist = np.linalg.norm(p - proj)
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    side = np.sign(cross)
    return dist * side

# generate SDF
def generate_sdf(edges, size, spread):
    sdf = np.zeros((size, size), dtype=np.float32)
    for y in range(size):
        for x in range(size):
            p = np.array([x + 0.5, y + 0.5])  # center of pixel
            min_d = spread
            for a, b in edges:
                d = signed_distance(p, a, b)
                if abs(d) < abs(min_d):
                    min_d = d
            sdf[y, x] = min_d

    # Normalize
    img = np.clip((sdf / spread) * 127 + 128, 0, 255).astype(np.uint8)
    return Image.fromarray(img, mode='L')


def generate_char(char: str, face: freetype.Face, image_size: int) -> Image:
    spread = image_size / 8  # max distance to measure from edge

    face.set_char_size(image_size * image_size)

    points, tags, contours = get_outline(face, char)
    edges = extract_edges(points, contours)
    norm_edges = normalize_edges(edges, image_size, spread)
    return generate_sdf(norm_edges, image_size, spread).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

