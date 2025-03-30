import math
from pygame import Vector2
import numpy
import engine
from perlin_noise import PerlinNoise

class LayeredNoise:
    def __init__(self, layers: int, seed: int, start_octaves: int = 3):
        self.noise_list: list[PerlinNoise] = []
        for i in range(layers):
            self.noise_list.append(PerlinNoise(start_octaves*(i + 1), seed))
        
    def noise(self, pos):
        noise_val = 0.0
        multiplier = 1
        for noise in self.noise_list:
            noise_val += noise.noise(pos) * multiplier
            multiplier *= 0.5
        return noise_val
            
def bezier_point(curve, t):
    """De Casteljau's algorithm to evaluate a Bezier curve."""
    while len(curve) > 1:
        curve = [(1 - t) * curve[i] + t * curve[i + 1] for i in range(len(curve) - 1)]
    return curve[0]  # The final point is the evaluated point at t


def vector_towards(start: Vector2, to: Vector2, magnitude):
    relx = to.x - start.x
    rely = to.y - start.y
    angle = math.atan2(rely, relx)
    
    return Vector2((magnitude) * math.cos(angle), (magnitude) * math.sin(angle))

def is_even(x):
    return x % 2 == 0


def clamp(min, value, max):
    if value < min: return min
    if value > max: return max
    return value

def clamp_vector(min, value, max):
    return Vector2(clamp(min.x, value.x, max.x), clamp(min.y, value.y, max.y))

def vector_is_close(value1, value2, max):

    if math.isclose(value1.x, value2.x, abs_tol=max) and math.isclose(value1.y, value2.y, abs_tol=max):
        return True
    
    return False

def gaussian_random(rng: numpy.random.RandomState, mean=0, standard_deveation=1):
    u = 1 - rng.random()
    v = rng.random()
    z = math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    return z * standard_deveation + mean

class Curve:
    def get_value(self, x):
        pass

class Linear(Curve):
    def get_value(self, x):
        return min(1, x)

class EaseInOut(Curve):
    def get_value(self, x):
        return min(1, (x*x)*(3-(2*x))) 
    
class EaseInOutExpo(Curve):
    def get_value(self, x: float) -> float:
        return min(max((2 ** (20 * x - 10)) / 2 if x < 0.5 else (2 - 2 ** (-20 * x + 10)) / 2, 0), 1)

class EaseInOutSin(Curve):
    def get_value(self, x):
        return min(1, math.sin(x*1.5))
    
class EaseInOutCircular(Curve):
    def get_value(self, x):
        return (1 - math.sqrt(1 - (2 * x) ** 2)) / 2 if x < 0.5 else (math.sqrt(1 - (-2 * x + 2) ** 2) + 1) / 2

class EaseOutSin(Curve):
    def get_value(self, x):
        return (math.sin((0.5*x)*math.pi))

class BounceOut(Curve):
    def get_value(self, x):
        n1, d1 = 7.5625, 2.75
        return (
            n1 * x * x if x < 1 / d1 else
            n1 * (x - 1.5 / d1) * (x - 1.5 / d1) + 0.75 if x < 2 / d1 else
            n1 * (x - 2.25 / d1) * (x - 2.25 / d1) + 0.9375 if x < 2.5 / d1 else
            n1 * (x - 2.625 / d1) * (x - 2.625 / d1) + 0.984375
        )
    
