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

class Vector3(GenericVector):
    pass


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


def vector_towards(start: Vector, to: Vector, magnitude):
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

class Curve(ABC):
    """The generic curve function.w"""
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
