from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.graphics.image import Image 
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.graphics.renderer import Renderer

RENDERING_MODES = ["full", "albedo", "lighting", "normal", "emission"]

class GraphicsManager:
    """
    The graphics manager.
    
    :param main: The main object.
    :type main: Main
    """
    def __init__(self, main: 'Main', renderer: 'Renderer'):
        self.main = main
        self.rendering_mode = "full"
        self.renderer = renderer
        self.images: list['Image'] = []

    def draw(self, camera: 'Camera'):
        """
        Draws the scene from the perspective of a camera.

        :pararm camera: The camera that the scene will be drawn from.
        :type camera: Camera
        """
        
        for image in self.images:
            self.renderer.draw_image(image, camera)
    

# class _GraphicsManager:
#     def __init__(self, scene: engine.actor.Scene, ctx: moderngl.Context):
#         self.ctx = ctx
#         self.scene = scene

#         self.rendering_mode_cooldown = engine.actor.Timer(0.5)
#         self.rendering_mode_cooldown.activate()

#         self.albedo_key = "_ENGINE_albedo"
#         self.normal_key = "_ENGINE_normal"
#         self.shadow_key = "_ENGINE_shadow"
#         self.lighting_key = "_ENGINE_lighting"
#         self.post_key = "_ENGINE_post"

#         self.background_normal = Color((0.5, 0.5, 1.0))

#         self.scene.texture_locker.add(self.albedo_key)
#         self.scene.texture_locker.add(self.normal_key)
#         self.scene.texture_locker.add(self.shadow_key)
#         self.scene.texture_locker.add(self.lighting_key)
#         self.scene.texture_locker.add(self.post_key)
#         self.rendering_mode = "general"

#         self.general_images: list[Image] = []

#         self.post_layers: list[PostProcessLayer] = []

#         self.lights: list[PointLight] = []
#         self.directional_lights: list[DirectionalLight] = []
#         self.spot_lights: list[SpotLight] = []
#         self.global_light = Color("#505050")
#         self.lighting_program = self.ctx.program(
#             self.scene.files.load_text("engine/shader/graphics/uv.vert"),
#             self.scene.files.load_text("engine/shader/graphics/light.frag"),
#         )

#         self.clear_program = self.ctx.program(
#             self.scene.files.load_text("engine/shader/graphics/empty.vert"),
#             self.scene.files.load_text("engine/shader/graphics/clear.frag"),
#         )

#         self.lighting_program["albedo_texture"] = self.scene.texture_locker.get_value(
#             self.albedo_key
#         )
#         self.lighting_program["normal_texture"] = self.scene.texture_locker.get_value(
#             self.normal_key
#         )
#         # self.lighting_program["shadow_texture"] = self.scene.texture_locker.get_value(self.shadow_key)

#         self.screen_program = self.ctx.program(
#             self.scene.files.load_text("engine/shader/graphics/uv.vert"),
#             self.scene.files.load_text("engine/shader/graphics/texture.frag"),
#         )

#         self.clear_vao = create_fullscreen_quad(self.ctx, self.clear_program)
#         self.lighting_vao = create_fullscreen_quad(self.ctx, self.lighting_program)
#         self.screen_vao = create_fullscreen_quad(self.ctx, self.screen_program)

#         self.on_resize()

#     def on_resize(self):
#         width = self.scene.main.window_size[0]
#         height = self.scene.main.window_size[1]

#         self.general_framebuffer = self.ctx.framebuffer(
#             color_attachments=[
#                 self.ctx.texture((width, height), 4),  # Albedo
#                 self.ctx.texture((width, height), 4),  # Normal
#             ]
#         )

#         self.shadow_framebuffer = self.ctx.framebuffer(
#             color_attachments=[self.ctx.texture((width, height), 1)]
#         )

#         self.lighting_framebuffer = self.ctx.framebuffer(
#             color_attachments=[self.ctx.texture((width, height), 3)]
#         )

#         self.post_framebuffer = self.ctx.framebuffer(
#             color_attachments=[self.ctx.texture((width, height), 3)]
#         )

#     def add_general(self, image):  # draws a general image (actors, objects, etc.)
#         self.general_images.append(image)

#     def add_light(self, light):
#         self.lights.append(light)

#     def add_directional_light(self, light):
#         self.directional_lights.append(light)

#     def add_spotlight(self, light):
#         self.spot_lights.append(light)

#     def add_shadow(self, image):
#         self.shadow_casters.append(image)

#     def reset(self):
#         self.general_images.clear()
#         self.lights.clear()
#         self.directional_lights.clear()
#         self.spot_lights.clear()

#     def cycle_rendering_mode(self):
#         if self.rendering_mode_cooldown.complete:
#             i = RENDERING_MODES.index(self.rendering_mode)
#             i += 1
#             if i >= len(RENDERING_MODES):
#                 i = 0
#             self.rendering_mode = RENDERING_MODES[i]
#             self.rendering_mode_cooldown.activate()

#     def get_font(self, font_name: str):
#         font = self.fonts["default"]
#         if font_name in self.fonts.keys():
#             font = self.fonts[font_name]

#         return font

#     def render(self):
#         if self.rendering_mode == "full":
#             self.draw_general()
#             self.draw_lighting()
#             self.draw_post_processing()
#             self.draw_screen()

#         if self.rendering_mode == "light":
#             self.draw_general()
#             self.draw_lighting()
#             self.draw_screen()

#         if self.rendering_mode == "general":
#             self.draw_general()
#             self.draw_screen()

#         if self.rendering_mode == "normal":
#             self.draw_general()
#             self.draw_screen()

#         self.scene.ui.draw()

#     def draw_post_processing(self):
#         self.post_framebuffer.use()

#         self.lighting_framebuffer.color_attachments[0].use(
#             self.scene.texture_locker.get_value(self.post_key)
#         )

#         for layer in self.post_layers:
#             layer.draw()

#             self.post_framebuffer.color_attachments[0].use(
#                 self.scene.texture_locker.get_value(self.post_key)
#             )

#     def draw_general(self):
#         self.general_framebuffer.use()  # Render to the G-buffer

#         bg = self.scene.camera.background_color.float_normalized
#         self.clear_program["albedo_color"] = bg
#         self.clear_program["normal_color"] = self.background_normal.float_normalized
#         self.clear_vao.render()

#         self.general_images.sort(key=lambda img: img.z)
#         for image in self.general_images:
#             image.draw()

#         # Bind G-buffer textures
#         self.general_framebuffer.color_attachments[0].use(
#             self.scene.texture_locker.get_value(self.albedo_key)
#         )  # Albedo
#         self.general_framebuffer.color_attachments[1].use(
#             self.scene.texture_locker.get_value(self.normal_key)
#         )  # Normal

#     def draw_lighting(self):
#         self.lighting_framebuffer.use()  # Switch to rendering on the screen

#         self.lighting_program["global_light"] = self.global_light.float_normalized
#         self.lighting_program["view"].write(self.scene.camera.view_matrix)
#         self.lighting_program["proj"].write(self.scene.camera.proj_matrix)
#         # self.lighting_program["zoom"] = self.scene.camera.zoom

#         self.lighting_program["light_count"].value = len(self.lights)
#         self.lighting_program["dir_light_count"] = len(self.directional_lights)
#         self.lighting_program["spot_light_count"] = len(self.spot_lights)

#         i = 0
#         for light in self.directional_lights:
#             if i >= 19:
#                 break
#             self.lighting_program[f"dirLights[{i}].color"] = (
#                 light.color.float_normalized
#             )
#             self.lighting_program[f"dirLights[{i}].direction"] = light.direction
#             self.lighting_program[f"dirLights[{i}].intensity"] = light.intensity

#             i += 1

#         i = 0
#         for light in self.spot_lights:
#             if i >= 19:
#                 break
#             self.lighting_program[f"spotLights[{i}].color"] = (
#                 light.color.float_normalized
#             )
#             self.lighting_program[f"spotLights[{i}].direction"] = (
#                 math.sin(light.direction),
#                 math.cos(light.direction),
#             )
#             self.lighting_program[f"spotLights[{i}].intensity"] = light.intensity
#             self.lighting_program[f"spotLights[{i}].radius"] = light.radius
#             self.lighting_program[f"spotLights[{i}].angle"] = light.angle
#             self.lighting_program[f"spotLights[{i}].position"] = (
#                 light.position.x,
#                 -light.position.y,
#             )
#             i += 1

#         i = 0
#         for light in self.lights:
#             if i >= 19:
#                 break
#             self.lighting_program[f"lights[{i}].color"] = light.color.float_normalized
#             self.lighting_program[f"lights[{i}].intensity"] = light.intensity
#             self.lighting_program[f"lights[{i}].position"] = (
#                 light.position.x,
#                 -light.position.y,
#             )
#             self.lighting_program[f"lights[{i}].radius"] = light.radius
#             i += 1

#         self.lighting_program["screen_size"].value = self.scene.main.window_size
#         self.lighting_framebuffer.color_attachments[0].use(
#             self.scene.texture_locker.get_value(self.lighting_key)
#         )  # Normal

#         # Render a fullscreen quad to apply lighting
#         self.lighting_vao.render(moderngl.TRIANGLES)

#     def draw_screen(self):
#         self.ctx.screen.use()

#         if self.rendering_mode == "full":
#             self.screen_program["tex"] = self.scene.texture_locker.get_value(
#                 self.post_key
#             )

#             self.screen_vao.render()

#         if self.rendering_mode == "light":
#             self.screen_program["tex"] = self.scene.texture_locker.get_value(
#                 self.lighting_key
#             )

#             self.screen_vao.render()

#         if self.rendering_mode == "general":
#             self.screen_program["tex"] = self.scene.texture_locker.get_value(
#                 self.albedo_key
#             )
#             self.screen_vao.render()

#         if self.rendering_mode == "normal":
#             self.screen_program["tex"] = self.scene.texture_locker.get_value(
#                 self.normal_key
#             )
#             self.screen_vao.render()

#     def update(self, dt):
#         self.rendering_mode_cooldown.update(dt)

#     def draw(self):
#         self.render()
#         self.reset()
