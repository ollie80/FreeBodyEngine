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

import freetype

from dataclasses import dataclass

import FreeBodyEngine.data

DEFAULT_NORMAL = "#8080ff"

empty_vert_shader = '''
#version 330 core

in vec2 vert;
in vec2 texCoord;

void main() {
    
    gl_Position = vec4(vert, texCoord.x, 1.0);
}
'''

uv_vert_shader = """
#version 330 core

in vec2 vert;
in vec2 texCoord;
out vec2 uv;

void main() {
    uv = texCoord;

    gl_Position = vec4(vert, 0.0, 1.0);
}
"""

plain_frag_shader = """
#version 330 core
out vec4 fragColor;
in vec2 uv;
void main() {
    uv;
    fragColor = vec4(uv, 1.0, 1.0);  
}
"""

texture_frag_shader = """
#version 330 core

uniform sampler2D tex;

in vec2 uv;
out vec4 f_color;

void main() {
    f_color = vec4(texture(tex, uv).rgba);
}
"""

WORLD_VERT_SHADER = '''
#version 330 core

uniform mat4 proj;
uniform mat4 view;
uniform vec2 position;

in vec2 vert;
in vec2 texCoord;
out vec2 uv;

void main() {
    uv = texCoord;

    gl_Position = proj * view * vec4(vec2(vert + position).x, vec2(vert + position).y, 0.0, 1.0);
}
'''

WORLD_FRAG_SHADER = '''
#version 330 core

uniform sampler2D tex;
uniform sampler2D normal_tex;

in vec2 uv;
out vec4 frag_albedo;  // Diffuse color
out vec4 frag_normal;  // Normal data

void main() {
    frag_albedo = texture(tex, uv);
    
    // Convert normal map from [0,1] to [-1,1] range
    vec4 normal = texture(normal_tex, uv).rgba;
    frag_normal = normal;
}
'''



ANIMATION_FRAG = """
#version 330 core

in vec2 uv;
out vec4 frag_albedo;
out vec4 frag_normal;

uniform sampler2D albedo;
uniform sampler2D normal;

uniform vec2 spritesheet_size;
uniform vec2 img_size;
uniform vec2 img_pos;

void main() {
    spritesheet_size;
    vec2 tile_pos = vec2(img_size * img_pos)/ spritesheet_size;
    vec2 tile_percentage = vec2(img_size/ spritesheet_size * uv);
    vec2 sample_pos = vec2(tile_pos + tile_percentage);
    frag_albedo = vec4(texture(albedo, sample_pos).rgba); 
    frag_normal = vec4(texture(normal, sample_pos).rgba); 
}
"""

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

def create_fullscreen_quad(ctx, shader, size=vector(1, 1)):
    quad_vertices = np.array([
        -1.0, -1.0,  0.0, 0.0,  # Bottom-left
         1.0, -1.0,  1.0, 0.0,  # Bottom-right
         1.0,  1.0,  1.0, 1.0,  # Top-right
        -1.0,  1.0,  0.0, 1.0   # Top-left
    ], dtype="f4")

    indices = np.array([
        0, 1, 2,  # First triangle
        2, 3, 0   # Second triangle
    ], dtype="i4")

    vbo = ctx.buffer(quad_vertices)
    ibo = ctx.buffer(indices)

    vao = ctx.vertex_array(
        shader,
        [(vbo, "2f 2f", "vert", "texCoord")],  # Bind attributes
        ibo
    )

    return vao

@dataclass
class Frame:
    duration: int
    pos: tuple
    flip: bool

@dataclass
class Animation:
    frames: list[Frame]

class AnimationPlayer:
    def __init__(self, spritesheet: "Spritesheet", animations: dict[str, Animation]):
        self.animations = animations
        self.spritesheet = spritesheet
        self.use_normal = self.spritesheet.use_normal
        self.anim_timer = engine.core.Timer(1) 
        self.current_animation = "none"
        self.index = 0
        self.on_change: callable = None
        self.set_animation(list(self.animations.keys())[0])

    def set_animation(self, name: str):
        self.current_animation = name
        self.index = 0
        self.anim_timer.duration = self.animations[self.current_animation].frames[self.index]['duration']
        self.anim_timer.activate()

    def update_image(self):
        if self.current_animation != "none":
            if self.anim_timer.complete:
                self.index += 1
                if self.index > len(self.animations[self.current_animation].frames) - 1:
                    self.index = 0
                self.anim_timer.duration = self.animations[self.current_animation].frames[self.index]['duration']
                self.anim_timer.activate()
                if self.on_change != None:
                    self.on_change()
                    
            elif (not self.anim_timer.active) and (self.current_animation != None):
                self.anim_timer.activate()

    def get_pos(self):
        return self.animations[self.current_animation].frames[self.index]['pos']
        

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
            if uniform == 'proj':
                self.program[uniform].write(self.image.scene.camera.proj_matrix.tobytes())

            elif uniform == 'view':
                self.program[uniform].write(self.image.scene.camera.view_matrix.tobytes())
            
            elif uniform == 'position':
                 self.program[uniform] = ((self.image.position.x + self.image.offset.x), -(self.image.position.y + self.image.offset.y)) 
            
            elif uniform == 'time':
                self.program[uniform] = pygame.time.get_ticks()
            
            elif uniform == 'tex':
                self.program[uniform] = self.image.scene.texture_locker.get_value(self.image.name)
            
            elif uniform == 'normal_tex':
                self.program[uniform] = self.image.scene.texture_locker.get_value(self.image.normal_name)

    def set_frag_uniforms(self):
        pass
    
    def set_vert_uniforms(self):
        pass

    def set_uniforms(self):
        #print(*self.program)
        self.set_generic_uniforms()
        self.set_vert_uniforms()
        self.set_frag_uniforms()

    def initialize(self, image: "Image"):
        self.image = image
        self.program = self.image.scene.glCtx.program(vertex_shader=self.vert, fragment_shader=self.frag)
    
class DefaultShader(Shader):
    def __init__(self, scene):
        super().__init__(scene, WORLD_VERT_SHADER, WORLD_FRAG_SHADER)

class Image:
    def __init__(self, texture: moderngl.Texture, name: str, scene: engine.core.Scene, size=(32,32), z=1, normal: moderngl.Texture = None):
        self.scene = scene
        self.name = name
        self.normal_name = self.name + "_normal"
        self.texture = texture
        self.size = size
        
        if normal == None:
            normal_surf = pygame.Surface(self.size, pygame.SRCALPHA)
            normal_surf.fill(DEFAULT_NORMAL)
            self.normal = surf_to_texture(normal_surf, self.scene.glCtx)
        else:
            self.normal = normal

        self.offset = vector(0, 0)
        self.position = vector(0, 0)
        self.z = z 

        self.set_shader(DefaultShader(self.scene))

    def set_shader(self, shader: Shader):
        self.shader = shader
        self.shader.initialize(self)
        x = self.size[0]
        y = self.size[1]
        # y values are fliped for pygame
        quad_buffer = self.scene.glCtx.buffer(data=array('f', [
            # position (x, y), uv coords (x,y)
            -1.0, 1.0, 0.0, 0.0, # top left
            x, 1.0, 1.0, 0.0, # top right
            -1.0, -y, 0.0, 1.0, # bottom left
            x, -y, 1.0, 1.0, # bottom right
        ]))

        self.render_object = self.scene.glCtx.vertex_array(self.shader.program, [(quad_buffer, '2f 2f',  'vert', 'texCoord')])

    def remove(self):
        self.texture.release()
        self.normal.release()


    def update(self, dt):
        pass
    
    def draw(self):
        albedo = self.scene.texture_locker.add(self.name)
        normal = self.scene.texture_locker.add(self.normal_name)

        self.texture.use(albedo)
        self.normal.use(normal)

        self.shader.set_uniforms()
        
        self.render_object.render(mode=moderngl.TRIANGLE_STRIP)

        self.scene.texture_locker.remove(self.name)
        self.scene.texture_locker.remove(self.normal_name)

class AnimatedShader(Shader):
    def __init__(self, scene):
        super().__init__(scene, WORLD_VERT_SHADER, ANIMATION_FRAG)
        self.image: AnimatedImage

    def set_frag_uniforms(self):
        albedo = self.image.scene.texture_locker.add(self.image.name)
        normal = self.image.scene.texture_locker.add(self.image.normal_name)

        self.image.animation_player.spritesheet.general.use(albedo)
        self.image.animation_player.spritesheet.normal.use(normal)

        self.program['albedo'] = albedo
        self.program['normal'] = normal

        self.program['spritesheet_size'] = self.image.animation_player.spritesheet.general.size
        self.program['img_size'] = self.image.size
        self.program['img_pos'] = self.image.animation_player.get_pos()

        self.image.scene.texture_locker.remove(self.image.name)
        self.image.scene.texture_locker.remove(self.image.normal_name)
        

class AnimatedImage(Image):
    def __init__(self, animation_player: AnimationPlayer, name: str, scene: engine.core.Scene, z=1):
        self.animation_player = animation_player
        self.scene = scene
        self.name = name
        self.normal_name = self.name + "_normal"
        self.size = vector(*self.animation_player.spritesheet.size)
        

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
    def __init__(self, name: str, images: list[Image],  scene: engine.core.Scene, z=1):
        self.images = images
        self.name = name
        self.scene = scene
        self._pos = vector(0, 0)
        
        self.z = z

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
        for image  in self.images:
            image.update(dt)

    def remove(self):
        for image in self.images:
            image.remove()

    def set_shader(self, shader):
        pass

class Camera(engine.core.Entity):
    def __init__(self, pos, scene, zoom=5):
        super().__init__(pos, scene)
        self.rotation = 0
        self.zoom = zoom
        self.camera_id = 1
        self.background_color = "#b4befe"

        self.update_view_matrix()
        self.update_projection_matrix()

    def on_resize(self):
        self.update_projection_matrix()

    def on_update(self, dt):
        self.update_projection_matrix()

    def on_draw(self):
        self.update_view_matrix()

    def update_projection_matrix(self):
        # Orthographic projection matrix
        width = self.scene.main.window_size[0]
        height = self.scene.main.window_size[1]
        left = -width / 2
        right = width / 2
        bottom = -height / 2
        top = height / 2
        near = -1.0
        far = 1.0

        proj_matrix = np.array([
            [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
            [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
            [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)

        scale_matrix = np.array([
            [self.zoom,  0.0,  0.0,  0.0],  # Scale X
            [0.0,  self.zoom,  0.0,  0.0],  # Scale Y
            [0.0,  0.0,  1.0,  0.0],  # Z remains unchanged
            [0.0,  0.0,  0.0,  1.0]   # Homogeneous coordinate
        ], dtype=np.float32)

        self.proj_matrix = np.dot(proj_matrix, scale_matrix)

    def update_view_matrix(self):
        # Translation matrix
        tx, ty = -self.position.x, self.position.y
        translation_matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [tx, ty, 0.0, 1.0]
        ], dtype=np.float32)

        # Rotation matrix (around the Z-axis)
        angle = math.radians(self.rotation)
        cos_theta = math.cos(angle)
        sin_theta = math.sin(angle)
        rotation_matrix = np.array([
            [cos_theta, -sin_theta, 0.0, 0.0],
            [sin_theta, cos_theta, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)

        # Combine translation and rotation
        self.view_matrix = np.dot(translation_matrix, rotation_matrix)

DEBUG_FRAG_SHADER = """
#version 330 core

in vec2 uv;
out vec4 f_color;

uniform sampler2D tex;

void main() {
    f_color = vec4(texture(tex, uv).rgb, 1.0);
}
"""



LIGHT_FRAG_SHADER = """
#version 330 core
#define MAX_LIGHTS 100

struct Light {
    vec2 position;
    vec3 color;
    float intensity;
    float radius;
};

struct SpotLight {
    vec2 position;
    vec2 direction;
    vec3 color;
    float angle;
    float intensity;
    float radius;
};

struct DirectionalLight {
    vec2 direction;
    vec3 color;
    float intensity;
};

uniform sampler2D albedo_texture;
uniform sampler2D normal_texture;

uniform vec2 screen_size;

uniform Light lights[MAX_LIGHTS];
uniform int light_count;

uniform SpotLight spotLights[MAX_LIGHTS];
uniform int spot_light_count;

uniform DirectionalLight dirLights[MAX_LIGHTS];
uniform int dir_light_count;

uniform vec3 global_light;

uniform mat4 view;
uniform mat4 proj;
uniform float zoom;

in vec2 uv;
out vec4 frag_color;

void main() {
    vec3 albedo = texture(albedo_texture, uv).rgb;
    vec3 normal = texture(normal_texture, uv).rgb;
    normal = normalize(normal * 2.0 - 1.0);


    // Process each light
    // Convert fragment position from screen space to NDC
    vec4 frag_pos_ndc = vec4((gl_FragCoord.xy / screen_size) * 2.0 - 1.0, 0.0, 1.0);

    // Transform from NDC to world space
    vec4 frag_pos_world = inverse(proj * view) * frag_pos_ndc;
    frag_pos_world /= frag_pos_world.w; // Perspective divide

    // Start with global ambient lighting
    vec3 lighting = global_light;

    // Process each light
    if (light_count > 0) {
        for (int i = 0; i < dir_light_count; i++) {
            vec3 light_vec = normalize(vec3(dirLights[i].direction, 1.0));
            float diff = max(dot(normal, light_vec), 0.0);

            lighting += dirLights[i].color * diff * dirLights[i].intensity;
        }

        for (int i = 0; i < spot_light_count; i++) {
            vec2 light_pos_world = spotLights[i].position;
            vec2 to_frag = normalize(frag_pos_world.xy - light_pos_world);
            vec2 spot_dir = normalize(spotLights[i].direction);

            // Calculate spotlight effect
            float angle_diff = dot(to_frag, spot_dir);
            float spot_effect = smoothstep(cos(spotLights[i].angle), cos(spotLights[i].angle * 0.9), angle_diff);

            // Compute attenuation
            float dist = length(light_pos_world - frag_pos_world.xy);
            if (dist > spotLights[i].radius) continue;
            float attenuation = 1.0 - (dist / spotLights[i].radius);
            attenuation = max(attenuation, 0.0);

            // Diffuse lighting
            vec3 light_vec = normalize(vec3(to_frag, 1.0));
            float diff = max(dot(normal, light_vec), 0.0);

            lighting += spotLights[i].color * diff * spotLights[i].intensity;
        }
        
        for (int i = 0; i < light_count; i++) {
            // Light position is already in world space
            vec2 light_pos_world = lights[i].position;

            // Compute world-space distance
            float dist = length(light_pos_world - frag_pos_world.xy);
            if (dist > lights[i].radius) continue;

            // Calculate lighting contribution
            vec2 light_dir = normalize(light_pos_world - frag_pos_world.xy);
            vec3 light_vec = normalize(vec3(light_dir, 1.0));
            float diff = max(dot(normal, light_vec), 0.0);
            float attenuation = 1.0 - (dist / lights[i].radius);
            attenuation = max(attenuation, 0.0);

            lighting += lights[i].color * diff * lights[i].intensity * attenuation;
        }
    }

    frag_color = vec4(albedo * lighting, 1.0);
}
"""

class DirectionalLight(engine.core.Entity):
    def __init__(self, scene: engine.core.Scene, color: str, intensity: int, angle: int):
        super().__init__(vector(0, 0), scene, vector(1, 1))
        self.data = {
            "intensity": intensity,
            "color": color,
            "angle": angle
        }

    @property 
    def intensity(self) -> float:
        return self.data['intensity']
    
    @intensity.setter
    def intensity(self, new):
        self.data['intensity'] = new
    
    @property 
    def color(self) -> str:
        return self.data['color']
    
    @color.setter
    def color(self, new):
        self.data['color'] = new
    
    @property
    def angle(self) -> float:
        return self.data['angle']

    @angle.setter
    def angle(self, new):
        self.data['angle'] = new
    
    def on_draw(self):
        self.scene.graphics.add_directional_light(self)

class PointLight(engine.core.Entity):
    def __init__(self, position, scene, radius: int, color: str, intensity: int):
        super().__init__(position, scene)

        self.data = {
            "intensity": intensity,
            "color": color,
            "radius": radius
        }

    
    @property 
    def intensity(self) -> float:
        return self.data['intensity']
    
    @intensity.setter
    def intensity(self, new):
        self.data['intensity'] = new
    
    @property 
    def color(self) -> str:
        return self.data['color']
    
    @color.setter
    def color(self, new):
        self.data['color'] = new
    
    @property
    def radius(self) -> float:
        return self.data['radius']

    @radius.setter
    def radius(self, new):
        self.data['radius'] = new

    def on_draw(self):
        self.scene.graphics.add_light(self)

class SpotLight(engine.core.Entity):
    def __init__(self, position, scene, radius: int, color: str, intensity: int, angle, direction):
        super().__init__(position, scene)

        self.data = {
            "intensity": intensity,
            "color": color,
            "radius": radius,
            "angle": angle,
            "direction": direction
        }

    @property 
    def intensity(self) -> float:
        return self.data['intensity']
    
    @intensity.setter
    def intensity(self, new):
        self.data['intensity'] = new
    
    @property 
    def color(self) -> str:
        return self.data['color']
    
    @color.setter
    def color(self, new):
        self.data['color'] = new
    
    @property
    def angle(self) -> float:
        return self.data['angle']

    @angle.setter
    def angle(self, new):
        self.data['angle'] = new

    @property
    def direction(self) -> vector:
        return self.data['direction']

    @direction.setter
    def direction(self, new):
        self.data['direction'] = new

    @property
    def radius(self) -> vector:
        return self.data['radius']

    @radius.setter
    def radius(self, new):
        self.data['radius'] = new


    def on_draw(self):
        self.scene.graphics.add_spotlight(self)

shadow_vert_shader = """
#version 330 core

in vec2 vert;
in vec2 texCoord;
out vec2 uv;

void main() {
    uv = texCoord;

    gl_Position = vec4(vert, 0.0, 1.0);
}
"""

shadow_frag_shader = """

"""

class ShadowCaster(engine.core.Component):
    def __init__(self, entity: engine.core.Entity):
        super().__init__(entity)
        self.program = self.entity.scene.glCtx.program(shadow_vert_shader, shadow_frag_shader)
        
        x = self.entity.size[0]
        y = self.entity.size[1]

        # y values are fliped for pygame
        quad_buffer = self.entity.scene.glCtx.buffer(data=array('f', [
            # position (x, y), uv coords (x,y)
            -1.0, 1.0, 0.0, 0.0, # top left
            x, 1.0, 1.0, 0.0, # top right
            -1.0, -y, 0.0, 1.0, # bottom left
            x, -y, 1.0, 1.0, # bottom right
        ]))

        self.render_object = self.entity.scene.glCtx.vertex_array(self.program, [(quad_buffer, '2f 2f',  'vert', 'texCoord')])

        self.position = self.entity.position

    def update(self, dt):
        self.position = self.entity.position

    def draw(self, lights):
        for light in lights:
            # Set the color for light[i]
            self.lighting_program[f"lights[{i}].color"] = light.color
            
            # Set the intensity for light[i]
            self.lighting_program[f"lights[{i}].intensity"] = light.intensity
            
            # Set the position for light[i]
            self.lighting_program[f"lights[{i}].position"] = light.position
            
            # Set the radius for light[i]
            self.lighting_program[f"lights[{i}].radius"] = light.radius
            i+=1

        self.render_object.render()

CLEAR_FRAG_SHADER = """
#version 330 core

uniform vec3 normal_color;
uniform vec3 albedo_color;

out vec4 frag_albedo;
out vec4 frag_normal;

void main() {
    frag_albedo = vec4(albedo_color, 1.0);
    frag_normal = vec4(normal_color, 1.0);
}
"""

RENDERING_MODES = ["full",  "general", "normal", "light"]

class PostProcessLayer:
    def __init__(self, scene: engine.core.Scene, frag: str):
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
            if uniform == 'albedo_tex':
                self.program[uniform] = self.scene.texture_locker.get_value(self.scene.graphics.albedo_key)
            elif uniform == 'normal_tex':
                self.program[uniform] = self.scene.texture_locker.get_value(self.scene.graphics.normal_key)
            elif uniform == 'lighting_tex':
                self.program[uniform] = self.scene.texture_locker.get_value(self.scene.graphics.lighting_key)
            elif uniform == 'post_tex':
                self.program[uniform] = self.scene.texture_locker.get_value(self.scene.graphics.post_key)
            elif uniform == 'time':
                self.program[uniform] = pygame.time.get_ticks()

    def draw(self):
        self.set_uniforms()
        self.vao.render()

class Graphics:
    def __init__(self, scene: engine.core.Scene, ctx: moderngl.Context):
        self.ctx = ctx
        self.scene = scene
        
        self.rendering_mode_cooldown = engine.core.Timer(5)
        self.rendering_mode_cooldown.activate()

        self.albedo_key = "_ENGINE_albedo"
        self.normal_key = "_ENGINE_normal"
        self.shadow_key = "_ENGINE_shadow"
        self.lighting_key = "_ENGINE_lighting"
        self.post_key = "_ENGINE_post"
        self.ui_key = "_ENGINE_ui"

        self.background_normal = (0.5, 0.5, 1.0)
        
        self.scene.texture_locker.add(self.albedo_key)
        self.scene.texture_locker.add(self.normal_key)
        self.scene.texture_locker.add(self.shadow_key)
        self.scene.texture_locker.add(self.ui_key)
        self.scene.texture_locker.add(self.lighting_key)
        self.scene.texture_locker.add(self.post_key)
        self.rendering_mode = "full"

        self.general_images: list[Image] = []
        self.shadow_casters: list[ShadowCaster] = []
        
        self.post_layers: list[PostProcessLayer] = []

        self.lights: list[PointLight] = []
        self.directional_lights: list[DirectionalLight] = []
        self.spot_lights: list[SpotLight] = []
        self.global_light = "#505050" 
        self.lighting_program = self.ctx.program(uv_vert_shader, LIGHT_FRAG_SHADER)
        

        self.clear_program = self.ctx.program(empty_vert_shader, CLEAR_FRAG_SHADER)

        self.ui_program = self.ctx.program(uv_vert_shader, texture_frag_shader)

        self.lighting_program["albedo_texture"] = self.scene.texture_locker.get_value(self.albedo_key)
        self.lighting_program["normal_texture"] = self.scene.texture_locker.get_value(self.normal_key)
        #self.lighting_program["shadow_texture"] = self.scene.texture_locker.get_value(self.shadow_key)

        self.screen_program = self.ctx.program(uv_vert_shader, texture_frag_shader)

        self.ui_program["tex"] = self.scene.texture_locker.get_value(self.ui_key)


        self.clear_vao = create_fullscreen_quad(self.ctx, self.clear_program)
        self.lighting_vao = create_fullscreen_quad(self.ctx, self.lighting_program)
        self.ui_vao = create_fullscreen_quad(self.ctx, self.ui_program)
        self.screen_vao = create_fullscreen_quad(self.ctx, self.screen_program)

        self.fonts: dict[str, freetype.Face] = {}
        self.on_resize()

    def on_resize(self):
        width = self.scene.main.window_size[0]
        height = self.scene.main.window_size[1]

        self.general_framebuffer = self.ctx.framebuffer(
            color_attachments=[
                self.ctx.texture((width, height), 4),  # Albedo
                self.ctx.texture((width, height), 4),  # Normal
            ]
        )

        self.shadow_framebuffer = self.ctx.framebuffer(
            color_attachments=[
                self.ctx.texture((width, height), 1)
            ]
        )

        self.lighting_framebuffer = self.ctx.framebuffer(
            color_attachments=[
                self.ctx.texture((width, height), 3)
            ]
        )

        self.post_framebuffer = self.ctx.framebuffer(
            color_attachments=[
                self.ctx.texture((width, height), 3)
            ]
        )

    def add_general(self, image): # draws a general image (actors, objects, etc.)
        self.general_images.append(image)

    def add_light(self, light):
        self.lights.append(light)
    
    def add_directional_light(self, light):
        self.directional_lights.append(light)

    def add_spotlight(self, light):
        self.spot_lights.append(light)

    def add_shadow(self, image):
        self.shadow_casters.append(image)

    def reset(self):
        self.general_images.clear()
        self.lights.clear()
        self.directional_lights.clear()
        self.spot_lights.clear()

    def add_font(self, key, name):
        """Creates a font that can be used to render text. Must be a TTF file"""
        path = f"game/assets/graphics/fonts/{name}.ttf"
        if os.path.exists(path):
            font = freetype.Face(path)
            self.fonts[key] = font
        else:
            print(f"Font with name: {name} doesn't exsist.")

    def get_font(self, font_name: str):
        font = self.fonts['default']
        if font_name in self.fonts.keys():
            font = self.fonts[font_name]

        return font

    def render(self):
        if self.rendering_mode == "full":
            self.draw_general()
            self.draw_lighting()
            self.draw_post_processing()
            self.draw_screen()

        if self.rendering_mode == 'light':
            self.draw_general()
            self.draw_lighting()
            self.draw_screen()

        if self.rendering_mode == "general":
            self.draw_general()
            self.draw_screen()

        if self.rendering_mode == "normal":
            self.draw_general()
            self.draw_screen()
    
    def draw_ui(self):
        self.ui_program['tex'] = self.scene.texture_locker.get_value(self.ui_key)
        self.ui_vao.render()

    def draw_post_processing(self):
        self.post_framebuffer.use()
        
        self.lighting_framebuffer.color_attachments[0].use(self.scene.texture_locker.get_value(self.post_key))

        for layer in self.post_layers:
            layer.draw()

            self.post_framebuffer.color_attachments[0].use(self.scene.texture_locker.get_value(self.post_key))
            

    def draw_general(self):
        self.general_framebuffer.use()  # Render to the G-buffer

        bg = hex_to_rgb(self.scene.camera.background_color)
        self.clear_program['albedo_color'] = bg
        self.clear_program['normal_color'] = self.background_normal
        self.clear_vao.render()

        self.general_images.sort(key=lambda img: img.z)
        for image in self.general_images:
            image.draw()

        # Bind G-buffer textures
        self.general_framebuffer.color_attachments[0].use(self.scene.texture_locker.get_value(self.albedo_key))  # Albedo
        self.general_framebuffer.color_attachments[1].use(self.scene.texture_locker.get_value(self.normal_key))  # Normal

    def draw_lighting(self):
        
        self.lighting_framebuffer.use()  # Switch to rendering on the screen

        self.lighting_program['global_light'] = hex_to_rgb(self.global_light)
        self.lighting_program["view"].write(self.scene.camera.view_matrix)
        self.lighting_program["proj"].write(self.scene.camera.proj_matrix) 
        #self.lighting_program["zoom"] = self.scene.camera.zoom

        self.lighting_program["light_count"].value = len(self.lights)
        self.lighting_program["dir_light_count"] = len(self.directional_lights)
        self.lighting_program["spot_light_count"] = len(self.spot_lights)
        
        i = 0
        for light in self.directional_lights:
            self.lighting_program[f"dirLights[{i}].color"] = hex_to_rgb(light.color)
            self.lighting_program[f"dirLights[{i}].direction"] = light.direction
            self.lighting_program[f"dirLights[{i}].intensity"] = light.intensity
            
            i+=1
        
        i = 0
        for light in self.spot_lights:
            self.lighting_program[f"spotLights[{i}].color"] = hex_to_rgb(light.color)
            self.lighting_program[f"spotLights[{i}].direction"] = (math.sin(light.direction), math.cos(light.direction))
            self.lighting_program[f"spotLights[{i}].intensity"] = light.intensity
            self.lighting_program[f"spotLights[{i}].radius"] = light.radius
            self.lighting_program[f"spotLights[{i}].angle"] = light.angle
            self.lighting_program[f"spotLights[{i}].position"] = (light.position.x, -light.position.y)
            i+=1
 
        i = 0
        for light in self.lights:
            self.lighting_program[f"lights[{i}].color"] = hex_to_rgb(light.color)
            self.lighting_program[f"lights[{i}].intensity"] = light.intensity
            self.lighting_program[f"lights[{i}].position"] = (light.position.x, -light.position.y)
            self.lighting_program[f"lights[{i}].radius"] = light.radius
            i+=1

        self.lighting_program["screen_size"].value = self.scene.main.window_size
        self.lighting_framebuffer.color_attachments[0].use(self.scene.texture_locker.get_value(self.lighting_key))  # Normal

        # Render a fullscreen quad to apply lighting
        self.lighting_vao.render(moderngl.TRIANGLES)
    
    def draw_screen(self):
        self.ctx.screen.use()

        if self.rendering_mode == 'full':
            self.screen_program['tex'] = self.scene.texture_locker.get_value(self.post_key)          
        
            self.screen_vao.render()

        if self.rendering_mode == 'light':
            self.screen_program['tex'] = self.scene.texture_locker.get_value(self.lighting_key)
        
            self.screen_vao.render()
        
        if self.rendering_mode == 'general':
            self.screen_program['tex'] = self.scene.texture_locker.get_value(self.albedo_key)
            self.screen_vao.render()

        if self.rendering_mode == 'normal':
            self.screen_program['tex'] = self.scene.texture_locker.get_value(self.normal_key)
            self.screen_vao.render()



    def check_hotkeys(self):
        if self.scene.input.check_action("CYCLE_RENDERING_MODE") and self.rendering_mode_cooldown.complete:
            i = RENDERING_MODES.index(self.rendering_mode) 
            i += 1
            if i > len(RENDERING_MODES) - 1:
                i = 0
            self.rendering_mode = RENDERING_MODES[i]
            if self.rendering_mode != "wireframe":
                gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)

            self.rendering_mode_cooldown.activate()

    def update(self, dt):
        self.rendering_mode_cooldown.update(dt)
        self.check_hotkeys()

    def draw(self):
        self.render()
        self.reset()

