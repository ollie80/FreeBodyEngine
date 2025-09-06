from FreeBodyEngine.core.node import Node2D, Node3D
from FreeBodyEngine.math import Vector, Vector3
from dataclasses import dataclass
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.texture import Texture, TextureStack

@dataclass
class ParticleSettings:
    """
    The information that controlls the attributes of particle. Attributes with minimum and maximum values will be given a value between the max and min.
    
    :param velocity_min: The minimum initial velocity.
    :type velocity_min: Vector
    :param velocity_max: The maximum initial velocity.
    :type velocity_max: Vector
    :param lifetime: The time a particle will last for. A value of -1 will make it last forever.
    :type lifetime: float
    :param acceleration_min: The minimum acceleration.
    :type acceleration_min: Vector
    :param acceleration_max: The maximum acceleration.
    :type acceleration_max: Vector
    :param color: If color is set, the particle will use a flat color.
    :type color: Color
    :param texture: If texture is set, the particle will use the texture.
    :type texture: Texture
    :param texture_stack: If texture_stack is set, a random image in the stack will be used for each particle.
    :type texture_stack: TextureStack
    """
    velocity_min: Vector = Vector()
    velocity_max: Vector = Vector(1, 1)

    lifetime: float = -1.0

    acceleration_min: Vector = Vector()
    acceleration_max: Vector = Vector(1, 1)

    color: Color = None
    texture: Texture = None
    texture_stack: TextureStack = None


@dataclass
class Particle:
    def __init__(self):
        velocity: Vector
        acceleration: Vector

        lifetime: float

        useTexture: bool = False
        useTextureStack: bool = False
        useColor: bool = False

class ParticleEmmiter(Node2D):
    def __init__(self, position: Vector = Vector(), rotation: float = 1, scale: Vector = Vector(), particle_settings: ParticleSettings = ParticleSettings()):
        super().__init__(position, rotation, scale)
        self.particle_settings: ParticleSettings = particle_settings
        self.particles = []

    def spawn(self):
        