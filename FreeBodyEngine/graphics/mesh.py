from FreeBodyEngine.utils import abstractmethod
import numpy as np


class Mesh:
    """
    Mesh class. 
    """
    def __init__(self, vertices: np.ndarray, normals: np.ndarray, uvs: np.ndarray, indices: np.ndarray):
        self.vertices = vertices
        self.normals = normals
        self.uvs = uvs
        self.indices = indices
    
    @abstractmethod
    def destroy(self):
        pass

    @abstractmethod
    def draw(self):
        """Must be called before drawing."""
        pass

    @classmethod
    def generate_quad(cls, width = 1.0, height = 1.0):
        """Generates a simple quadrilateral mesh."""
        hw = width / 2.0
        hh = height / 2.0

        vertices = np.array([
            -hw, -hh, 0.0,  # Bottom left
             hw, -hh, 0.0,  # Bottom right
            -hw,  hh, 0.0,  # Top right
             hw,  hh, 0.0  # Top left
        ], dtype=np.float32)

        uvs = np.array([
            1.0, 0.0,  # Bottom left
            0.0, 0.0,  # Bottom right
            1.0, 1.0,  # Top right
            0.0, 1.0,  # Top left
        ], dtype=np.float32)
        
        normals = np.array([
            0.0, 0.0, 1.0,  # Facing out of the screen
            0.0, 0.0, 1.0,
            0.0, 0.0, 1.0,
            0.0, 0.0, 1.0,
        ], dtype=np.float32)

        indices = np.array([
            0, 1, 2,
            2, 1, 3,
        ], dtype=np.uint32)

        return cls(vertices, normals, uvs, indices)
        
    @classmethod
    def generate_cube():
        pass
    
    @classmethod
    def generate_sphere(cls, radius=1.0, sectors=36, stacks=18):
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

        return cls(
            vertices=np.array(vertices, dtype=np.float32),
            normals=np.array(normals, dtype=np.float32),
            uvs=np.array(uvs, dtype=np.float32),
            indices=np.array(indices, dtype=np.uint32)
        )
