from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import get_service, warning
import numpy as np
from enum import Enum, auto

class AttributeType(Enum):
    """Per-vertex attribute layout a Mesh's `attributes` dict declares for
    one channel (e.g. "verticies", "uvs"). Only FLOAT/VEC2/VEC3/VEC4/INT/
    IVEC2/IVEC3/IVEC4 are actually handled by the GL33/GL44 backends'
    upload() (see GLMesh.upload) - MAT3/MAT4/VEC5/VEC6/IVEC5/IVEC6 raise
    there."""
    FLOAT = auto()
    VEC2 = auto()
    VEC3 = auto()
    VEC4 = auto()
    VEC5 = auto()
    VEC6 = auto()

    INT = auto()
    IVEC2 = auto()
    IVEC3 = auto()
    IVEC4 = auto()
    IVEC5 = auto()
    IVEC6 = auto()

    MAT3 = auto()
    MAT4 = auto()


class PrimitiveType(Enum):
    """GL primitive topology a Mesh's vertex/index data is drawn as."""
    TRIANGLES = auto()
    TRIANGLE_STRIP = auto()
    TRIANGLE_FAN = auto()


class IndexType(Enum):
    """Index buffer element width - GLMesh selects GL_UNSIGNED_SHORT for
    UINT16 or GL_UNSIGNED_INT for UINT32 when uploading/drawing indices."""
    UINT16 = auto()
    UINT32 = auto()

class BufferUsage(Enum):
    """GPU buffer update-frequency hint, mapped to GL_STATIC_DRAW/
    GL_DYNAMIC_DRAW/GL_STREAM_DRAW by the GL backends. A STATIC mesh
    additionally refuses set_data() calls - see Mesh.set_data."""
    STATIC = auto()
    DYNAMIC = auto()
    STREAM = auto()

class Mesh:
    """Backend-agnostic vertex/index geometry: a dict of named per-vertex
    attributes (`{"verticies": (AttributeType.VEC3, array), ...}`), optional
    indices, and drawing/update-frequency hints. Concrete backends (GLMesh
    etc.) own the actual GPU buffers and implement uploading/drawing/
    destroying them."""
    def __init__(
        self,
        attributes: dict[str, tuple[AttributeType, np.ndarray]],
        indices: np.ndarray = None,
        primitive: PrimitiveType = PrimitiveType.TRIANGLES,
        index_type: IndexType = IndexType.UINT16,
        usage: BufferUsage = BufferUsage.STATIC,
    ):
        """Stores the mesh's attribute/index data and drawing hints;
        uploading them to the GPU is left to a concrete subclass's
        constructor."""

        self.attributes = attributes
        self.indices = indices
        self.primitive = primitive
        self.index_type = index_type
        self.usage = usage

    @abstractmethod
    def destroy(self):
        """Releases the mesh's underlying GPU resources."""
        pass

    @abstractmethod
    def _set_attribute_data(self, attribute_name: str, data: np.ndarray):
        pass

    def set_data(self, attribute_name: str, data: np.ndarray):
        """Updates one attribute's data in place - a no-op (with a warning)
        if this mesh's `usage` is STATIC, since a static mesh's buffers
        aren't expected to change after upload."""
        if self.usage == BufferUsage.STATIC:
            warning("Cannot set data of a static Mesh.")
            return
        self._set_attribute_data(attribute_name, data)

    @abstractmethod
    def draw(self):
        """Issues the draw call for this mesh using its currently uploaded
        GPU buffers."""
        pass


def create_static_mesh(
    verticies: np.ndarray,
    uvs: np.ndarray,
    normals: np.ndarray,
    indices: np.ndarray,
    buffer_usage: BufferUsage = BufferUsage.STATIC,
    primitive: PrimitiveType = PrimitiveType.TRIANGLES,
) -> Mesh:
    """Builds a Mesh (via the active renderer's mesh class) from raw vertex/
    uv/normal arrays plus `indices`, always as IndexType.UINT32 regardless of
    Mesh's own UINT16 default - see the comment on `index_type` below."""
    return get_service("renderer").get_mesh_class()(
        {
            "verticies": (AttributeType.VEC3, verticies),
            "uvs": (AttributeType.VEC2, uvs),
            "normals": (AttributeType.VEC3, normals),
        },
        indices=indices,
        # Every caller here (this module's generate_*() helpers and the glTF
        # loader in core/files/loaders/model.py) builds `indices` as uint32 -
        # Mesh's own default (IndexType.UINT16) silently mismatched that,
        # making GLMesh.draw() read a uint32 index buffer 2 bytes at a time
        # (GL_UNSIGNED_SHORT) instead of 4, corrupting every indexed mesh's
        # geometry regardless of vertex count.
        index_type=IndexType.UINT32,
        usage=buffer_usage,
        primitive=primitive,
    )


def generate_quad(width=1.0, height=1.0):
    """Generates a quad mesh centered at the origin, facing +Z."""
    hw = width / 2.0
    hh = height / 2.0

    vertices = np.array(
        [
            -hw,
            -hh,
            0.0,  # Bottom left
            hw,
            -hh,
            0.0,  # Bottom right
            -hw,
            hh,
            0.0,  # Top right
            hw,
            hh,
            0.0,  # Top left
        ],
        dtype=np.float32,
    )

    uvs = np.array(
        [
            1.0,
            0.0,  # Bottom left
            0.0,
            0.0,  # Bottom right
            1.0,
            1.0,  # Top right
            0.0,
            1.0,  # Top left
        ],
        dtype=np.float32,
    )

    normals = np.array(
        [0.0, 0.0, 1.0] * 4,
        dtype=np.float32,
    )

    indices = np.array(
        [
            0,
            1,
            2,
            2,
            1,
            3,
        ],
        dtype=np.uint32,
    )

    return create_static_mesh(vertices, uvs, normals, indices)


def generate_circle(radius=0.5, segments=32):
    """Generates a filled circle mesh (a triangle fan around a center
    vertex), facing +Z."""
    vertices = [0.0, 0.0, 0.0]  # center
    normals = [0.0, 0.0, 1.0]  # facing +Z
    uvs = [0.5, 0.5]  # center UV
    indices = []

    for i in range(segments + 1):  # +1 to close the loop
        angle = 2 * np.pi * i / segments
        x = np.cos(angle) * radius
        y = np.sin(angle) * radius
        vertices.extend([x, y, 0.0])
        normals.extend([0.0, 0.0, 1.0])
        u = (x / (2 * radius)) + 0.5
        v = (y / (2 * radius)) + 0.5
        uvs.extend([u, v])
        if i > 0:
            indices.extend([0, i, i + 1])

    return create_static_mesh(
        verticies=np.array(vertices, dtype=np.float32),
        normals=np.array(normals, dtype=np.float32),
        uvs=np.array(uvs, dtype=np.float32),
        indices=np.array(indices, dtype=np.uint32),
    )


def generate_polygon(local_vertices):
    """Generates a filled convex polygon mesh (a triangle fan around the
    vertices' own centroid), facing +Z - for debug-visualizing a
    PolygonCollisionShape, whose `local_vertices` (a list of
    `(x, y)`-like pairs) this takes directly."""
    xs = [v[0] for v in local_vertices]
    ys = [v[1] for v in local_vertices]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    max_extent = max(max(abs(x - cx), abs(y - cy)) for x, y in zip(xs, ys)) or 1.0

    vertices = [cx, cy, 0.0]
    normals = [0.0, 0.0, 1.0]
    uvs = [0.5, 0.5]
    indices = []

    n = len(local_vertices)
    for i in range(n + 1):  # +1 to close the loop
        x, y = local_vertices[i % n]
        vertices.extend([x, y, 0.0])
        normals.extend([0.0, 0.0, 1.0])
        uvs.extend([((x - cx) / (2 * max_extent)) + 0.5, ((y - cy) / (2 * max_extent)) + 0.5])
        if i > 0:
            indices.extend([0, i, i + 1])

    return create_static_mesh(
        verticies=np.array(vertices, dtype=np.float32),
        normals=np.array(normals, dtype=np.float32),
        uvs=np.array(uvs, dtype=np.float32),
        indices=np.array(indices, dtype=np.uint32),
    )


def generate_cube(width: float = 1.0, height: float = 1.0, depth: float = 1.0):
    """Generates an axis-aligned box mesh centered at the origin, with
    unshared per-face vertices so each face gets its own flat UVs/normal."""
    hw = width / 2.0
    hh = height / 2.0
    hd = depth / 2.0
    positions = [
        [-hw, -hh, -hd],
        [hw, -hh, -hd],
        [hw, hh, -hd],
        [-hw, hh, -hd],
        [-hw, -hh, hd],
        [hw, -hh, hd],
        [hw, hh, hd],
        [-hw, hh, hd],
    ]
    vertices = np.array(
        [
            # Front face
            *positions[4],
            *positions[5],
            *positions[6],
            *positions[4],
            *positions[6],
            *positions[7],
            # Back face
            *positions[1],
            *positions[0],
            *positions[3],
            *positions[1],
            *positions[3],
            *positions[2],
            # Left face
            *positions[0],
            *positions[4],
            *positions[7],
            *positions[0],
            *positions[7],
            *positions[3],
            # Right face
            *positions[5],
            *positions[1],
            *positions[2],
            *positions[5],
            *positions[2],
            *positions[6],
            # Top face
            *positions[3],
            *positions[7],
            *positions[6],
            *positions[3],
            *positions[6],
            *positions[2],
            # Bottom face
            *positions[0],
            *positions[1],
            *positions[5],
            *positions[0],
            *positions[5],
            *positions[4],
        ],
        dtype=np.float32,
    )
    uvs = np.array(
        [
            0.0,
            0.0,
            1.0,
            0.0,
            1.0,
            1.0,
            0.0,
            0.0,
            1.0,
            1.0,
            0.0,
            1.0,
        ]
        * 6,
        dtype=np.float32,
    )
    normals_per_face = [
        [0.0, 0.0, 1.0],  # Front
        [0.0, 0.0, -1.0],  # Back
        [-1.0, 0.0, 0.0],  # Left
        [1.0, 0.0, 0.0],  # Right
        [0.0, 1.0, 0.0],  # Top
        [0.0, -1.0, 0.0],  # Bottom
    ]
    normals = (
        np.array(normals_per_face * 6, dtype=np.float32).repeat(6, axis=0).flatten()
    )
    indices = np.array([i for i in range(36)], dtype=np.uint32)
    return create_static_mesh(vertices, normals, uvs, indices)


def generate_sphere(radius=1.0, sectors=36, stacks=18):
    """Generates a UV sphere mesh."""
    vertices = []
    normals = []
    uvs = []
    indices = []

    for i in range(stacks + 1):
        stack_angle = np.pi / 2 - i * np.pi / stacks  # from pi/2 to -pi/2
        xy = radius * np.cos(stack_angle)
        z = radius * np.sin(stack_angle)
        for j in range(sectors + 1):
            sector_angle = j * 2 * np.pi / sectors  # 0 to 2pi
            x = xy * np.cos(sector_angle)
            y = xy * np.sin(sector_angle)
            vertices.extend([x, y, z])
            nx, ny, nz = x / radius, y / radius, z / radius
            normals.extend([nx, ny, nz])
            u = j / sectors
            v = i / stacks
            uvs.extend([u, v])

    for i in range(stacks):
        for j in range(sectors):
            first = i * (sectors + 1) + j
            second = first + sectors + 1
            indices.extend([first, second, first + 1])
            indices.extend([second, second + 1, first + 1])

    return create_static_mesh(
        vertices=np.array(vertices, dtype=np.float32),
        normals=np.array(normals, dtype=np.float32),
        uvs=np.array(uvs, dtype=np.float32),
        indices=np.array(indices, dtype=np.uint32),
    )


def generate_sphere(radius=1.0, sectors=36, stacks=18):
    """Generates a UV sphere mesh."""
    vertices = []
    normals = []
    uvs = []
    indices = []

    for i in range(stacks + 1):
        stack_angle = np.pi / 2 - i * np.pi / stacks  # from pi/2 to -pi/2
        xy = radius * np.cos(stack_angle)
        z = radius * np.sin(stack_angle)
        for j in range(sectors + 1):
            sector_angle = j * 2 * np.pi / sectors  # 0 to 2pi
            x = xy * np.cos(sector_angle)
            y = xy * np.sin(sector_angle)
            vertices.extend([x, y, z])
            nx, ny, nz = x / radius, y / radius, z / radius
            normals.extend([nx, ny, nz])
            u = j / sectors
            v = i / stacks
            uvs.extend([u, v])

    for i in range(stacks):
        for j in range(sectors):
            first = i * (sectors + 1) + j
            second = first + sectors + 1
            indices.extend([first, second, first + 1])
            indices.extend([second, second + 1, first + 1])

    return create_static_mesh(
        vertices=np.array(vertices, dtype=np.float32),
        normals=np.array(normals, dtype=np.float32),
        uvs=np.array(uvs, dtype=np.float32),
        indices=np.array(indices, dtype=np.uint32),
    )


def __str__(self):
    return str(self.vertices)


def __repr__(self):
    return str(self)
