from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine import get_service, warning
import numpy as np
from enum import Enum, auto


class AttributeType(Enum):
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
    TRIANGLES = auto()
    TRIANGLE_STRIP = auto()
    TRIANGLE_FAN = auto()


class IndexType(Enum):
    UINT16 = auto()
    UINT32 = auto()


class BufferUsage(Enum):
    STATIC = auto()
    DYNAMIC = auto()
    STREAM = auto()


class Mesh:
    def __init__(
        self,
        attributes: dict[str, tuple[AttributeType, np.ndarray]],
        indices: np.ndarray = None,
        primitive: PrimitiveType = PrimitiveType.TRIANGLES,
        index_type: IndexType = IndexType.UINT16,
        usage: BufferUsage = BufferUsage.STATIC,
    ):

        self.attributes = attributes
        self.indices = indices
        self.primitive = primitive
        self.index_type = index_type
        self.usage = usage

    @abstractmethod
    def destroy(self):
        pass

    @abstractmethod
    def _set_attribute_data(self, attribute_name: str, data: np.ndarray):
        pass

    def set_data(self, attribute_name: str, data: np.ndarray):
        if self.usage == BufferUsage.STATIC:
            warning("Cannot set data of a static Mesh.")
            return
        self._set_attribute_data(attribute_name, data)

    @abstractmethod
    def draw(self):
        pass


def create_static_mesh(
    verticies: np.ndarray,
    uvs: np.ndarray,
    normals: np.ndarray,
    indices: np.ndarray,
    buffer_usage: BufferUsage = BufferUsage.STATIC,
    primitive: PrimitiveType = PrimitiveType.TRIANGLES,
) -> Mesh:
    return get_service("renderer").get_mesh_class()(
        {
            "verticies": (AttributeType.VEC3, verticies),
            "uvs": (AttributeType.VEC2, uvs),
            "normals": (AttributeType.VEC3, normals),
        },
        indices=indices,
        usage=buffer_usage,
        primitive=primitive,
    )


def generate_quad(width=1.0, height=1.0):
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
        [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0],
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

    return create_static_mesh(vertices, normals, uvs, indices)


def generate_circle(radius=0.5, segments=32):
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
        vertices=np.array(vertices, dtype=np.float32),
        normals=np.array(normals, dtype=np.float32),
        uvs=np.array(uvs, dtype=np.float32),
        indices=np.array(indices, dtype=np.uint32),
    )


def generate_cube(width: float = 1.0, height: float = 1.0, depth: float = 1.0):
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
