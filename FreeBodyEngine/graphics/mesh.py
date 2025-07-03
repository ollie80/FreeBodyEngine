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
            0.0, 0.0,  # Bottom left
            1.0, 0.0,  # Bottom right
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
    def generate_sphere():
        pass

