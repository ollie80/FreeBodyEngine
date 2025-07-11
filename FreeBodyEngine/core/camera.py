from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.core.node import Node2D, Node3D
from FreeBodyEngine.math import Vector, Vector3
import numpy as np
import math
import time
from enum import Enum, auto

class CAMERA_PROJECTION(Enum):
    PERSPECTIVE = auto()
    ORTHOGRAPHIC = auto()


class Camera:
    def __init__(self, projection: CAMERA_PROJECTION, background_color: Color, zoom: float):
        self.zoom = zoom
        self.background_color = background_color
        self.projection = projection
        self.view_matrix: np.ndarray = np.identity(4, np.float32)
        self.proj_matrix: np.ndarray = np.identity(4, np.float32)

class Camera2D(Node2D, Camera):
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
        Node2D.__init__(self, position=position, rotation=rotation)
        Camera.__init__(self, projection=projection, background_color=background_color, zoom=zoom)

    
    def on_initialize(self):
        self._update_projection_matrix()
        self._update_view_matrix()


    def _update_projection_matrix(self):
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

    def _get_view_mat(self):
        tx, ty = -self.world_transform.position.x, self.world_transform.position.y
        translation_matrix = np.array(
            [
                [1.0, 0.0, 0.0, tx],
                [0.0, 1.0, 0.0, -ty],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        # rotation around z axis
        angle = math.radians(self.world_transform.rotation)
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

        return np.dot(translation_matrix, rotation_matrix)


    def _update_view_matrix(self):
        tx, ty = -self.world_transform.position.x, self.world_transform.position.y
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
        angle = math.radians(self.world_transform.rotation)
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

        self.view_matrix = np.dot(translation_matrix, rotation_matrix)

    def update(self):
        super().update()
        self._update_projection_matrix()
        self._update_view_matrix()


class Camera3D(Node3D, Camera):
    def __init__(self, position: 'Vector' = Vector3(), rotation: 'Vector' = Vector3(), zoom: float = 1.0, projection=CAMERA_PROJECTION.ORTHOGRAPHIC, background_color: Color = Color("#324848")):
        Node3D.__init__(self, position=position, rotation=rotation)
        Camera.__init__(self, projection=projection, background_color=background_color, zoom=zoom)

    def on_initialize(self):
        self._update_projection_matrix()
        self._update_view_matrix()

    def _update_projection_matrix(self):
        width = self.scene.main.window.size[0]
        height = self.scene.main.window.size[1]
        aspect = width / height if height != 0 else 1.0
        near = 0.1
        far = 1000.0  # larger far plane

        if self.projection == CAMERA_PROJECTION.PERSPECTIVE:
            fov_deg = 60.0
            fov_rad = math.radians(fov_deg)
            f = 1.0 / math.tan(fov_rad / 2.0)
            
            self.proj_matrix = np.array([
                [f / aspect, 0.0,  0.0,                              0.0],
                [0.0,        f,    0.0,                              0.0],
                [0.0,        0.0, (far + near) / (near - far), (2 * far * near) / (near - far)],
                [0.0,        0.0, -1.0,                              0.0],
            ], dtype=np.float32)


        elif self.projection == CAMERA_PROJECTION.ORTHOGRAPHIC:
            scale = self.zoom
            left = -width / 2 * scale
            right = width / 2 * scale
            bottom = -height / 2 * scale
            top = height / 2 * scale

            self.proj_matrix = np.array([
                [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
                [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
                [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
                [0.0, 0.0, 0.0, 1.0],
            ], dtype=np.float32)

    def _update_view_matrix(self):
        pos = self.world_transform.position
        rot = self.world_transform.rotation  # assumed to be Vector(pitch, yaw, roll) in degrees

        # Convert rotation to radians
        pitch = math.radians(rot.x)
        yaw = math.radians(rot.y)
        roll = math.radians(rot.z)

        # Calculate rotation matrix (Yaw-Pitch-Roll)
        cx, sx = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cz, sz = math.cos(roll), math.sin(roll)

        # Combined rotation matrix (Rz * Rx * Ry)
        rotation_matrix = np.array([
            [cy * cz + sx * sy * sz, cz * sx * sy - cy * sz, cx * sy, 0.0],
            [cx * sz, cx * cz, -sx, 0.0],
            [cy * sx * sz - cz * sy, cy * cz * sx + sy * sz, cx * cy, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float32)

        # Translation matrix
        translation_matrix = np.identity(4, dtype=np.float32)
        translation_matrix[:3, 3] = -np.array([pos.x, pos.y, pos.z], dtype=np.float32)

        # View matrix = R⁻¹ * T⁻¹ == Rᵗ * -T (if R is orthonormal)
        self.view_matrix = rotation_matrix.T @ translation_matrix

    def update(self):
        super().update()
        self._update_projection_matrix()
        self._update_view_matrix()
