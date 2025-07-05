from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.core.node import Node2D
from FreeBodyEngine.math import Vector
import numpy as np
import math
import time
from enum import Enum, auto

class CAMERA_PROJECTION(Enum):
    PERSPECTIVE = auto()
    ORTHOGRAPHIC = auto()

class Camera2D(Node2D):
    """
    A generic camera object. The camera doesn't draw anything, its only purpose is to provide matricies to the renderer.
    
    :param position: The world position of the camera.
    :type position: vector
    
    :param zoom: The zoom of the camera. The larger the zoom value, the larger the image.
    :type zoom: float
    
    :param rotation: The rotation of the camera around the Z axis.
    :type rotation: float

    :param background_color: The color that the background of the screen will be set to.
    :type background_color: Color
    """

    def __init__(self, position: 'Vector' = Vector(), zoom: float = 250, rotation: float = 0, projection=CAMERA_PROJECTION.ORTHOGRAPHIC, background_color: Color = Color("#324848")):
        super().__init__(position, rotation)
        
        self.zoom = zoom
        self.background_color = background_color
        self.projection = projection

    def _update_rect(self):
        center_x, center_y = self.transform.position.x, self.transform.position.y
        width, height = (
            self.scene.main.window.size[0] / self.zoom,
            self.scene.main.window.size[1] / self.zoom,
        )

    def _update_projection_matrix(self):
        self._update_rect()
        width = self.scene.main.window.size[0]
        height = self.scene.main.window.size[1]
        aspect = width / height if height != 0 else 1.0
        near = 0.1
        far = 100.0

        if self.projection == CAMERA_PROJECTION.PERSPECTIVE:
            fov_deg = 60.0
            fov_rad = math.radians(fov_deg)
            f = 1.0 / math.tan(fov_rad / 2.0)

            proj_matrix = np.array([
                [f / aspect, 0.0, 0.0, 0.0],
                [0.0, f, 0.0, 0.0],
                [0.0, 0.0, (far + near) / (near - far), (2 * far * near) / (near - far)],
                [0.0, 0.0, -1.0, 0.0],
            ], dtype=np.float32)

        elif self.projection == CAMERA_PROJECTION.ORTHOGRAPHIC:
            left = -width / 2
            right = width / 2
            bottom = -height / 2
            top = height / 2

            proj_matrix = np.array([
                [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
                [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
                [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
                [0.0, 0.0, 0.0, 1.0],
            ], dtype=np.float32)

        scale_matrix = np.array([
            [self.zoom, 0.0, 0.0, 0.0],
            [0.0, self.zoom, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float32)

        self.proj_matrix = np.dot(proj_matrix, scale_matrix)

    def _update_view_matrix(self):
        tx, ty = -self.transform.position.x, self.transform.position.y
        translation_matrix = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [tx, ty, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        # rotation around Z-Axis
        angle = math.radians(self.transform.rotation)
        cos_theta = math.cos(angle)
        sin_theta = math.sin(angle)

        rotation_matrix = np.array(
            [
                [cos_theta, -sin_theta, 0.0, 0.0],
                [sin_theta, cos_theta, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )



        # Combine translation and rotation
        self.view_matrix = np.dot(translation_matrix, rotation_matrix)

    def update(self):
        super().update()
        self._update_projection_matrix()
        self._update_view_matrix()
