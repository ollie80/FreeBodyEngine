"""Light node types for PBRPipeline's deferred lighting composite pass (see
graphics/pbr/pipeline.py). These are PBRPipeline-specific, not a core engine
concept - a different GraphicsPipeline is free to have no lighting model at
all, or a completely different one, so this deliberately lives under
graphics/pbr rather than core.

A `Light` is always paired with a `Node2D` or `Node3D` base, the same mixin
pattern `core/camera.py`'s `Camera` uses -
`PointLight2D`/`DirectionalLight2D`/`SpotLight2D` for 2D scenes,
`PointLight3D`/`DirectionalLight3D`/`SpotLight3D` for 3D ones. Both flavors
feed the same per-pixel lighting math in the composite shader (see
engine_assets/shader/lighting_composite.fbfrag) - a 2D light is just a 3D
light whose node happens to live in a `Node2D` tree, placed at a nominal
world-space Z height so falloff/direction math isn't degenerate at z=0.

Shadows: `cast_shadows` is honored today only for `DirectionalLight3D` (a
real orthographic shadow map - see PBRPipeline._render_shadow_maps()). It's
accepted on every other light type but is currently a no-op there - 2D
shadow casting needs its own visibility/radial-map technique rather than a
repurposed 3D depth map (sprites are coplanar with the camera's view plane,
so there's no "above" for a light to look down from the way a 3D directional
light can); that's tracked as separate follow-up work, not implemented here.
Point/spot shadow maps (3D) are also left for follow-up - they need a
cubemap or paraboloid map rather than DirectionalLight3D's single ortho map.
"""
import math
from enum import Enum, auto

from FreeBodyEngine.core.node import Node2D, Node3D
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.math import Vector, Vector3


class LightType(Enum):
    """Which falloff/direction model a light uses in the composite pass."""
    POINT = auto()
    DIRECTIONAL = auto()
    SPOT = auto()


def _pitch_yaw_roll_to_forward(rotation: Vector3) -> Vector3:
    """Converts a pitch/yaw/roll rotation (degrees) into a world-space
    forward direction. Deliberately duplicates Camera3D._update_view_matrix's
    rotation-matrix construction (core/camera.py) rather than routing
    through Transform3.model, since Transform3.model's rotation submatrix is
    a separately-flagged, not-yet-fixed bug (same class of issue the 2D
    Transform.model rotation direction had before this session's fix) - this
    keeps a light's "facing" convention matching the camera's own, proven
    convention exactly."""
    pitch = math.radians(rotation.x)
    yaw = math.radians(rotation.y)
    roll = math.radians(rotation.z)

    cx, sx = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cz, sz = math.cos(roll), math.sin(roll)

    m00 = cy * cz + sx * sy * sz
    m01 = cz * sx * sy - cy * sz
    m02 = cx * sy
    m10 = cx * sz
    m11 = cx * cz
    m12 = -sx
    m20 = cy * sx * sz - cz * sy
    m21 = cy * cz * sx + sy * sz
    m22 = cx * cy

    # Local forward is -Z (OpenGL/camera convention).
    fx, fy, fz = 0.0, 0.0, -1.0
    return Vector3(
        m00 * fx + m01 * fy + m02 * fz,
        m10 * fx + m11 * fy + m12 * fz,
        m20 * fx + m21 * fy + m22 * fz,
    ).normalized


class Light:
    """Mixin holding the color/intensity/falloff/shadow state shared by
    every light node - never used on its own, always alongside a Node2D or
    Node3D base (see the concrete classes below)."""
    def __init__(self, light_type: LightType, color: Color, intensity: float,
                 range: float, spot_angle: float, cast_shadows: bool):
        """Stores this light's shading parameters.

        :param light_type: POINT/DIRECTIONAL/SPOT - selects the falloff
            model the composite pass uses for this light.
        :param color: The light's color.
        :param intensity: A brightness multiplier on top of `color`.
        :param range: For POINT/SPOT, the world-space distance at which this
            light's contribution reaches zero. Unused for DIRECTIONAL.
        :param spot_angle: For SPOT, the half-angle (degrees) of the cone.
            Unused otherwise.
        :param cast_shadows: Whether this light should cast real-time
            shadows - see the module docstring for which light types
            actually honor this today.
        """
        self.light_type = light_type
        self.color = color
        self.intensity = intensity
        self.range = range
        self.spot_angle = spot_angle
        self.cast_shadows = cast_shadows
        self.enabled = True


class PointLight2D(Node2D, Light):
    """A 2D point light - radiates outward from a world-space point with
    distance falloff out to `range`, no shadows (see module docstring)."""
    def __init__(self, position: Vector = Vector(), z: float = 0.5,
                 color: Color = Color("#FFFFFFFF"), intensity: float = 1.0,
                 range: float = 6.0):
        """`z` places this light a nominal height above the 2D scene's own
        Z=0 plane, purely so falloff distance isn't computed against a
        light sitting exactly in the same plane as everything it lights."""
        Node2D.__init__(self, position=position)
        Light.__init__(self, LightType.POINT, color, intensity, range, 0.0, False)
        self.z = z

    @property
    def world_position3(self) -> Vector3:
        """This light's world position as a Vector3, for the composite
        pass's shared 3D lighting math."""
        p = self.world_position
        return Vector3(p.x, p.y, self.z)


class DirectionalLight2D(Node2D, Light):
    """A 2D 'sun' light - shines from a fixed direction across the whole
    scene rather than from a point. `rotation` (inherited from Node2D)
    controls that direction in the XY plane; `z` gives it a small downward
    component so it lights flat 2D geometry's surface normal rather than
    grazing it edge-on. No shadows (see module docstring)."""
    def __init__(self, rotation: float = 45.0, z: float = 5.0,
                 color: Color = Color("#FFFFFFFF"), intensity: float = 1.0):
        Node2D.__init__(self, rotation=rotation)
        Light.__init__(self, LightType.DIRECTIONAL, color, intensity, 0.0, 0.0, False)
        self.z = z

    @property
    def direction3(self) -> Vector3:
        """World-space direction this light shines *toward*."""
        d = Vector(0, -1).rotated(self.world_rotation)
        return Vector3(d.x, d.y, -self.z).normalized


class SpotLight2D(Node2D, Light):
    """A 2D spot light - a point light restricted to a cone facing
    `rotation`. No shadows (see module docstring)."""
    def __init__(self, position: Vector = Vector(), rotation: float = 0.0,
                 z: float = 0.5, color: Color = Color("#FFFFFFFF"),
                 intensity: float = 1.0, range: float = 6.0,
                 spot_angle: float = 30.0):
        Node2D.__init__(self, position=position, rotation=rotation)
        Light.__init__(self, LightType.SPOT, color, intensity, range, spot_angle, False)
        self.z = z

    @property
    def world_position3(self) -> Vector3:
        p = self.world_position
        return Vector3(p.x, p.y, self.z)

    @property
    def direction3(self) -> Vector3:
        d = Vector(0, -1).rotated(self.world_rotation)
        return Vector3(d.x, d.y, 0.0).normalized


class PointLight3D(Node3D, Light):
    """A 3D point light - radiates outward from a world-space point with
    distance falloff out to `range`. Shadows not yet implemented for point
    lights (needs a cubemap/paraboloid map - see module docstring)."""
    def __init__(self, position: Vector3 = Vector3(), color: Color = Color("#FFFFFFFF"),
                 intensity: float = 1.0, range: float = 8.0, cast_shadows: bool = False):
        Node3D.__init__(self, position=position)
        Light.__init__(self, LightType.POINT, color, intensity, range, 0.0, cast_shadows)

    @property
    def world_position3(self) -> Vector3:
        """This light's world position - named to match PointLight2D/
        SpotLight2D's `world_position3` so PBRPipeline can read any light's
        position the same way regardless of whether it's 2D or 3D."""
        return self.world_transform.position


class DirectionalLight3D(Node3D, Light):
    """A 3D 'sun' light - shines uniformly from a fixed direction across the
    whole scene. This is the one light type with a real shadow
    implementation today: with `cast_shadows=True`, PBRPipeline renders a
    single orthographic depth map from this light's direction each frame
    and samples it in the composite pass (see
    PBRPipeline._render_shadow_maps())."""
    def __init__(self, rotation: Vector3 = Vector3(-45.0, 45.0, 0.0),
                 color: Color = Color("#FFFFFFFF"), intensity: float = 1.0,
                 cast_shadows: bool = False,
                 shadow_extent: float = 20.0, shadow_distance: float = 30.0):
        """`shadow_extent` is the half-width of the orthographic shadow
        frustum (world units) and `shadow_distance` is how far back along
        `-direction3` the shadow camera is placed before looking at the
        scene origin - both only matter when `cast_shadows` is True."""
        Node3D.__init__(self, rotation=rotation)
        Light.__init__(self, LightType.DIRECTIONAL, color, intensity, 0.0, 0.0, cast_shadows)
        self.shadow_extent = shadow_extent
        self.shadow_distance = shadow_distance

    @property
    def direction3(self) -> Vector3:
        """World-space direction this light shines *toward*."""
        return _pitch_yaw_roll_to_forward(self.world_transform.rotation)


class SpotLight3D(Node3D, Light):
    """A 3D spot light - a point light restricted to a cone facing this
    node's rotation. Shadows not yet implemented for spot lights (see
    module docstring)."""
    def __init__(self, position: Vector3 = Vector3(), rotation: Vector3 = Vector3(),
                 color: Color = Color("#FFFFFFFF"), intensity: float = 1.0,
                 range: float = 8.0, spot_angle: float = 30.0, cast_shadows: bool = False):
        Node3D.__init__(self, position=position, rotation=rotation)
        Light.__init__(self, LightType.SPOT, color, intensity, range, spot_angle, cast_shadows)

    @property
    def world_position3(self) -> Vector3:
        """This light's world position - see PointLight3D.world_position3."""
        return self.world_transform.position

    @property
    def direction3(self) -> Vector3:
        """World-space direction this light shines *toward*."""
        return _pitch_yaw_roll_to_forward(self.world_transform.rotation)
