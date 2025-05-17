import os
import sys
from array import array

import pygame

import moderngl
import OpenGL.GL as gl

import FreeBodyEngine as engine
from pygame import Vector2 as vector
import numpy as np
import math

from typing import Union, Iterable
from dataclasses import dataclass

import FreeBodyEngine.data


DEFAULT_NORMAL = "#8080ff"


def surf_to_texture(surf, ctx: moderngl.Context, aa=moderngl.NEAREST):
    tex = ctx.texture(surf.get_size(), 4)
    tex.filter = (aa, aa)
    tex.swizzle = "BGRA"
    tex.write(surf.get_view("1"))
    return tex


def create_fullscreen_quad(ctx, shader, size=vector(1, 1)):
    quad_vertices = np.array(
        [
            -1.0,
            -1.0,
            0.0,
            0.0,  # Bottom-left
            1.0,
            -1.0,
            1.0,
            0.0,  # Bottom-right
            1.0,
            1.0,
            1.0,
            1.0,  # Top-right
            -1.0,
            1.0,
            0.0,
            1.0,  # Top-left
        ],
        dtype="f4",
    )

    indices = np.array(
        [
            0,
            1,
            2,  # First triangle
            2,
            3,
            0,  # Second triangle
        ],
        dtype="i4",
    )

    vbo = ctx.buffer(quad_vertices)
    ibo = ctx.buffer(indices)

    vao = ctx.vertex_array(
        shader,
        [(vbo, "2f 2f", "vert", "texCoord")],  # Bind attributes
        ibo,
    )

    return vao


def get_texture_aspect_ratio(texture: moderngl.Texture):
    return engine.math.simplify_fraction(texture.size[0], texture.size[1])



@dataclass
class Frame:
    duration: int
    pos: tuple
    flip: bool


@dataclass
class Animation:
    frames: list[Frame]
    next: str | None


class AnimationPlayer:
    def __init__(self, spritesheet: "Spritesheet", animations: dict[str, Animation]):
        self.animations = animations
        self.spritesheet = spritesheet
        self.use_normal = self.spritesheet.use_normal
        self.anim_timer = engine.actor.Timer(1)
        self.current_animation = "none"

        self.index = 0
        self.on_change: callable = None
        self.set_animation(list(self.animations.keys())[0])

    def set_animation(self, name: str):
        self.current_animation = name
        self.index = 0
        self.anim_timer.duration = (
            self.animations[self.current_animation].frames[self.index]["duration"]
            / 1000
        )
        self.anim_timer.activate()

    def update_image(self):
        if self.current_animation != "none":
            if self.anim_timer.complete:
                self.index += 1
                if self.index > len(self.animations[self.current_animation].frames) - 1:
                    if self.animations[self.current_animation].next:
                        self.set_animation(self.animations[self.current_animation].next)
                        self.index = 0

                    else:
                        self.index = 0
                self.anim_timer.duration = (
                    self.animations[self.current_animation].frames[self.index][
                        "duration"
                    ]
                    / 1000
                )
                self.anim_timer.activate()
                if self.on_change != None:
                    self.on_change()

            elif (not self.anim_timer.active) and (self.current_animation != None):
                self.anim_timer.activate()

    def get_pos(self):
        return self.animations[self.current_animation].frames[self.index]["pos"]

    def update(self, dt):
        self.anim_timer.update(dt)
        self.update_image()


@dataclass
class Spritesheet:
    general: moderngl.Texture
    normal: moderngl.Texture
    use_normal: bool
    size: vector


class Shader:
    def __init__(self, scene, vert, frag):
        self.vert = vert
        self.frag = frag

    def set_generic_uniforms(self):
        for uniform in self.program:
            if uniform == "proj":
                self.program[uniform].write(
                    self.image.scene.camera.proj_matrix.tobytes()
                )

            elif uniform == "view":
                self.program[uniform].write(
                    self.image.scene.camera.view_matrix.tobytes()
                )

            elif uniform == "position":
                self.program[uniform] = (
                    (self.image.position.x + self.image.offset.x),
                    -(self.image.position.y + self.image.offset.y),
                )

            elif uniform == "time":
                self.program[uniform] = pygame.time.get_ticks()

            elif uniform == "tex":
                key = self.image.scene.texture_locker.get_value(self.image.name)
                if key:
                    self.program[uniform] = key

            elif uniform == "normal_tex":
                key = self.image.scene.texture_locker.get_value(self.image.normal_name)
                if key:
                    self.program[uniform] = key

    def set_frag_uniforms(self):
        pass

    def set_vert_uniforms(self):
        pass

    def set_uniforms(self):
        # print(*self.program)
        self.set_generic_uniforms()
        self.set_vert_uniforms()
        self.set_frag_uniforms()

    def initialize(self, image: "Image"):
        self.image = image
        self.program = self.image.scene.glCtx.program(
            vertex_shader=self.vert, fragment_shader=self.frag
        )


class DefaultShader(Shader):
    def __init__(self, scene: engine.actor.Scene):
        super().__init__(
            scene,
            scene.files.load_text("engine/shader/graphics/world.vert"),
            scene.files.load_text("engine/shader/graphics/world.frag"),
        )


class AnimatedShader(Shader):
    def __init__(self, scene: engine.actor.Scene, vert=None, frag=None):
        if vert:
            v = vert
        else:
            v = scene.files.load_text("engine/shader/graphics/world.vert")

        if frag:
            f = frag
        else:
            f = scene.files.load_text("engine/shader/graphics/animation.frag")

        super().__init__(scene, v, f)
        self.image: AnimatedImage

    def set_frag_uniforms(self):
        albedo = self.image.scene.texture_locker.add(self.image.name)
        normal = self.image.scene.texture_locker.add(self.image.normal_name)

        self.image.animation_player.spritesheet.general.use(albedo)

        if self.image.animation_player.spritesheet.normal:
            self.image.animation_player.spritesheet.normal.use(normal)

        self.program["albedo"] = albedo
        self.program["normal"] = normal

        self.program["spritesheet_size"] = (
            self.image.animation_player.spritesheet.general.size
        )
        self.program["img_size"] = self.image.size
        self.program["img_pos"] = self.image.animation_player.get_pos()

        self.image.scene.texture_locker.remove(self.image.name)
        self.image.scene.texture_locker.remove(self.image.normal_name)


class AnimatedImage(Image):
    def __init__(
        self,
        animation_player: AnimationPlayer,
        name: str,
        scene: engine.actor.Scene,
        z=1,
        size: vector = None,
    ):
        self.animation_player = animation_player
        self.scene = scene
        self.name = name
        self.normal_name = self.name + "_normal"
        if size == None:
            self.size = vector(*self.animation_player.spritesheet.size)
        else:
            self.size = size

        self.position = vector(0, 0)
        self.offset = vector(0, 0)
        self.z = z

        self.set_shader(AnimatedShader(self.scene))

    def update(self, dt):
        self.animation_player.update(dt)

    def draw(self):
        self.shader.set_uniforms()
        self.render_object.render(mode=moderngl.TRIANGLE_STRIP)


class CompositeImage(Image):
    def __init__(self, name: str, images: list[Image], scene: engine.actor.Scene, z=1):
        self.images = images
        self.name = name
        self.scene = scene

        self._pos = vector(0, 0)

        self.z = z

    @property
    def center(self):
        return self.position

    @center.setter
    def center(self, new):
        self.position = new

    @property
    def position(self):
        return self._pos

    @position.setter
    def position(self, new):
        self._pos = new
        for image in self.images:
            image.position = self._pos

    def draw(self):
        for image in self.images:
            image.draw()

    def update(self, dt):
        for image in self.images:
            image.update(dt)

    def remove(self):
        for image in self.images:
            image.remove()

    def set_shader(self, shader):
        pass


class Camera(engine.actor.Entity):
    def __init__(self, pos, scene, zoom=5):
        super().__init__(pos, scene)
        self.rotation = 0
        self.zoom = zoom
        self.camera_id = 1
        self.background_color = Color("#b4befe")

        self.update_rect()
        self.update_view_matrix()
        self.update_projection_matrix()

    def on_resize(self):
        self.update_projection_matrix()

    def on_update(self, dt):
        self.update_projection_matrix()

    def on_draw(self):
        self.update_view_matrix()

    def update_rect(self):
        center_x, center_y = self.position.x, self.position.y
        width, height = (
            self.scene.main.window_size[0] / self.zoom,
            self.scene.main.window_size[1] / self.zoom,
        )

        self.rect = pygame.Rect(
            center_x - (width / 2), center_y - (height / 2), width, height
        )

    def update_projection_matrix(self):
        # Orthographic projection matrix
        self.update_rect()
        width = self.scene.main.window_size[0]
        height = self.scene.main.window_size[1]
        left = -width / 2
        right = width / 2
        bottom = -height / 2
        top = height / 2
        near = -1.0
        far = 1.0

        proj_matrix = np.array(
            [
                [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
                [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
                [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        scale_matrix = np.array(
            [
                [self.zoom, 0.0, 0.0, 0.0],  # Scale X
                [0.0, self.zoom, 0.0, 0.0],  # Scale Y
                [0.0, 0.0, 1.0, 0.0],  # Z remains unchanged
                [0.0, 0.0, 0.0, 1.0],  # Homogeneous coordinate
            ],
            dtype=np.float32,
        )

        self.proj_matrix = np.dot(proj_matrix, scale_matrix)

    def update_view_matrix(self):
        # Translation matrix
        tx, ty = -self.position.x, self.position.y
        translation_matrix = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [tx, ty, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        # Rotation matrix (around the Z-axis)
        angle = math.radians(self.rotation)
        cos_theta = math.cos(angle)
        sin_theta = math.sin(angle)

        rotation_matrix = np.array(
            [
                [cos_theta, -sin_theta, 0.0, 0.0],
                [sin_theta, cos_theta, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        # Combine translation and rotation
        self.view_matrix = np.dot(translation_matrix, rotation_matrix)


class DirectionalLight(engine.actor.Entity):
    def __init__(
        self, scene: engine.actor.Scene, color: Color, intensity: int, angle: int
    ):
        super().__init__(vector(0, 0), scene, vector(1, 1))
        self.data = {"intensity": intensity, "color": color, "angle": angle}

    @property
    def intensity(self) -> float:
        return self.data["intensity"]

    @intensity.setter
    def intensity(self, new):
        self.data["intensity"] = new

    @property
    def color(self) -> Color:
        return self.data["color"]

    @color.setter
    def color(self, new):
        self.data["color"] = new

    @property
    def angle(self) -> float:
        return self.data["angle"]

    @angle.setter
    def angle(self, new):
        self.data["angle"] = new

    def on_draw(self):
        self.scene.graphics.add_directional_light(self)


class PointLight(engine.actor.Entity):
    def __init__(self, position, scene, radius: int, color: Color, intensity: int):
        super().__init__(position, scene)

        self.data = {"intensity": intensity, "color": color, "radius": radius}

    @property
    def intensity(self) -> float:
        return self.data["intensity"]

    @intensity.setter
    def intensity(self, new):
        self.data["intensity"] = new

    @property
    def color(self) -> Color:
        return self.data["color"]

    @color.setter
    def color(self, new):
        self.data["color"] = new

    @property
    def radius(self) -> float:
        return self.data["radius"]

    @radius.setter
    def radius(self, new):
        self.data["radius"] = new

    def on_draw(self):
        self.scene.graphics.add_light(self)


class SpotLight(engine.actor.Entity):
    def __init__(
        self,
        position,
        scene,
        radius: int,
        color: Color,
        intensity: int,
        angle,
        direction,
    ):
        super().__init__(position, scene)

        self.data = {
            "intensity": intensity,
            "color": color,
            "radius": radius,
            "angle": angle,
            "direction": direction,
        }

    @property
    def intensity(self) -> float:
        return self.data["intensity"]

    @intensity.setter
    def intensity(self, new):
        self.data["intensity"] = new

    @property
    def color(self) -> Color:
        return self.data["color"]

    @color.setter
    def color(self, new):
        self.data["color"] = new

    @property
    def angle(self) -> float:
        return self.data["angle"]

    @angle.setter
    def angle(self, new):
        self.data["angle"] = new

    @property
    def direction(self) -> vector:
        return self.data["direction"]

    @direction.setter
    def direction(self, new):
        self.data["direction"] = new

    @property
    def radius(self) -> vector:
        return self.data["radius"]

    @radius.setter
    def radius(self, new):
        self.data["radius"] = new

    def on_draw(self):
        self.scene.graphics.add_spotlight(self)


RENDERING_MODES = ["full", "general", "normal", "light"]


class PostProcessLayer:
    def __init__(self, scene: engine.actor.Scene, frag: str):
        self.scene = scene

        self.program = self.scene.glCtx.program(uv_vert_shader, frag)
        self.vao = create_fullscreen_quad(self.scene.glCtx, self.program)

    def set_uniforms(self):
        self.set_generic_uniforms()
        self.on_set_uniforms()

    def on_set_uniforms(self):
        pass

    def set_generic_uniforms(self):
        for uniform in self.program:
            if uniform == "albedo_tex":
                self.program[uniform] = self.scene.texture_locker.get_value(
                    self.scene.graphics.albedo_key
                )
            elif uniform == "normal_tex":
                self.program[uniform] = self.scene.texture_locker.get_value(
                    self.scene.graphics.normal_key
                )
            elif uniform == "lighting_tex":
                self.program[uniform] = self.scene.texture_locker.get_value(
                    self.scene.graphics.lighting_key
                )
            elif uniform == "post_tex":
                self.program[uniform] = self.scene.texture_locker.get_value(
                    self.scene.graphics.post_key
                )
            elif uniform == "time":
                self.program[uniform] = pygame.time.get_ticks()

    def draw(self):
        self.set_uniforms()
        self.vao.render()

