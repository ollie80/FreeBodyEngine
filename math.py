import math
import numpy
import FreeBodyEngine as engine
from perlin_noise import PerlinNoise
from typing import Iterable, overload, Union, Sequence
from abc import ABC, abstractmethod

class GenericVector:
    """
    Only used for typing, not actual logic.
    """
    x: float
    y: float



VECTOR_LIKE = Union[GenericVector, float, Sequence[float]]

class LayeredNoise:
    def __init__(self, layers: int, seed: int, start_octaves: int = 3):
        self.noise_list: list[PerlinNoise] = []
        for i in range(layers):
            self.noise_list.append(PerlinNoise(start_octaves * (i + 1), seed))

    def noise(self, pos):
        noise_val = 0.0
        multiplier = 1
        for noise in self.noise_list:
            noise_val += noise.noise(pos) * multiplier
            multiplier *= 0.5
        return noise_val


def simplify_fraction(numerator, denominator):
    if denominator == 0:
        raise ValueError("Denominator cannot be zero.")

    gcd = math.gcd(numerator, denominator)
    simplified_numerator = numerator // gcd
    simplified_denominator = denominator // gcd

    # Ensure denominator is positive
    if simplified_denominator < 0:
        simplified_numerator *= -1
        simplified_denominator *= -1

    return simplified_numerator, simplified_denominator


def bezier_point(curve, t):
    """De Casteljau's algorithm to evaluate a Bezier curve."""
    while len(curve) > 1:
        curve = [(1 - t) * curve[i] + t * curve[i + 1] for i in range(len(curve) - 1)]
    return curve[0]  # The final point is the evaluated point at t


def vector_towards(start: 'Vector', to: 'Vector', magnitude):
    relx = to.x - start.x
    rely = to.y - start.y
    angle = math.atan2(rely, relx)

    return Vector((magnitude) * math.cos(angle), (magnitude) * math.sin(angle))


def is_even(x):
    return x % 2 == 0


def clamp(min, value, max):
    if value < min:
        return min
    if value > max:
        return max
    return value


def clamp_vector(min, value, max):
    return Vector(clamp(min.x, value.x, max.x), clamp(min.y, value.y, max.y))


def vector_is_close(value1, value2, max):
    if math.isclose(value1.x, value2.x, abs_tol=max) and math.isclose(
        value1.y, value2.y, abs_tol=max
    ):
        return True

    return False


def gaussian_random(rng: numpy.random.RandomState, mean=0, standard_deveation=1):
    u = 1 - rng.random()
    v = rng.random()
    z = math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    return z * standard_deveation + mean


class GenericRotation:
    pass

class Rotation():
    pass

class Transform:
    def __init__(self, position: VECTOR_LIKE, rotation: float, scale: VECTOR_LIKE):
        self.position = Vector(position)
        self.rotation = rotation
        self.scale = Vector(scale)

    def copy(self):
        return Transform(self.position.copy(), self.rotation, self.scale.copy())

    def neg(self):
        return Transform(-self.position, -self.rotation, -self.scale)
    
    def model(self) -> numpy.ndarray:
        px = self.position.x
        py = self.position.y
        pz = getattr(self.position, 'z', 0.0)

        sx = self.scale.x
        sy = self.scale.y
        sz = getattr(self.scale, 'z', 1.0)

        # Rotation in degrees; interpret as rotation about Z for 2D
        rz = self.rotation  # assume scalar float for now, rotation around Z

        # Convert to radians
        rz_rad = math.radians(rz)

        cos_r = math.cos(rz_rad)
        sin_r = math.sin(rz_rad)

        scale = numpy.array([
            [sx, 0,  0,  0],
            [0,  sy, 0,  0],
            [0,  0,  sz, 0],
            [0,  0,  0,  1]
        ], dtype=float)

        rotation = numpy.array([
            [cos_r, -sin_r, 0, 0],
            [sin_r,  cos_r, 0, 0],
            [0,      0,     1, 0],
            [0,      0,     0, 1]
        ], dtype=float)

        translation = numpy.array([
            [1, 0, 0, px],
            [0, 1, 0, py],
            [0, 0, 1, pz],
            [0, 0, 0, 1]
        ], dtype=float)

        return translation @ rotation @ scale
    
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
        raise TypeError("Transform can only be multiplied by a scalar or another Transform")

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return Transform(self.position / other,
                            self.rotation / other,
                            self.scale / other)
        elif isinstance(other, Transform):
            return Transform(self.position / other.position,
                            self.rotation - other.rotation,
                            self.scale / other.scale)
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
        raise TypeError("Transform can only be divided by a scalar or another Transform")

    def to_matrix(self):
        # Construct 2D affine transform matrix: T * R * S
        cos_r = math.cos(math.radians(self.rotation))
        sin_r = math.sin(math.radians(self.rotation))

        sx, sy = self.scale.x, self.scale.y
        px, py = self.position.x, self.position.y

        return [
            [cos_r * sx, -sin_r * sy, px],
            [sin_r * sx,  cos_r * sy, py],
            [0,           0,          1]
        ]


    def compose_with(self, parent_transform: 'Transform') -> 'Transform':
        # Apply parent transform to self (full matrix multiplication)
        parent_mat = parent_transform.to_matrix()
        local_mat = self.to_matrix()
        result_mat = multiply_matrices(parent_mat, local_mat) # type: ignore
        return Transform.from_matrix(result_mat)

class Vector(GenericVector):
    @overload
    def __init__(self) -> None: ...
    @overload
    def __init__(self, x: float) -> None: ...
    @overload
    def __init__(self, x: float, y: float) -> None: ...
    @overload
    def __init__(self, x: Sequence[float]) -> None: ...
    @overload
    def __init__(self, x: 'Vector') -> None: ...

    def __init__(self, x: Union[float, Sequence[float], GenericVector] = 0, y: float = None):
        if isinstance(x, Vector):
            self.x, self.y = x.x, x.y
        elif isinstance(x, Sequence):
            self.x, self.y = x[0], x[1]
        elif y is not None:
            self.x, self.y = x, y
        else:
            self.x, self.y = x, 0

    def __iadd__(self, other):
        if isinstance(other, Vector):
            self.x += other.x
            self.y += other.y
            return self
        elif isinstance(other, (float, int)):
            self.x += other
            self.y += other
            return self

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
        return math.sqrt(self.x**2 + self.y**2)

    @property
    def normalized(self):
        mag = self.magnitude
        if mag == 0:
            return Vector(0, 0)  # Or raise an error
        return Vector(self.x / mag, self.y / mag) 

    def distance(self, to: 'Vector'):
        return abs(self.magnitude - to.magnitude)

    def __iter__(self):
        return iter((self.x, self.y))  # returns an iterator over a tuple

    def __repr__(self):
        return f"[{self.x}, {self.y}]"

class Vector3:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, Vector3):
            self.x, self.y, self.z = x.x, x.y, x.z
        elif isinstance(x, (list, tuple)) and len(x) == 3:
            self.x, self.y, self.z = x
        else:
            self.x, self.y, self.z = float(x), float(y), float(z)

    def copy(self):
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


class Curve(ABC):
    """The generic curve function."""
    @abstractmethod
    def get_value(self, x):
        pass


class Linear(Curve):
    def get_value(self, x):
        return min(1, x)


class EaseInOut(Curve):
    def get_value(self, x):
        return min(1, (x * x) * (3 - (2 * x)))


class EaseInOutExpo(Curve):
    def get_value(self, x: float) -> float:
        return min(
            max(
                (2 ** (20 * x - 10)) / 2 if x < 0.5 else (2 - 2 ** (-20 * x + 10)) / 2,
                0,
            ),
            1,
        )


class EaseInOutSin(Curve):
    def get_value(self, x):
        return min(1, math.sin(x * 1.5))


class EaseInOutCircular(Curve):
    def get_value(self, x):
        return (
            (1 - math.sqrt(1 - (2 * x) ** 2)) / 2
            if x < 0.5
            else (math.sqrt(1 - (-2 * x + 2) ** 2) + 1) / 2
        )


class EaseOutSin(Curve):
    def get_value(self, x):
        return min(math.sin((0.5 * x) * math.pi), 1)


class BounceOut(Curve):
    def get_value(self, x):
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


