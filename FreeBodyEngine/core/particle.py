from FreeBodyEngine.core.node import Node2D, Node3D
from FreeBodyEngine.math import Vector, Vector3
from dataclasses import dataclass
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.texture import Texture, TextureStack
from FreeBodyEngine.core.timer import Timer
import numpy as np
from FreeBodyEngine import delta
import random


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
    :param spawn_cooldown: The cooldown between particle spawns.
    :type spawn_cooldown: float
    :param max_particles: The maximum amount of particles that can exist at any time.
    :type max_particles: int
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
    spawn_cooldown: float = 0.1
    
    max_particles: int = 100
    
    acceleration_min: Vector = Vector()
    acceleration_max: Vector = Vector(1, 1)

    color: Color = None
    texture: Texture = None
    texture_stack: TextureStack = None

PARTICLE_DTYPE = np.dtype(
    [
        ("pos", np.float32, (2,)),
        ("vel", np.float32, (2,)),
        ("lifetime", np.float32),
        ("active", np.bool_),
    ]
)

class ParticleEmmiter(Node2D):
    """Spawns and simulates a pool of particles on a fixed-size, struct-of-arrays NumPy buffer (`self.particles`, dtype PARTICLE_DTYPE) rather than one object per particle, so large particle counts stay cheap."""
    def __init__(
        self,
        position: Vector = Vector(),
        rotation: float = 1,
        scale: Vector = Vector(),
        particle_settings: ParticleSettings = ParticleSettings()
    ):
        """Allocates the fixed-size particle buffer (sized to `particle_settings.max_particles`) and starts the spawn cooldown timer.

        `free_list` tracks which slots in `self.particles` are unused - a
        spawn pops a slot from it, and a particle's death pushes its slot
        back on, so the buffer never needs to grow or shrink.
        """
        super().__init__(position, rotation, scale)
        self.particle_settings: ParticleSettings = particle_settings
        self.particles = np.zeros(particle_settings.max_particles, dtype=PARTICLE_DTYPE)
        
        self.spawn_timer = Timer(self.particle_settings.spawn_cooldown)
        self.spawn_timer.activate()

        self.active = np.zeros(self.particle_settings.max_particles, dtype=bool)
        self.free_list = list(range(self.particle_settings.max_particles))

        self._active = True

    def activate(self):
        """Resumes spawning and simulating particles."""
        self._active = True

    def deactivate(self):
        """Stops spawning and simulating particles (on_update() becomes a no-op) - existing particles are left as they are, not cleared."""
        self._active = False

    def _spawn(self):
        self.particles
        if not self.free_list:
            return None
        
        idx = self.free_list.pop()
        self.particles['pos'][idx] = [self.world_transform.position.x, self.world_transform.position.y]
        
        vx = random.uniform(self.particle_settings.velocity_min.x,self.particle_settings.velocity_max.x)
        vy = random.uniform(self.particle_settings.velocity_min.y, self.particle_settings.velocity_max.y)
        self.particles['vel'][idx] = [vx, vy]

        self.particles['lifetime'][idx] = self.particle_settings.lifetime
        self.particle['active'][idx] = True
        return idx

    def on_update(self):
        """While active, spawns a new particle whenever the spawn cooldown completes, ages and moves all currently-alive particles, and recycles any whose lifetime has run out back onto `free_list`."""
        if self._active:
            self.spawn_timer.update()

            if self.spawn_timer.complete:
                self._spawn()
                self.spawn_timer.activate()

            
            self.particles['lifetime'][self.particles['active']] -= delta()

            alive_mask = self.particles['active']
            alive = self.particles[alive_mask]

            accel_x = random.uniform(self.particle_settings.acceleration_min.x, self.particle_settings.acceleration_max.x)
            accel_y = random.uniform(self.particle_settings.acceleration_min.y, self.particle_settings.acceleration_max.y)

            alive['vel'][0] += accel_x
            alive['vel'][1] += accel_y

            alive['pos'][0] += alive['vel'][0]
            alive['pos'][1] += alive['vel'][1]

            dead = np.where((self.particles['lifetime'] <= 0) & self.particles['active'])[0]

            if dead.size > 0:
                self.particles['active'][dead] = False
                self.free_list.extend(dead.tolist())
