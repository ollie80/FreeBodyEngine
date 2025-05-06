from dataclasses import dataclass
import moderngl
import pygame
import math
import json

import OpenGL.GL as GL
import numpy as np
import threading

import moderngl

import FreeBodyEngine as engine
import FreeBodyEngine.math.math

import random 
from sys import exit
from abc import abstractmethod
from typing import Literal
from pygame.math import Vector2 as vector


class Timer:
    def __init__(self, duration):
        self.duration = duration
        self.time_remaining = self.duration
        self.active = False
        self.complete = False

    def activate(self):
        self.active = True
        self.complete = False
        self.time_remaining = self.duration

    def deactivate(self):
        self.active = False
        self.time_remaining = 0

    def update(self, dt):
        if self.active:
            self.time_remaining -= dt
        if self.time_remaining <= 0:
            self.deactivate()
            self.complete = True

class Component:
    def __init__(self, name: str, entity: "engine.core.Entity"):
        self.name = str
        self.entity = entity
    
    def remove(self):
        pass

    def update(self, dt):
        pass

class Transform:
    """
    Basic 2D transform object.
    """
    def __init__(self, position: vector = vector(0, 0), rotation: int = 0, scale: vector = vector(0, 0)):
        super().__init__()
        self.position = position
        self.rotation = rotation
        self.scale = scale


class ColliderShape:
    def __init__(self):
        pass

    def get_bounds(self):
        pass

    def check_collision(self, other):
        pass

class Collider(Component):
    """
    The collider component. Requires a Collider Shape.
    """
    def __init__(self, name: str, entity: "engine.core.Entity", shape: "ColliderShape", collision_type: str = "passive"):
        super().__init__(name, entity)
        self.collision_type = "passive"
        self.shape = shape



    def update(self, dt):
        self.check_collisions()


# A drawn entity with basics physics 
class Actor(engine.core.Entity):
    def __init__(self, pos: vector, scene, name: str, size: vector = vector(32, 32), collision_type="passive"):
        super().__init__(pos, scene, size)
        self.name = name
        
        #physics
        self.vel = vector(0, 0)
        self.friction = 100

        self.collision_type = collision_type
        self.rect = pygame.FRect(self.position.x, self.position.y, size.x, size.y)
        self.image: None | engine.graphics.Image = None 

    def on_collision(self, other: "Actor"):
        pass

    def integrate_forces(self, dt):

        # Update position
        self.position += self.vel

        # Get velocity in polar coordinates
        pol = self.vel.as_polar()
        pol_magnitude = pol[0]

        direction_deg = pol[1]
        direction_rad = math.radians(direction_deg)

        # Apply friction
        magnitude = max(0, pol_magnitude - (self.friction * dt))
        
        # Convert back to Cartesian coordinates
        self.vel = pygame.math.Vector2(
            magnitude * math.cos(direction_rad),
            magnitude * math.sin(direction_rad)
        )
        


    def check_collisions(self, dt):
        for actor in (e for e in self.scene.entities if isinstance(e, Actor)):
            if actor != self and actor.rect.colliderect(self.rect):
                self.resolve_collision(actor)

    def resolve_collision(self, other: "Actor"):
        if self.collision_type == "active":
            dx = min(self.rect.right - other.rect.left, other.rect.right - self.rect.left)
            dy = min(self.rect.bottom - other.rect.top, other.rect.bottom - self.rect.top)
            # Push out in the direction of least penetration
            if dx < dy:
                if self.center.x < other.center.x:
                    self.position.x = other.rect.left - (self.size[0])  # Push left
                else:
                    self.position.x = other.rect.right # Push right
            else:
                if self.center.y < other.center.y:
                    self.position.y = other.rect.top - (self.size[1])  # Push up
                else:
                    self.position.y = other.rect.bottom # Push down
            self.on_collision(other)
        
        if self.collision_type == "fixed":
            self.on_collision(other)

        if self.collision_type == "passive":
            self.on_collision(other)

    def on_draw(self):
        if self.image:
            self.image.center = self.center
            self.scene.graphics.add_general(self.image)

    def update(self, dt):
        self.on_update(dt)
        
        for component in self.components:
            component.update(dt)

        self.integrate_forces(dt)
        self.rect.topleft = self.position
        self.check_collisions(dt)

        
        if self.image:
            self.image.update(dt)
        
        self.on_post_update()

class Fire(Component):
    def __init__(self, entity):
        super().__init__(entity)
        self.emmiters: list[engine.particle.ParticleEmitter] = []
        size = 8
        #particle = engine.particle.ParticleEmitter(self.entity.center, 3 * size, 0.02, 0.5, max=25 * size,  hor_min=-20 * size, hor_max=20 * size, vert_min=-50 * size, vert_max=-49 * size, color='#171426')
        #self.entity.scene.add(particle)
        #self.emmiters.append(particle)

        particle = engine.particle.ParticleEmitter(self.entity.center, 2 * size, 0.06, 0.5, max=25 * size,  hor_min=-10 * size, hor_max=10 * size, vert_min=-40 * size, vert_max=-15 * size, color='#3d263060')
        self.entity.scene.add(particle)
        self.emmiters.append(particle)
        
        particle = engine.particle.ParticleEmitter(self.entity.center, 2 * size, 0.08, 0.5, max=5 * size,  hor_min=-20 * size, hor_max=20 * size, vert_min=-40 * size, vert_max=-15 * size, color='#733d3860')
        self.entity.scene.add(particle)
        self.emmiters.append(particle)
        
        particle = engine.particle.ParticleEmitter(self.entity.center, 2 * size, 0.06, 0.5, max=5 * size,  hor_min=-10 * size, hor_max=10 * size, vert_min=-45 * size, vert_max=-15 * size, color='#a3263360')
        self.entity.scene.add(particle)
        self.emmiters.append(particle)
        
        particle = engine.particle.ParticleEmitter(self.entity.center, 2 * size, 0.06, 0.5, max=5 * size,  hor_min=-10 * size, hor_max=10 * size, vert_min=-45 * size, vert_max=-15 * size, color='#f7752160')
        self.entity.scene.add(particle)
        self.emmiters.append(particle)
        
        particle = engine.particle.ParticleEmitter(self.entity.center, 2 * size, 0.06, 0.2, max=5 * size,  hor_min=-10 * size, hor_max=20 * size, vert_min=-45 * size, vert_max=-15 * size, color='#ffe86160')
        self.entity.scene.add(particle)
        self.emmiters.append(particle)
    
    def update(self, dt):
        for emmiter in self.emmiters:
            emmiter.position = self.entity.center

class Tween(Component):
    def __init__(self, entity, curve: "engine.math.Curve", target: vector, duration: int, from_center = False):
        super().__init__("tween", entity)
        self.curve = curve
        self.from_center = from_center
        
        self.start_position = self.entity.position

        self.duration: float = duration
        self.time_past = 0
        self.target = target

    def update(self, dt):
        time_percentage: float = min(1, ((self.time_past) /  self.duration))
        percentage = self.curve.get_value(time_percentage)
        
        if time_percentage == 1:
            self.remove()
            return
        
        distance = percentage * (abs(self.target.distance_to(self.start_position)))
        
        self.time_past += dt
        

        vec = engine.math.vector_towards(self.start_position, self.target, distance)
        if self.from_center:
            self.entity.center = self.start_position + vec
        else:
            self.entity.position = self.start_position + vec
