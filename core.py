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
import FreeBodyEngine.math

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
    def __init__(self, name: str, entity: "Entity"):
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

class Physics(Component):
    def __init__(self, name, entity):
        super().__init__(name, entity)
        self.vel = vector(0, 0)

    def integrate_forces(self):        
        self.entity.transform.position += self.vel

    def update(self):
        self.integrate_forces()

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
    def __init__(self, name: str, entity: "Entity", shape: "ColliderShape", collision_type: str = "passive"):
        super().__init__(name, entity)
        self.collision_type = "passive"
        self.shape = shape



    def update(self, dt):
        self.check_collisions()

class _Entity:
    """
    A base class for objects that exist in a scene.
    """
    def __init__(self, scene: "Scene", name: str, position: vector = vector(0, 0), rotation: int = 0, scale: vector = vector(1, 1)):
        self.scene: "Scene" = scene
        self.name = name
        self.components: dict[str, Component] = []
        self.transform: Transform = Transform(position, rotation, scale)

    def add(self, *components):
        """
        Adds any amount of components. 
        """
        for component in components:
            self.components[component.name] = component

    def remove(self, name: str):
        """
        Removes the compnent with the given name.
        """
        if name in self.components.keys():
            self.components[name].remove()
            del self.components[name]
        
    def kill(self):
        """
        Removes the entity from its scene.
        """
        self.scene.entities.remove(self)
        self.on_kill()
    
    def update(self):
        pass

    def __repr__(self):
        return f"Entity(scene={self.scene}, name={self.name})"
    
    def __str__(self):
        return f"\"{self.name}\" in scene: {self.scene}"

    def on_kill(self):
        """
        Called when the entity is killed.
        """
        pass
    
    def on_draw(self):
        """
        Called when the scene is drawn.
        """
        pass

    def on_update(self):
        """
        Called when the entity is updated.
        """
        pass
    
class Raycast:
    def __init__(self, ):
        self.z


class Entity:
    def __init__(self, position: vector, scene, size=vector(32, 32), tag='none', anchor="center"):
        self.scene: Scene = scene
        self.tag = tag
        self.position = position
        self.screen_position = position
        self.components: list[Component] = []
        self.size = size
        
        self.anchor = anchor

    @property
    def center(self):
        return self.position + (self.size / 2)  # Calculates center from position    
    
    @center.setter
    def center(self, new_center):
        self.position = new_center - (self.size / 2)  # Adjusts position based on new center

    def kill(self):
        self.scene.entities.remove(self)
        self.on_kill()

    def update(self, dt):
        self.on_update(dt)
        
        for component in self.components:
            component.update(dt)
        self.on_post_update()     
    
    def on_event_loop(self, event):
        pass
    
    def on_kill(self):
        pass
    
    def on_draw(self): 
        pass

    def on_post_update(self):
        pass

    def on_update(self, dt):
        pass

# A drawn entity with basics physics 
class Actor(Entity):
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
        self.position += self.vel * dt

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
            self.image.position = self.position
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
        super().__init__(entity)
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

class SoundEmmiter(Entity):
    def __init__(self, position, sound_path, radius, max_volume=1, loop=False, tag=""):
        super().__init__(position, tag)
        self.sound = pygame.Sound(sound_path)
        self.sound.set_volume(max_volume)
        self.max_volume = max_volume
        self.radius = radius
        self.prev_volume = 0

    def play(self):
        pass

    def stop(self):
        pass

    def update_volume(self):
        distance = self.scene.camera.center.distance_to(self.position)
        volume = engine.math.clamp((distance * 100)/self.radius)
        
        if volume != self.prev_volume:
            self.sound.set_volume(volume)
        self.prev_volume = volume

    def on_update(self, dt):
        self.update_volume()

class Camera(Entity):
    def __init__(self, position: vector, scene, camera_id: str, zoom: float = -1.0, background_color: str = '#000000'):
        super().__init__(position, scene)
        self.camera_id = camera_id
        self.zoom = 1
        self.prev_zoom = self.zoom
        self.zoom_surf: pygame.surface.Surface
        self.bg_color = background_color
        
        self.mouse_screen_pos = vector(pygame.mouse.get_pos())
        self.mouse_world_pos = vector(0, 0)

        self.zoom_surf = pygame.surface.Surface(vector(self.scene.main.window_size[0] / self.zoom, self.scene.main.window_size[1] / self.zoom), pygame.SRCALPHA)
        self.update_domain()
        self.update_size()
        self.update_center()
           

    def on_event_loop(self, event):
        super().on_event_loop(event)
        if event.type == pygame.VIDEORESIZE:
            self.zoom_surf = pygame.surface.Surface(vector(self.scene.main.window_size[0] / self.zoom, self.scene.main.window_size[1] / self.zoom), pygame.SRCALPHA)

    def update_domain(self):
        self.domain = (range(round(self.position.x), round(self.position.x + (self.scene.main.window_size[0] / self.zoom))), range(round(self.position.y), round(self.position.y + (self.scene.main.window_size[1] / self.zoom))))
    def on_update(self, dt):
        self.update_domain()
        self.update_size()
        self.update_center()

    def update_size(self):
        self.size = vector(abs(self.domain[0].stop-self.domain[0].start), abs(self.domain[1].stop-self.domain[1].start))

    def update_center(self):
        self.center = vector((self.size.x / 2) - self.position.x, (self.size.y / 2) - self.position.y)

    def draw(self):
        if self.zoom != self.prev_zoom:
            self.zoom_surf = pygame.surface.Surface(vector(self.scene.main.window_size[0] / self.zoom, self.scene.main.window_size[1] / self.zoom), pygame.SRCALPHA)
        self.zoom_surf.fill(self.bg_color)
        self.prev_zoom = self.zoom        
        for circleParticle in sorted(
        (e for e in self.scene.entities if isinstance(e, engine.particle.CircleParticle)),
        key=lambda e: e.position.y
        ):

            position = (circleParticle.position - self.position) - (vector(circleParticle.surf.size) / 2)
            self.zoom_surf.blit(circleParticle.surf, position)

        
        for emitter in (e for e in self.scene.entities if isinstance(e, engine.particle.ParticleEmitter)):
            for particle in emitter.particles:
                pygame.draw.circle(self.zoom_surf, particle.color, (particle.pos.x - self.position.x, particle.pos.y - self.position.y), particle.radius)

        for actor in sorted(
        (e for e in self.scene.entities if isinstance(e, Actor)),
        key=lambda e: e.z
        ):
            if actor.visible:
                if actor.anchor == "center":
                    actor.screen_position = (actor.center - self.position)

                elif actor.anchor == "topleft":
                    actor.screen_position = (actor.position - self.position)

                self.zoom_surf.blit(actor.image, actor.screen_position)
        
        
        #self.scene.main.screen.blit(self.zoom_surf, (0, 0))

        self.scene.main.screen.blit(pygame.transform.scale_by(self.zoom_surf, self.zoom), (0, 0))


class Scene:
    def __init__(self, main: "Main"):
        self.SDL = main.SDL

        self.main = main
        self.entities: list[Entity] = []
        
        self.camera: engine.graphics.Camera
        self.files: engine.files.FileManager = self.main.files

        self.camera = engine.graphics.Camera(vector(0, 32), self, 1)
        self.texture_locker = engine.data.KeyLocker()
        self.glCtx: moderngl.Context = self.main.glCtx
        self.glCtx.enable(moderngl.BLEND)
        self.glCtx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.scene_texture = self.glCtx.texture(self.main.window_size, 4)
     

        self.graphics = engine.graphics.Graphics(self, self.glCtx)      
            
        self.add(self.camera)
        self.input = InputManager(self)
        
        
        self.ui = engine.ui.UIManager(self)

        self.update_mouse_pos()

    
    def graphics_setup(self):
        if not self.SDL:
            
            self.screen = self.glCtx.framebuffer(color_attachments=[self.scene_texture])

            self.program = self.glCtx.program(vertex_shader=scene_vertex_shader, fragment_shader=scene_fragment_shader)

            # Define vertices for a fullscreen quad (to display the framebuffer texture)
            vertices = np.array([
                -1, -1,  0, 0,
                1, -1,  1, 0,
                -1,  1,  0, 1,
                1,  1,  1, 1,
            ], dtype='f4')

            vbo = self.glCtx.buffer(vertices)
            self.vao = self.glCtx.simple_vertex_array(self.program, vbo, 'in_vert', 'in_text')
        else:
            self.display = pygame.surface.Surface((self.main.window_size[0] / self.camera.zoom, self.main.window_size[1] / self.camera.zoom))

    def set_active_camera(self, camera_id):
        for entity in self.entities:
            if entity.__class__ == Camera:
                if entity.camera_id == camera_id:
                    self.camera = entity

    def on_resize(self):
        self.graphics.on_resize()
        #self.lighting_manager.on_resize()
        self.camera.on_resize()
        self.ui.on_resize()
        self.glCtx.viewport = (0, 0, self.main.window_size[0], self.main.window_size[1])
    
    def event_loop(self, event):
        self.input.event_loop(event)
        for entity in self.entities:
            entity.on_event_loop(event)
        
    def on_post_draw(self):
        pass

    def update_mouse_pos(self):
        self.mouse_screen_pos = vector(pygame.mouse.get_pos())
        self.mouse_world_pos = vector((self.camera.position.x - (self.main.window_size[0]/2) / self.camera.zoom) + (self.mouse_screen_pos[0] / self.camera.zoom), (self.camera.position.y - (self.main.window_size[1]/2) / self.camera.zoom) + (self.mouse_screen_pos[1] / self.camera.zoom))

    def add(self, actor):
        self.entities.append(actor)

    def on_update(self, dt):
        pass

    def draw(self):
        self.on_draw()

        for entity in self.entities:
            entity.on_draw()
        
        self.graphics.draw()

        self.on_post_draw()

    def on_draw(self):
        pass

    def update(self, dt):
        self.input.handle_input()
        self.update_mouse_pos()
        self.graphics.update(dt)
        for entity in self.entities:
            entity.update(dt)
        self.on_update(dt)
        self.ui.update(dt)
        self.draw()

class Main: 
    def __init__(self, SDL, window_size: tuple = [800, 800], starting_scene: Scene = None, flags=pygame.RESIZABLE, fps: int = 60, display: int = 0, asset_dir=str):
        pygame.init()
        
        self.game_name = "FreeBodyEngine"
        self.files = engine.files.FileManager(self, asset_dir)
        self.SDL = SDL
        self.window_size = window_size
        self.fps_cap = fps
        self.volume = 100
        self.fps_timer = engine.core.Timer(10)
        self.fps_timer.activate()
        self.screen = pygame.display.set_mode(self.window_size, flags, display=display)
        
        self.clock = pygame.time.Clock()
        self.dt = 0

        self.glCtx = moderngl.create_context()
        self.scenes: dict[str, Scene] = {}
        self.active_scene: Scene = None

        self.transition_manager = SceneTransitionManager(self)

    def event_loop(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.VIDEORESIZE:
                self.window_size = pygame.display.get_window_size()
                self.active_scene.on_resize()
            self.on_event_loop(event)
            if self.active_scene:
                self.active_scene.event_loop(event)

    def on_event_loop(self, event):
        pass

    def add_scene(self, scene: Scene, name: str):
        self.scenes[name] = scene

    def remove_scene(self, name: str):
        if self.scenes[str] == self.active_scene:
            self.active_scene = None
        del self.scenes[str]

    def change_scene(self, name: str, transition: "SceneTransition" = None):
        if transition == None:
            self._set_scene(name)
        else:
            self.transition_manager.transition(transition, name)

    def _set_scene(self, name: str):
        self.active_scene = self.scenes[name]

    def has_scene(self, targetScene):
        for scene in self.scenes:
            if scene == targetScene:
                return True
        return False

    def run(self, profiler):
        total_fps = 0
        ticks = 0
        pygame.display.set_caption(f"Engine Dev       FPS: {round(self.clock.get_fps())}")

        if profiler:
            profiler_thread = threading.Thread(target=engine.debug.create_profiler_window, daemon=True)
            profiler_thread.start()
            
        while True: 
            dt = self.clock.tick(self.fps_cap) / 1000
            total_fps += self.clock.get_fps()
            ticks += 1
            self.fps_timer.update(dt)
            if self.fps_timer.complete:
                pygame.display.set_caption(f"Engine Dev       FPS: {round(total_fps/ticks)}")
                self.fps_timer.activate()
            self.event_loop()
            self.transition_manager.update(dt)

            if self.active_scene:
                self.active_scene.update(dt)
            self.transition_manager.draw()
            pygame.display.flip() 

class SceneTransition:
    def __init__(self, main: "Main", vert, frag, duration, curve = engine.math.Linear()):
        self.elapsed = 0
        self.duration = duration 
        self.time: int = 0
        
        self._reversed = False
        print('NEW NEW NEW NEW NEW NEW NEW NEW NEW')

        self.main = main
        self.curve = curve

        self.program = self.main.glCtx.program(vert, frag)
        
        self.vao = engine.graphics.create_fullscreen_quad(self.main.glCtx, self.program)        

    def update(self, dt):
        if not self._reversed:
            self.elapsed = min(self.elapsed + dt, self.duration) 
            self.time = self.curve.get_value(self.elapsed/self.duration)

            if self.time >= 1:
                self._reversed = True
                self.main._set_scene(self.main.transition_manager.new_scene)
        else:
            self.elapsed = max(self.elapsed - dt, 0)
            if self.elapsed == 0:
                self.time = 0
            else:
                self.time = self.curve.get_value(self.elapsed/self.duration)            
            
            if self.time <= 0:
                self.main.transition_manager.current_transition = None        
        
        print(self.elapsed)

    def draw(self):
        self.program['time'] = self.time
        if "inverse" in self.program:
            self.program['inverse'] = not self._reversed 
        self.main.glCtx.screen.use()
        self.vao.render(moderngl.TRIANGLE_STRIP)

class FadeTransition(SceneTransition):
    def __init__(self, main: "Main", duration: int):
        super().__init__(main, main.files.load_text('engine/shader/graphics/empty.vert'), main.files.load_text('engine/shader/scene_transitions/fade.glsl'), duration, engine.math.EaseInOut())

class StarWarsTransition(SceneTransition):
    def __init__(self, main: "Main", duration: int):
        super().__init__(main, main.files.load_text('engine/shader/graphics/uv.vert'), main.files.load_text('engine/shader/scene_transitions/starwars.glsl'), duration, engine.math.EaseInOut())

class SceneTransitionManager:
    def __init__(self, main: Main):
        self.main = main
        self.current_transition: SceneTransition = None
        self.new_scene: str = None

    def transition(self, transition: SceneTransition, new_scene: str):
        self.current_transition = transition
        self.new_scene = new_scene

    def update(self, dt):
        if self.current_transition:
            self.current_transition.update(dt)

    def draw(self):
        if self.current_transition:
            self.current_transition.draw()

class SplashScreenScene(Scene):
    def __init__(self, main: Main, duration: int, new_scene: str, texture: moderngl.Texture, color: str, transition=None):
        self.timer = Timer(duration)
        self.duration = duration
        self.timer.activate()
        self.transition = transition
        super().__init__(main)
        self.graphics.rendering_mode = "general"
        self.camera.background_color.hex = color

        self.new_scene = new_scene
        aspect = engine.graphics.get_texture_aspect_ratio(texture)
        print(aspect, texture.size)
        self.ui.add(engine.ui.UIImage(self.ui, texture, {"anchor": "bottomright", "height": "100%h", "aspect-ratio": aspect}))
        
        self.started_transition = False

    def on_update(self, dt):
        self.timer.update(dt)
        
        if self.timer.complete and not self.started_transition:
            self.started_transition = True
            if self.transition == None:
                transition =  StarWarsTransition(self.main, self.duration)
            else:
                transition = self.transition
            self.main.change_scene(self.new_scene, transition)


class InputManager: # im very sorry for what you're about to read
    def __init__(self, scene: Scene):
        self.scene = scene
        self.actions: dict[str, list[str]]
        self.active = {}
        self.controllers = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

        self.change_controller()
        self.input_mappings = {"K_Down": pygame.K_DOWN, "K_Up": pygame.K_UP, "K_Left": pygame.K_LEFT, "K_Right": pygame.K_RIGHT, "K_A": pygame.K_a, "K_D": pygame.K_d, "K_W": pygame.K_w, "K_S": pygame.K_s, "K_PGUP": pygame.K_PAGEUP, "K_PGDOWN": pygame.K_PAGEDOWN, "K_F3": pygame.K_F3, "K_F4": pygame.K_F4}
        self.mouse_mappings = {"M_SCRL_UP": -1, "M_SCRL_DOWN": 1}
        self.controller_input =  {"C_DDown": False, "C_DUp": False, "C_DLeft": False, "C_DRight": False, "C_BY": False, "C_BB": False, "C_BA": False, "C_BX": False, "C_T1": False, "C_T2": False, "C_B1": False, "C_B2": False, "C_LStick_Up": False, "C_LStick_Down": False, "C_LStick_Left": False, "C_LStick_Right": False, "C_RStick_Up": False, "C_RStick_Down": False, "C_RStick_Left": False, "C_RStick_Right": False}

        self.scroll_input = {"M_SCRL_UP": False, "M_SCRL_DOWN": False}

        self.joy_stick_generosity = 0.2
        self.get_controller_input()
        self.curr_input_type = "key"

        self.actions = self.scene.files.load_json('controlls/actions.json')
        for action in self.actions:
            self.active[action] = False

    def get_mouse_pressed(self, type='game') -> tuple[bool, bool, bool]:
        return pygame.mouse.get_pressed()

    def get_controllers(self):
        self.controllers = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

    def change_controller(self):
        self.get_controllers()
        if len(self.controllers) > 0:
            self.controller = self.controllers[0]
        else:
            self.controller = None
            
    def get_controller_input(self): # shitty controller standards kinda make this mess necessary
        if len(self.controllers) > 0:
            for input in self.controller_input:
                self.controller_input[input] = False
            
            controller_name = self.controller.get_name()
            if controller_name == "Xbox One Controller":
                dpad = self.controller.get_hat(0)
                if dpad[0] == -1:
                    self.controller_input["C_DLeft"] = True
                if dpad[0] == 1:
                    self.controller_input["C_DRight"] = True
                if dpad[1] == -1:
                    self.controller_input["C_DDown"] = True
                if dpad[1] == 1:
                    self.controller_input["C_DUp"] = True
                
                # left stick
                lStickHor = self.controller.get_axis(0)
                lStickVert = self.controller.get_axis(1)
                if lStickVert > 1 - self.joy_stick_generosity:
                    self.controller_input["C_LStick_Down"] = True
                elif lStickVert < -1 + self.joy_stick_generosity:
                    self.controller_input["C_LStick_Up"] = True
                if lStickHor > 1 - self.joy_stick_generosity:
                    self.controller_input["C_LStick_Right"] = True
                elif lStickHor < -1 + self.joy_stick_generosity:
                    self.controller_input["C_LStick_Left"] = True
                if lStickHor > 0.65 - self.joy_stick_generosity and lStickVert > 0.65 - self.joy_stick_generosity:
                    self.controller_input["C_LStick_Down"] = True
                    self.controller_input["C_LStick_Right"] = True
                if lStickHor > 0.65 - self.joy_stick_generosity and lStickVert < -0.65 + self.joy_stick_generosity:
                    self.controller_input["C_LStick_Up"] = True
                    self.controller_input["C_LStick_Right"] = True
                if lStickHor < -0.65 + self.joy_stick_generosity and lStickVert > 0.65 - self.joy_stick_generosity:
                    self.controller_input["C_LStick_Down"] = True
                    self.controller_input["C_LStick_Left"] = True
                if lStickHor < -0.65 + self.joy_stick_generosity and lStickVert < -0.65 + self.joy_stick_generosity:
                    self.controller_input["C_LStick_Up"] = True
                    self.controller_input["C_LStick_Left"] = True

                # left stick
                rStickHor = self.controller.get_axis(2)
                rStickVert = self.controller.get_axis(3)
                if rStickVert > 1 - self.joy_stick_generosity:
                    self.controller_input["C_RStick_Down"] = True
                elif rStickVert < -1 + self.joy_stick_generosity:
                    self.controller_input["C_RStick_Up"] = True
                if rStickHor > 1 - self.joy_stick_generosity:
                    self.controller_input["C_RStick_Right"] = True
                elif rStickHor < -1 + self.joy_stick_generosity:
                    self.controller_input["C_RStick_Left"] = True

                if rStickHor > 0.65 - self.joy_stick_generosity and rStickVert > 0.65 - self.joy_stick_generosity:
                    self.controller_input["C_RStick_Down"] = True
                    self.controller_input["C_RStick_Right"] = True
                if rStickHor > 0.65 - self.joy_stick_generosity and rStickVert < -0.65 + self.joy_stick_generosity:
                    self.controller_input["C_RStick_Up"] = True
                    self.controller_input["C_RStick_Right"] = True
                if rStickHor < -0.65 + self.joy_stick_generosity and rStickVert > 0.65 - self.joy_stick_generosity:
                    self.controller_input["C_RStick_Down"] = True
                    self.controller_input["C_RStick_Left"] = True
                if rStickHor < -0.65 + self.joy_stick_generosity and rStickVert < -0.65 + self.joy_stick_generosity:
                    self.controller_input["C_RStick_Up"] = True
                    self.controller_input["C_RStick_Left"] = True

    def reset_actions(self):
        for action in self.active:
            self.active[action] = False

    def check_action(self, action) -> bool: 
        return self.active[action]

    def event_loop(self, event):

        if event.type == pygame.JOYDEVICEADDED:
            self.change_controller()
        if event.type == pygame.JOYDEVICEREMOVED:
            self.change_controller()
        if event.type == pygame.MOUSEWHEEL:
            if event.y == self.mouse_mappings["M_SCRL_UP"]:
                self.scroll_input["M_SCRL_UP"] = True
            if event.y == self.mouse_mappings["M_SCRL_DOWN"]:
                self.scroll_input["M_SCRL_DOWN"] = True

    def handle_input(self):
        pygame.event.get()
        keys = pygame.key.get_pressed()

        self.reset_actions()

        for action in self.actions:
            for input in self.actions[action]:
                if input.startswith("K") and keys[self.input_mappings[input]]:
                    self.active[action] = True
                if self.controller != None:
                    if input.startswith("C") and self.controller_input[input]:
                        self.active[action] = True
                if input.startswith("M"):
                    if input.startswith("M_SCRL") and self.scroll_input[input] == True:
                        self.active[action] = True
                        
        self.scroll_input["M_SCRL_UP"] = False
        self.scroll_input["M_SCRL_DOWN"] = False
        
                    
        self.get_controller_input()

