from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.core.node import Node2D, Node3D
from FreeBodyEngine.math import Vector, Vector3
import numpy as np
import math
import time
from enum import Enum, auto
from FreeBodyEngine import get_service

class CAMERA_PROJECTION(Enum):
    """The two projection modes a `Camera` can use to build its projection
    matrix."""
    PERSPECTIVE = auto()
    ORTHOGRAPHIC = auto()


class Camera:
    """Mixin holding the projection/background/matrix state shared by
    `Camera2D` and `Camera3D` - always used alongside a `Node2D`/`Node3D`
    base (see those classes), never on its own."""
    def __init__(self, projection: CAMERA_PROJECTION, background_color: Color, zoom: float):
        """Stores the camera's settings and sets `view_matrix`/`proj_matrix`
        to identity until the first matrix update runs."""
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

    def __init__(self, position: 'Vector' = Vector(), zoom: float = 250, rotation: float = 0, projection=CAMERA_PROJECTION.ORTHOGRAPHIC, background_color: Color = Color("#060e08")):
        """Initializes both the `Node2D` and `Camera` halves of this
        object, since `Camera2D` doesn't use a single cooperative
        `super().__init__()` chain."""
        Node2D.__init__(self, position=position, rotation=rotation)
        Camera.__init__(self, projection=projection, background_color=background_color, zoom=zoom)

    def on_initialize(self):
        """Builds the initial projection and view matrices once the camera
        is attached to the scene tree (and so has a `world_transform`)."""
        self._update_projection_matrix()
        self._update_view_matrix()

    def _update_projection_matrix(self):
        width = get_service('window').size[0]
        height = get_service('window').size[1]
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
            [0.0, 0.0, self.zoom, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float32)

        self.proj_matrix = scale_matrix @ proj_matrix 

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
        # Both axes must be negated here - the view matrix has to move the
        # world opposite to the camera's own position (a camera that moves
        # +y should make the world appear to shift -y on screen). `tx` did
        # this correctly but `ty` didn't, which put every 2D scene's
        # vertical placement off by roughly 2x the camera's own y position
        # (e.g. a camera at y=1.6 looking at a point at y=0.3 rendered it
        # as if it were at y=1.6-(-1.3) instead of y=0.3-1.6) - increasingly
        # wrong the further the camera sits from y=0. _get_view_mat() above
        # (unused elsewhere, but presumably the intended reference) already
        # negates both axes.
        tx, ty = -self.world_transform.position.x, -self.world_transform.position.y
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
        """Updates the node tree as usual, then rebuilds both matrices
        every frame so the camera tracks window resizes and its own
        movement/rotation/zoom without needing an explicit invalidation."""
        super().update()
        self._update_projection_matrix()
        self._update_view_matrix()

class Camera3D(Node3D, Camera):
    """A 3D counterpart to `Camera2D`."""
    def __init__(self, position: 'Vector' = Vector3(), rotation: 'Vector' = Vector3(), zoom: float = 1.0, projection=CAMERA_PROJECTION.PERSPECTIVE, background_color: Color = Color("#324848")):
        """Initializes both the `Node3D` and `Camera` halves of this
        object, since `Camera3D` doesn't use a single cooperative
        `super().__init__()` chain."""
        Node3D.__init__(self, position=position, rotation=rotation)
        Camera.__init__(self, projection=projection, background_color=background_color, zoom=zoom)

    def on_initialize(self):
        """Builds the initial projection and view matrices once the camera
        is attached to the scene tree (and so has a `world_transform`)."""
        self._update_projection_matrix()
        self._update_view_matrix()

    def _get_view_mat(self):
        return self.view_matrix

    def _update_projection_matrix(self):
        width = get_service('window').size[0]
        height = get_service('window').size[1]
        aspect = width / height if height != 0 else 1.0
        near = 1.0
        far = 100.0

        if self.projection == CAMERA_PROJECTION.PERSPECTIVE:
            fov_deg = 60.0
            fov_rad = math.radians(fov_deg)
            f = 1.0 / math.tan(fov_rad / 2.0)

            self.proj_matrix = np.array([
                [f / aspect, 0.0, 0.0, 0.0],
                [0.0, f, 0.0, 0.0],
                [0.0, 0.0, (far + near) / (near - far), (2 * far * near) / (near - far)],
                [0.0, 0.0, -1.0, 0.0],
            ], dtype=np.float32)

        elif self.projection == CAMERA_PROJECTION.ORTHOGRAPHIC:
            half_width = width / 2.0
            half_height = height / 2.0

            left = -half_width
            right = half_width
            bottom = -half_height
            top = half_height

            self.proj_matrix = np.array([
                [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
                [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
                [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
                [0.0, 0.0, 0.0, 1.0],
            ], dtype=np.float32)
            
    def _update_view_matrix(self):
        pos = self.world_transform.position
        rot = self.world_transform.rotation

        pitch = math.radians(rot.x)
        yaw = math.radians(rot.y)
        roll = math.radians(rot.z)

        cx, sx = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cz, sz = math.cos(roll), math.sin(roll)

        rotation_matrix = np.array([
            [cy * cz + sx * sy * sz, cz * sx * sy - cy * sz, cx * sy, 0.0],
            [cx * sz, cx * cz, -sx, 0.0],
            [cy * sx * sz - cz * sy, cy * cz * sx + sy * sz, cx * cy, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float32)

        translation_matrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [pos.x, pos.y, pos.z, 1]
        ], dtype=np.float32)

        camera_world_matrix = translation_matrix @ rotation_matrix
        self.view_matrix = np.linalg.inv(camera_world_matrix)

    def update(self):
        """Updates the node tree as usual, then rebuilds both matrices
        every frame so the camera tracks window resizes and its own
        movement/rotation/zoom without needing an explicit invalidation."""
        super().update()
        self._update_projection_matrix()
        self._update_view_matrix()
