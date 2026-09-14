import numpy
import FreeBodyEngine as engine
from typing import Iterable, overload, Union, Sequence
from abc import ABC, abstractmethod

import math

class GenericVector:
    """
    Only used for typing, not actual logic.
    """
    x: float
    y: float

VECTOR_LIKE = Union[GenericVector, float, Sequence[float]]

def simplify_fraction(numerator, denominator):
    """Reduces a fraction to lowest terms, normalizing the sign so a
    negative result always carries its sign on the numerator.

    Raises:
        ValueError: If `denominator` is zero.
    """
    if denominator == 0:
        raise ValueError("Denominator cannot be zero.")

    gcd = math.gcd(numerator, denominator)
    simplified_numerator = numerator // gcd
    simplified_denominator = denominator // gcd

    if simplified_denominator < 0:
        simplified_numerator *= -1
        simplified_denominator *= -1

    return simplified_numerator, simplified_denominator

def bezier_point(curve, t):
    """De Casteljau's algorithm to evaluate a Bezier curve."""
    while len(curve) > 1:
        curve = [(1 - t) * curve[i] + t * curve[i + 1] for i in range(len(curve) - 1)]
    return curve[0]

def vector_towards(start: 'Vector', to: 'Vector', magnitude):
    """Returns a vector pointing from `start` towards `to`, scaled to
    `magnitude` rather than the actual distance between them."""
    relx = to.x - start.x
    rely = to.y - start.y
    angle = math.atan2(rely, relx)

    return Vector((magnitude) * math.cos(angle), (magnitude) * math.sin(angle))

def is_even(x):
    """Returns whether `x` is an even number."""
    return x % 2 == 0

def clamp(min, value, max):
    """Restricts `value` to the `[min, max]` range."""
    if value < min:
        return min
    if value > max:
        return max
    return value

def clamp_vector(min, value, max):
    """Componentwise `clamp()`: clamps `value`'s x and y independently
    against `min` and `max`'s corresponding components."""
    return Vector(clamp(min.x, value.x, max.x), clamp(min.y, value.y, max.y))

def vector_is_close(value1, value2, max):
    """Returns whether `value1` and `value2` are within `max` of each other
    on both axes (`math.isclose` with `abs_tol=max`, applied per component)."""
    if math.isclose(value1.x, value2.x, abs_tol=max) and math.isclose(
        value1.y, value2.y, abs_tol=max
    ):
        return True

    return False

def gaussian_random(rng: numpy.random.RandomState, mean=0, standard_deveation=1):
    """Draws a single normally-distributed random value via the Box-Muller
    transform, using `rng` instead of the `random`/`numpy.random` globals so
    callers can get reproducible sequences from a seeded generator."""
    u = 1 - rng.random()
    v = rng.random()
    z = math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    return z * standard_deveation + mean

class GenericRotation:
    """Placeholder for a future rotation representation shared between 2D
    and 3D transforms; not yet implemented or used anywhere."""
    pass

class Rotation():
    """Placeholder for a future rotation representation; not yet
    implemented or used anywhere."""
    pass

class Transform:
    """A 2D position/rotation/scale triple, with `rotation` a single scalar
    angle (degrees) around Z rather than a full rotation object."""
    def __init__(self, position: VECTOR_LIKE, rotation: float, scale: VECTOR_LIKE):
        """`position` and `scale` are coerced through `Vector(...)`, so any
        `VECTOR_LIKE` value (a vector, scalar, or 2-sequence) works."""
        self.position = Vector(position)
        self.rotation = rotation
        self.scale = Vector(scale)

    def copy(self):
        """Returns an independent copy of this transform."""
        return Transform(self.position.copy(), self.rotation, self.scale.copy())

    def neg(self):
        """Returns a new transform with position, rotation and scale all
        negated."""
        return Transform(-self.position, -self.rotation, -self.scale)

    @property
    def model(self) -> numpy.ndarray:
        """Builds this transform's 4x4 model matrix (scale @ rotation @
        translation, as a row-vector affine matrix)."""
        px = self.position.x
        py = self.position.y

        sx = self.scale.x
        sy = self.scale.y

        rz = self.rotation  # assume scalar float for now, rotation around Z

        rz_rad = math.radians(rz)

        cos_r = math.cos(rz_rad)
        sin_r = math.sin(rz_rad)

        scale = numpy.array([
            [sx, 0,  0,  0],
            [0,  sy, 0,  0],
            [0,  0,  1, 0],
            [0,  0,  0,  1]
        ], dtype=float)

        # Transposed from the "usual" [[cos,-sin],[sin,cos]] column-vector
        # rotation matrix on purpose: this matrix is used in row-vector
        # convention (v @ M, per this method's own docstring), where that
        # form actually rotates *clockwise* for a positive angle - the
        # opposite of every other rotation in the engine (Vector.rotated(),
        # RectangleCollisionShape's corners, the whole physics/joints/IK
        # system), all of which treat positive degrees as counter-
        # clockwise. Confirmed via SpiderArena: a leg segment's rendered
        # mesh rotated the opposite way from its own joint anchors,
        # visibly not lining up between its hip/knee markers even though
        # the joints themselves (and the markers, being circles, rotation-
        # invariant in appearance) were positioned correctly.
        rotation = numpy.array([
            [cos_r,  sin_r, 0, 0],
            [-sin_r, cos_r, 0, 0],
            [0,      0,     1, 0],
            [0,      0,     0, 1]
        ], dtype=float)

        translation = numpy.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [px, py, 0, 1]
        ], dtype=float)

        # Same fix as Transform3.model below (verified against RaytraceDemo
        # for 3D): in row-vector convention (v @ M), `translation @ rotation
        # @ scale` transforms a point as `((v @ translation) @ rotation) @
        # scale` - translating FIRST means the translation offset itself
        # then gets rotated/scaled too, which is wrong (a model matrix
        # should scale, then rotate, then translate last, leaving the
        # translation itself untouched by the other two). Confirmed via
        # SpiderArena (a from-scratch 2D physics demo): any rotated child
        # node (i.e. nearly everything in a physics-driven scene) rendered
        # at a wildly wrong screen position - e.g. a body-part 10 degrees
        # from level, offset half a unit from its parent, rendered over 2
        # units away from its actual position - before this fix.
        return scale @ rotation @ translation

    def __eq__(self, other):
        if isinstance(other, Transform):
            return (self.position == other.position and
                    self.rotation == other.rotation and
                    self.scale == other.scale)
    
    def __add__(self, other):
        if isinstance(other, Transform):
            return Transform(self.position + other.position, self.rotation + other.rotation, self.scale + other.scale)

    def __iadd__(self, other):
        if isinstance(other, Transform):
            self.position += other.position
            self.rotation += other.rotation
            self.scale += other.scale
            return self
    
    def __sub__(self, other):
        if isinstance(other, Transform):
            return Transform(self.position - other.position, self.rotation - other.rotation, self.scale - other.scale)

    def __isub__(self, other):
        if isinstance(other, Transform):
            self.position -= other.position
            self.rotation -= other.rotation
            self.scale -= other.scale
            return self

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Transform(self.position * other,
                            self.rotation * other,
                            self.scale * other)
        elif isinstance(other, Transform):
            return Transform(self.position * other.position,
                            self.rotation + other.rotation,
                            self.scale * other.scale)
        elif isinstance(other, Vector):
            return Transform(self.position * other, self.rotation * other.magnitude, self.scale * other)

        raise TypeError("Transform can only be multiplied by a scalar or another Transform")

    def __imul__(self, other):
        if isinstance(other, (int, float)):
            self.position *= other
            self.rotation *= other
            self.scale *= other
            return self
        elif isinstance(other, Transform):
            self.position *= other.position
            self.rotation += other.rotation
            self.scale *= other.scale
            return self
        elif isinstance(other, Vector):
            self.position *= other
            self.rotation *= other.magnitude
            self.scale *= other
            return self

        raise TypeError("Transform can only be multiplied by a scalar or another Transform")

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return Transform(self.position / other,
                            self.rotation / other,
                            self.scale / other)
        elif isinstance(other, Transform):
            return Transform(self.position / other.position,
                            self.rotation / other.rotation,
                            self.scale / other.scale)
        elif isinstance(other, Vector):
            return Transform(self.position / other, self.rotation / other.magnitude, self.scale / other)

        raise TypeError("Transform can only be divided by a scalar or another Transform")

    def __itruediv__(self, other):
        if isinstance(other, (int, float)):
            self.position /= other
            self.rotation /= other
            self.scale /= other
            return self
        elif isinstance(other, Transform):
            self.position /= other.position
            self.rotation -= other.rotation
            self.scale /= other.scale
            return self
        
        elif isinstance(other, Vector):
            self.position /= other
            self.rotation /= other.magnitude
            self.scale /= other
            return self

        raise TypeError("Transform can only be divided by a scalar, vector or another Transform")

    def to_matrix(self):
        """Builds this transform's 3x3 2D affine matrix (column-vector
        convention: `[[cos*sx, -sin*sy, px], [sin*sx, cos*sy, py], [0, 0, 1]]`),
        used by `compose_with`/`from_matrix` for parent-child composition -
        distinct from `model`, which builds a 4x4 matrix in the row-vector
        convention the renderer expects."""
        cos_r = math.cos(math.radians(self.rotation))
        sin_r = math.sin(math.radians(self.rotation))

        sx, sy = self.scale.x, self.scale.y
        px, py = self.position.x, self.position.y

        return numpy.array(
            [[cos_r * sx, -sin_r * sy, px],
            [sin_r * sx,  cos_r * sy, py],
            [0,           0,          1]])
        
    def compose_with(self, parent_transform: 'Transform') -> 'Transform':
        """Combines this (local) transform with `parent_transform` to get
        the equivalent world transform, via 3x3 matrix multiplication
        rather than combining position/rotation/scale directly - this is
        what lets `Node2D.world_transform` account for a rotated or scaled
        parent's effect on a child's position."""
        parent_mat = parent_transform.to_matrix()
        local_mat = self.to_matrix()
        result_mat = parent_mat @ local_mat
        return Transform.from_matrix(result_mat)

    @classmethod
    def from_matrix(cls, mat: numpy.ndarray) -> 'Transform':
        """Decomposes a 3x3 affine matrix (as produced by `to_matrix`) back
        into a `Transform`'s position/rotation/scale.

        Raises:
            ValueError: If the matrix's extracted scale is zero on either
                axis, since rotation can't be recovered from it then.
        """
        assert mat.shape == (3, 3), "Matrix must be 3x3 for 2D transforms"

        # Extract translation (position)
        px = mat[0, 2]
        py = mat[1, 2]

        # Extract scale from matrix columns
        sx = math.hypot(mat[0, 0], mat[1, 0])
        sy = math.hypot(mat[0, 1], mat[1, 1])

        # Prevent division by Z
        if sx == 0 or sy == 0:
            raise ValueError("Cannot extract rotation from zero scale")

        # Extract rotation (in radians)
        rot_rad = math.atan2(mat[1, 0] / sx, mat[0, 0] / sx)
        rotation = math.degrees(rot_rad)

        return cls((px, py), rotation, (sx, sy))

class Transform3:
    """A 3D position/rotation/scale triple, with `rotation` a `Vector3` of
    Euler angles (degrees, applied Z then Y then X - see `model`)."""
    def __init__(self, position: 'Vector3', rotation: 'Vector3', scale: 'Vector3'):
        """`position`, `rotation` and `scale` are each coerced through
        `Vector3(...)`."""
        self.position = Vector3(position)
        self.rotation = Vector3(rotation)
        self.scale = Vector3(scale)

    def copy(self):
        """Returns an independent copy of this transform."""
        return Transform3(self.position.copy(), self.rotation.copy(), self.scale.copy())

    def neg(self):
        """Returns a new transform with position, rotation and scale all
        negated."""
        return Transform3(-self.position, -self.rotation, -self.scale)

    @property
    def model(self) -> numpy.ndarray:
        """Builds this transform's 4x4 model matrix, as `scale @ rotation @
        translation` (row-vector convention) so a locally-authored mesh is
        scaled and rotated about its own origin before being placed in the
        world - see the note below on why the factor order matters here."""
        tx, ty, tz = self.position
        sx, sy, sz = self.scale
        rx, ry, rz = map(math.radians, self.rotation)

        cosx, sinx = math.cos(rx), math.sin(rx)
        cosy, siny = math.cos(ry), math.sin(ry)
        cosz, sinz = math.cos(rz), math.sin(rz)

        rot_x = numpy.array([
            [1,     0,      0,     0],
            [0,   cosx,  -sinx,   0],
            [0,   sinx,   cosx,   0],
            [0,     0,      0,     1]
        ])

        rot_y = numpy.array([
            [cosy,  0, siny, 0],
            [0,     1,   0,  0],
            [-siny, 0, cosy, 0],
            [0,     0,   0,  1]
        ])

        rot_z = numpy.array([
            [cosz, -sinz, 0, 0],
            [sinz,  cosz, 0, 0],
            [0,       0,  1, 0],
            [0,       0,  0, 1]
        ])

        scale = numpy.diag([sx, sy, sz, 1])

        translation = numpy.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [tx, ty, tz, 1]
        ], dtype=float)

        rotation = rot_z @ rot_y @ rot_x

        # `translation`'s translation components live in its last ROW (a
        # row-vector affine matrix: v' = v @ M), so composing left-to-right
        # as `translation @ rotation @ scale` applies translation *first*
        # and scale *last* to any point run through this matrix - meaning
        # scale then also multiplies the translation itself (a Model3D at
        # position (2, 0, 0) with scale 8 ended up at world (16, 0, 0), not
        # (2, 0, 0)). Scale-then-rotate-then-translate (the standard TRS
        # order for placing a locally-authored mesh in the world) needs the
        # matrix factors in the opposite order: `scale @ rotation @
        # translation`.
        return scale @ rotation @ translation


    def __eq__(self, other):
        return (isinstance(other, Transform3) and
                self.position == other.position and
                self.rotation == other.rotation and
                self.scale == other.scale)

    def __add__(self, other):
        if isinstance(other, Transform3):
            return Transform3(self.position + other.position,
                              self.rotation + other.rotation,
                              self.scale + other.scale)

    def __iadd__(self, other):
        if isinstance(other, Transform3):
            self.position += other.position
            self.rotation += other.rotation
            self.scale += other.scale
            return self

    def __sub__(self, other):
        if isinstance(other, Transform3):
            return Transform3(self.position - other.position,
                              self.rotation - other.rotation,
                              self.scale - other.scale)

    def __isub__(self, other):
        if isinstance(other, Transform3):
            self.position -= other.position
            self.rotation -= other.rotation
            self.scale -= other.scale
            return self

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Transform3(self.position * other,
                              self.rotation * other,
                              self.scale * other)
        elif isinstance(other, Transform3):
            return Transform3(self.position * other.position,
                              self.rotation + other.rotation,
                              self.scale * other.scale)
        raise TypeError("Transform3 can only be multiplied by a scalar or another Transform3")

    def __imul__(self, other):
        if isinstance(other, (int, float)):
            self.position *= other
            self.rotation *= other
            self.scale *= other
            return self
        elif isinstance(other, Transform3):
            self.position *= other.position
            self.rotation += other.rotation
            self.scale *= other.scale
            return self
        raise TypeError("Transform3 can only be multiplied by a scalar or another Transform3")

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return Transform3(self.position / other,
                              self.rotation / other,
                              self.scale / other)
        elif isinstance(other, Transform3):
            return Transform3(self.position / other.position,
                              self.rotation - other.rotation,
                              self.scale / other.scale)
        raise TypeError("Transform3 can only be divided by a scalar or another Transform3")

    def __itruediv__(self, other):
        if isinstance(other, (int, float)):
            self.position /= other
            self.rotation /= other
            self.scale /= other
            return self
        elif isinstance(other, Transform3):
            self.position /= other.position
            self.rotation -= other.rotation
            self.scale /= other.scale
            return self
        raise TypeError("Transform3 can only be divided by a scalar or another Transform3")

class Vector(GenericVector):
    """A 2D float vector, also used throughout the engine as a generic
    (x, y) pair (e.g. sizes, UV coordinates). Constructible from separate
    x/y values, a single scalar (broadcast to both axes), a 2-element
    sequence, or another `Vector` - see the `__init__` overloads."""
    @overload
    def __init__(self) -> None:
        """Overload signature for a default-constructed vector: `Vector()` defaults to `(0, 0)`."""
        ...
    @overload
    def __init__(self, x: float) -> None:
        """Overload signature for a single scalar broadcast to both axes: `Vector(s)` -> `(s, s)`."""
        ...
    @overload
    def __init__(self, x: float, y: float) -> None:
        """Overload signature for explicit x/y values: `Vector(x, y)`."""
        ...
    @overload
    def __init__(self, x: Sequence[float]) -> None:
        """Overload signature for building from a 2-element sequence: `Vector([x, y])`."""
        ...
    @overload
    def __init__(self, x: 'Vector') -> None:
        """Overload signature for copying another `Vector`."""
        ...

    def __init__(self, x: Union[float, Sequence[float], GenericVector] = 0, y: float = None):
        """Builds a vector from another `Vector`, a 2-element sequence, an
        explicit `(x, y)` pair, or a single scalar broadcast to both axes
        (`Vector()` defaults to `(0, 0)`)."""
        if isinstance(x, Vector):
            self.x, self.y = x.x, x.y
        elif isinstance(x, Sequence):
            self.x, self.y = x[0], x[1]
        elif y is not None:
            self.x, self.y = x, y
        else:
            self.x, self.y = x, x

    @classmethod
    def from_angle(self, angle: float) -> 'Vector':
        """Returns a unit vector pointing at `angle` radians."""
        return Vector(math.cos(angle), math.sin(angle))

    def __getitem__(self, index):
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        else:
            raise IndexError("Vector index out of range")

    def __setitem__(self, index, value):
        if index == 0:
            self.x = value
        elif index == 1:
            self.y = value
        else:
            raise IndexError("Vector index out of range")

    def copy(self) -> 'Vector':
        """Returns an independent copy of this vector."""
        return Vector(self.x, self.y)

    def __hash__(self):
        return hash((self.x, self.y))

    def __neg__(self):
        return Vector(-self.x, -self.y)


    def __iadd__(self, other):
        if isinstance(other, Vector):
            self.x += other.x
            self.y += other.y
            return self
        elif isinstance(other, (float, int)):
            self.x += other
            self.y += other
            return self

    def cross(self, other: "Vector") -> float:
        """Returns the 2D cross product (the scalar z-component of the 3D
        cross product), whose sign indicates whether `other` is clockwise
        or counter-clockwise from this vector."""
        return self.x * other.y - self.y * other.x

    def dot(self, other: "Vector") -> float:
        """Returns the dot product of this vector and `other`."""
        return self.x * other.x + self.y * other.y

    def perpendicular(self) -> "Vector":
        """Returns this vector rotated 90 degrees counter-clockwise."""
        return Vector(-self.y, self.x)

    def __add__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x + other.x, self.y + other.y)
        if isinstance(other, (int, float)):
            return Vector(self.x + other, self.y + other)

    def __isub__(self, other):
        if isinstance(other, Vector):
            self.x -= other.x
            self.y -= other.y
            return self
        elif isinstance(other, (float, int)):
            self.x -= other
            self.y -= other
            return self

    def __eq__(self, other):
        return isinstance(other, Vector) and self.x == other.x and self.y == other.y

    def __sub__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x - other.x, self.y - other.y)
        if isinstance(other, (int, float)):
            return Vector(self.x - other, self.y - other)

    def __imul__(self, other):
        if isinstance(other, Vector):
            self.x *= other.x
            self.y *= other.y
            return self
        elif isinstance(other, (float, int)):
            self.x *= other
            self.y *= other
            return self

    def __mul__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x * other.x, self.y * other.y)
        if isinstance(other, (int, float)):
            return Vector(self.x * other, self.y * other)

    def __itruediv__(self, other):
        if isinstance(other, Vector):
            self.x /= other.x
            self.y /= other.y
            return self
        elif isinstance(other, (float, int)):
            self.x /= other
            self.y /= other
            return self

    def __truediv__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x / other.x, self.y / other.y)
        if isinstance(other, (int, float)):
            return Vector(self.x / other, self.y / other)

    @property
    def magnitude(self):
        """This vector's length."""
        return math.sqrt(self.x**2 + self.y**2)

    @property
    def normalized(self):
        """This vector scaled to length 1, or `(0, 0)` if it's already the
        zero vector (rather than raising a divide-by-zero error)."""
        mag = self.magnitude
        if mag == 0:
            return Vector(0, 0)  # Or raise an error
        return Vector(self.x / mag, self.y / mag)

    def distance(self, to: 'Vector'):
        """Returns the Euclidean distance between this point and `to`."""
        return (self - to).magnitude

    def rotated(self, degrees: float) -> 'Vector':
        """Returns this vector rotated counter-clockwise by `degrees` around
        the origin - for rotating a local offset (e.g. a joint anchor or a
        polygon vertex) by a body's rotation into world space."""
        rad = math.radians(degrees)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        return Vector(self.x * cos_r - self.y * sin_r, self.x * sin_r + self.y * cos_r)

    def __iter__(self):
        return iter((self.x, self.y))  # returns an iterator over a tuple

    def __repr__(self):
        return f"[{self.x}, {self.y}]"

class Vector3:
    """A 3D float vector."""
    def __init__(self, x=0.0, y=None, z=None):
        """Builds a vector from another `Vector3`, a 3-element list/tuple,
        explicit `(x, y, z)` values, or a single scalar broadcast to all
        three axes (`Vector3()` defaults to `(0, 0, 0)`)."""
        if isinstance(x, (int, float)):
            self.x = x
            if y == None:
                self.y = x
            else:
                self.y = y
            if z == None:
                self.z = x
            else:
                self.z = z
        elif isinstance(x, Vector3):
            self.x, self.y, self.z = x.x, x.y, x.z
        elif isinstance(x, (list, tuple)) and len(x) == 3:
            self.x, self.y, self.z = x
        else:
            self.x, self.y, self.z = float(x), float(y), float(z)

    def __getitem__(self, index) -> int:
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        elif index == 2:
            return self.z
        else:
            raise IndexError("Vector3 index out of range")

    def __setitem__(self, index, value):
        if index == 0:
            self.x = value
        elif index == 1:
            self.y = value
        elif index == 2:
            self.z = value
        else:
            raise IndexError("Vector3 index out of range")

    def copy(self):
        """Returns an independent copy of this vector."""
        return Vector3(self.x, self.y, self.z)

    def __add__(self, other):
        if isinstance(other, Vector3):
            return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)
        raise TypeError("Can only add Vector3 to Vector3")

    def __sub__(self, other):
        if isinstance(other, Vector3):
            return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)
        raise TypeError("Can only subtract Vector3 from Vector3")

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Vector3(self.x * other, self.y * other, self.z * other)
        if isinstance(other, Vector3):
            return Vector3(self.x * other.x, self.y * other.y, self.z * other.z)
        raise TypeError("Can multiply Vector3 by scalar or Vector3")

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return Vector3(self.x / other, self.y / other, self.z / other)
        if isinstance(other, Vector3):
            return Vector3(self.x / other.x, self.y / other.y, self.z / other.z)
        raise TypeError("Can divide Vector3 by scalar or Vector3")

    def __repr__(self):
        return f"Vector3({self.x}, {self.y}, {self.z})"
    
    def __iter__(self):
        return iter((self.x, self.y, self.z))

class Curve(ABC):
    """Base class for easing curves: given a progress value `x` (typically
    0-1), maps it to an eased output value used to interpolate animations."""
    @abstractmethod
    def get_value(self, x):
        """Evaluates the curve at `x`."""
        pass

class Linear(Curve):
    """No easing - output equals input, capped at 1."""
    def get_value(self, x):
        """See class docstring."""
        return min(1, x)

class EaseInOut(Curve):
    """Smoothstep-style ease in and out (cubic Hermite interpolation),
    capped at 1."""
    def get_value(self, x):
        """See class docstring."""
        return min(1, (x * x) * (3 - (2 * x)))

class EaseInOutExpo(Curve):
    """Exponential ease in and out, clamped to `[0, 1]`."""
    def get_value(self, x: float) -> float:
        """See class docstring."""
        return min(
            max(
                (2 ** (20 * x - 10)) / 2 if x < 0.5 else (2 - 2 ** (-20 * x + 10)) / 2,
                0,
            ),
            1,
        )

class EaseInOutSin(Curve):
    """Sine-based ease in and out, capped at 1."""
    def get_value(self, x):
        """See class docstring."""
        return min(1, math.sin(x * 1.5))

class EaseInOutCircular(Curve):
    """Circular ease in and out (based on the unit circle equation)."""
    def get_value(self, x):
        """See class docstring."""
        return (
            (1 - math.sqrt(1 - (2 * x) ** 2)) / 2
            if x < 0.5
            else (math.sqrt(1 - (-2 * x + 2) ** 2) + 1) / 2
        )

class EaseOutSin(Curve):
    """Sine-based ease out, capped at 1."""
    def get_value(self, x):
        """See class docstring."""
        return min(math.sin((0.5 * x) * math.pi), 1)

class BounceOut(Curve):
    """Ease out with a bouncing overshoot at the end, made of four
    quadratic segments (a standard "bounce" easing formula)."""
    def get_value(self, x):
        """See class docstring."""
        n1, d1 = 7.5625, 2.75
        return (
            n1 * x * x
            if x < 1 / d1
            else n1 * (x - 1.5 / d1) * (x - 1.5 / d1) + 0.75
            if x < 2 / d1
            else n1 * (x - 2.25 / d1) * (x - 2.25 / d1) + 0.9375
            if x < 2.5 / d1
            else n1 * (x - 2.625 / d1) * (x - 2.625 / d1) + 0.984375
        )
