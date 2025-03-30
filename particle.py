import math
import pygame
from pygame import Vector2 as vector
import FreeBodyEngine as engine
from random import randint
import random

class Particle:
    def __init__(self, color: str, radius: int, lifespan: float, pos: vector, vel: vector, morph: int):
        self.color = color
        self.radius = radius
        self.max_radius = radius
        self.time_remaining = lifespan
        self.lifespan = lifespan

        self.morph = morph
        self.pos = pos
        self.vel = vel
    
    def grow_radius(self):
        time = self.time_remaining / self.lifespan
        return self.max_radius * -(math.cos(math.pi * time) - 1) / 2

    def shrink_radius(self):
        time = self.time_remaining / self.lifespan
        return self.max_radius * -(math.cos(math.pi * time) + 1) / 2

    def update(self, dt):
        self.pos = vector(self.pos.x + (self.vel.x * dt), self.pos.y + (self.vel.y * dt))
        if self.morph != 0:
            if self.morph == -1:
                self.radius = self.shrink_radius()
            else:
                self.radius = self.grow_radius()
        self.time_remaining  -= dt

class ParticleEmitter(engine.core.Entity):
    def __init__(self, pos: vector, size, spawn_rate: int, lifespan: int, color: str = 'black', 
                morph: int = 0, # -1 = shrink, 0 = none, 1 = grow
                max: int = 10, vert_min = -10, vert_max = 10,  hor_min = -10, hor_max = 10, tag="none"):
        
        super().__init__(pos, tag=tag)
        self.morph = morph
        self.particles = []
        self.spawn_timer = engine.core.Timer(spawn_rate)

        self.color = color
        self.lifespan = lifespan
        self.max = max

        self.size = size
        self.vert_max = vert_max
        self.vert_min = vert_min
        self.hor_max = hor_max
        self.hor_min = hor_min
        self.spawn_timer.activate()

    def spawn(self):
        self.particles.append(Particle(self.color, self.size, self.lifespan, self.position, vector(random.randrange(round(self.hor_min), round(self.hor_max)), random.randrange(round(self.vert_min), round(self.vert_max))), self.morph))
    
    def update(self, dt):
        self.spawn_timer.update(dt)
        if self.spawn_timer.complete == True and len(self.particles) < self.max:
            self.spawn()  
            self.spawn_timer.activate()

        for particle in self.particles:
            particle.update(dt)
            if particle.time_remaining <= 0:
                self.particles.remove(particle)

class CircleParticle(engine.core.Entity):
    def __init__(self, radius, max_radius, duration, curve, position, color="#FFFFFF"):
        self.radius = radius
        self.start_radius = radius
        self.max_radius = max_radius - self.radius
        self.duration = duration
        self.time_past = 0
        self.curve = curve
        self.color = color
        self.position = position
        self.surf = pygame.surface.Surface(vector(self.radius*2, self.radius*2))


    def update(self, dt):

        time_percentage: float = min(1, ((self.time_past) /  self.duration))
        if time_percentage == 1:
            self.kill()
        percentage = self.curve.get_value(time_percentage)

        if time_percentage == 1:
            self.kill()
            return
        
        self.radius = self.start_radius + (percentage * (abs(self.max_radius)))
        self.time_past += dt
        
        
        self.surf = pygame.surface.Surface(vector(self.radius*2, self.radius*2))
        self.surf.fill("#4a412a") # very ugly color
        draw_pos = (self.surf.size[0]/ 2, self.surf.size[1]/2)
        pygame.draw.circle(self.surf, self.color, draw_pos, self.radius)
        pygame.draw.circle(self.surf, "#4a412a", draw_pos, self.radius - 2)
        self.surf.set_colorkey("#4a412a")
        