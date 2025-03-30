import sys
from array import array
import pygame
import moderngl
import engine
from pygame import Vector2 as vector
import numpy as np

from dataclasses import dataclass

import engine.data


default_vert_shader = '''
#version 330 core

uniform vec2 CameraPosition;
uniform float CameraZoom;
uniform vec2 Position;
uniform vec2 ASMultiplier;

in vec2 vert;
in vec2 texCoord;
out vec2 uv;

void main() {
    uv = texCoord;


    gl_Position = vec4(((vert + Position - CameraPosition) / CameraZoom) * ASMultiplier, 0.0, 1.0);
}
'''

default_frag_shader = '''
#version 330 core

uniform sampler2D tex;
in vec2 uv;
out vec4 f_color;

void main() {
    f_color = vec4(texture(tex, uv).rgb, 1.0);
}
'''

def surf_to_texture(surf, ctx: moderngl.Context, aa = moderngl.NEAREST):
    tex = ctx.texture(surf.get_size(), 4)
    tex.filter = (aa, aa)
    tex.swizzle = "BGRA"
    tex.write(surf.get_view('1'))
    return tex

def hex_to_rgb(hex_color):
    """Convert hex color (#RRGGBB or RRGGBB) to an RGB tuple (R, G, B)."""
    hex_color = hex_color.lstrip("#")  
    if len(hex_color) != 6:
        raise ValueError("Hex color must be 6 characters long.")
    
    return tuple((int(hex_color[i:i+2], 16)/255) for i in (0, 2, 4))

@dataclass
class Frame:
    duration: int
    pos: tuple

@dataclass
class Animation:
    frames: list[Frame]

class AnimationPlayer:
    def __init__(self, spritesheet: "Spritesheet", animations: dict[str, Animation]):
        self.animations = animations
        self.spritesheet = spritesheet
        self.anim_timer = engine.core.Timer(1) 
        self.current_animation = "none"
        self.index = 0

    def set_animation(self, name: str):
        self.current_animation = name
        self.index = 0
        self.anim_timer.duration = self.animations[self.current_animation][self.index].duration
        self.anim_timer.activate()

    def update_image(self):
        if self.current_animation != "none":
            if self.anim_timer.complete:
                self.index += 1
                self.anim_timer.duration = self.animations[self.current_animation][self.index].duration
                self.anim_timer.activate()

            elif (not self.anim_timer.active) and (self.current_animation != None):
                self.anim_timer.activate()

    def get_image(self):
        return self.spritesheet.get_image(self.animations[self.current_animation][self.index].pos)

    def update(self, dt):
        self.anim_timer.update(dt)
        self.update_image()

@dataclass
class SpriteSheetLayout:
    tile_size: pygame.Vector2
    ignore_empty: bool


class Spritesheet:
    def __init__(self, surf: pygame.surface.Surface, layout: SpriteSheetLayout):
        self.images: list[list[None | pygame.surface.Surface]] = []
        self.generate_images(surf, layout)

    def generate_image_list(self, width, height):
        for y in range(height):
            self.images.append([])
            for x in range(width):
                self.images[y].append(None)

    def generate_images(self, surf: pygame.surface.Surface, layout: SpriteSheetLayout):
        width = surf.get_size()[0] / layout.tile_size
        height = surf.get_size()[1] / layout.tile_size

        for y in range(round(height)):
            self.images.append([])
            for x in range(round(width)):
                self.images[y].append(surf.subsurface(pygame.Rect(x * layout.tile_size, y * layout.tile_size, layout.tile_size, layout.tile_size)))        

    def get_image(self, pos: tuple) -> pygame.Surface:
        return self.images[pos[1]][pos[0]]


class Shader:
    def __init__(self, vert, frag): 
        self.vert = vert
        self.frag = frag
    
    def set_vert_uniforms(self):
        pass
        self.program['CameraPosition'] = self.image.scene.camera.ndc_pos
        self.program['CameraZoom'] = self.image.scene.camera.zoom
        self.program['Position'] = self.image.scene.camera.pixel_to_ndc(self.image.position)
        self.program['ASMultiplier'] = self.image.scene.camera.ASMultiplier

    def initialize(self, image: "Image"):
        self.image = image
        self.program = self.image.scene.glCtx.program(vertex_shader=self.vert, fragment_shader=self.frag)
    
    def set_uniforms(self):
        pass

class DefaultShader(Shader):
    def __init__(self):
        super().__init__(default_vert_shader, default_frag_shader)

    def set_uniforms(self):
        self.program['tex'] = self.image.scene.texture_locker.get_value(self.image.name)

class Image:
    def __init__(self, surf, name: str, scene: engine.core.Scene, size=(32,32)):
        self.scene = scene
        self.name = name
        self.surf = pygame.transform.scale(surf, size)
        self.surf = surf
        self.size = size
        self.position = vector(0, 0)

    def set_shader(self, shader):
        return 
    
    def remove(self):
        return

    def update(self, dt):
        pass

    def draw(self):
        offset_pos = self.position - self.scene.camera.position
        self.scene.display.blit(self.surf, offset_pos)

class AnimatedImage(Image):
    def __init__(self, animation_player: AnimationPlayer, size: vector, name: str, scene: engine.core.Scene):
        self.animation_player = animation_player
        self.scene = scene
        self.name = name
        self.rect = self.surf.get_rect()
         
        self.size = size
        self.position = vector(0, 0)

    def update_image(self):
        pass
    def update(self, dt):
        self.animation_player.update(dt)

    def draw(self):
        self.update_image()
        super().draw()

class Camera(engine.core.Entity):
    def __init__(self, pos, scene, zoom=5):
        super().__init__(pos, scene)
        self.rotation = 0
        self.zoom = zoom
        self.camera_id = 1
        self.ASMultiplier = self.get_aspect_ratio_multiplier()
        self.ndc_pos = self.pixel_to_ndc(self.position)

    def on_resize(self):
        self.ASMultiplier = self.get_aspect_ratio_multiplier()

    def on_update(self, dt):
        self.ndc_pos = self.pixel_to_ndc(self.position)

    def pixel_to_ndc(self, pos):
        width = self.scene.main.window_size[0]/self.zoom
        height = self.scene.main.window_size[1]/self.zoom
        return vector(pos[0]/width, pos[1]/height)

    def on_resize(self):
        self.ASMultiplier = self.get_aspect_ratio_multiplier()
    
    def get_aspect_ratio_multiplier(self):
        width = self.scene.main.window_size[0]
        height = self.scene.main.window_size[1]

        multiplier = vector(1, 1)
        if width > height:
            multiplier.x = height/width
        else:
            multiplier.y = width/height

        return multiplier

LIGHT_VERTEX_SHADER = """
#version 330 core
in vec2 vert;
out vec2 uv;
void main() {
    uv = vert;
    gl_Position = vec4(vert, 0.0, 1.0);
}
"""

LIGHT_FRAGMENT_SHADER = """
#version 330 core
in vec2 uv;
out vec4 fragColor;
uniform sampler2D sceneTexture;
uniform sampler2D lightTexture;
uniform vec2 lightPosition;  
uniform float lightRadius;
uniform vec3 lightColor;
uniform float lightIntensity;

void main() {
    vec4 sceneColor = texture(sceneTexture, uv);
    vec4 lightMask = texture(lightTexture, uv);
    vec4 totalLight = vec4(0.0);

    
    float dist = length(uv - lightPosition);
    float intensity = clamp(1.0 - (dist / lightRadius), 0.0, 1.0) * lightIntensity;
    totalLight += vec4(lightColor * intensity, 1.0);
    

    fragColor = sceneColor * totalLight * lightMask;
}
"""

class Light(engine.core.Entity):
    def __init__(self, position, scene, radius: int, color: str, intensity: int):
        super().__init__(position, scene)
        self.intensity = intensity
        self.radius = radius
        self.color = color
        self.key = self.scene.lighting_manager.add(self)

    def on_kill(self):
        self.scene.lighting_manager.remove(self.key)

class LightingManager:
    def __init__(self, scene: engine.core.Scene):
        self.scene = scene
        self.ambient_lighting = 0.8
        self.texture_key = "__ENGINE__light_texture"
        self.scene.texture_locker.add(self.texture_key)
    
        self.ctx = scene.glCtx

        self.light_key_locker = engine.data.IndexKeyLocker()


        self.lights: list[Light] = []
        self.light_texture = self.ctx.texture(scene.main.window_size, 4)

        self.light_fbo = self.ctx.framebuffer(
            color_attachments=[self.light_texture]
        )
        self.light_shader = self.ctx.program(
            vertex_shader=LIGHT_VERTEX_SHADER, fragment_shader=LIGHT_FRAGMENT_SHADER
        )
        self.quad_buffer = self.ctx.buffer(data=np.array([
            -1, -1, 1, -1, -1, 1,
            -1, 1, 1, -1, 1, 1
        ], dtype=np.float32))
        self.vao: moderngl.VertexArray = self.ctx.vertex_array(
            self.light_shader, [(self.quad_buffer, "2f", "vert")]
        )
    
    def add(self, light: Light) -> str:
        self.lights.append(light)
        return self.light_key_locker.add()
    
    def remove(self, key):
        index = self.light_key_locker.remove(key)
        del self.lights[index]

    def on_resize(self):
        self.light_texture.release()
        self.light_fbo.release()
        self.light_texture = self.ctx.texture(self.scene.main.window_size, 4)
        print(self.light_texture.size)
        self.light_fbo = self.ctx.framebuffer(color_attachments=[self.light_texture])

    def render_lights(self):
        self.light_fbo.use()
        self.ctx.clear(self.ambient_lighting, self.ambient_lighting, self.ambient_lighting, 1.0)
        
        for light in self.lights:
            self.light_shader["lightPosition"] = light.position
            self.light_shader["lightRadius"] = light.radius
            self.light_shader["lightColor"] = hex_to_rgb(light.color)
            self.light_shader["lightIntensity"] = light.intensity

            self.vao.render(moderngl.TRIANGLE_STRIP)
        self.ctx.screen.use()