from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.core.main import Main
    from FreeBodyEngine.core.camera import Camera
    from FreeBodyEngine.graphics.renderer import Renderer

class Image:
    pass
# class Image:
#     def __init__(
#         self,
#         texture: moderngl.Texture,
#         name: str,
#         scene: engine.actor.Scene,
#         size=(32, 32),
#         z=1,
#         normal: moderngl.Texture = None,
#     ):
#         self.scene = scene
#         self.name = name
#         self.normal_name = self.name + "_normal"
#         self.texture = texture
#         self.size = size

#         if normal == None:
#             normal_surf = pygame.Surface(self.size, pygame.SRCALPHA)
#             normal_surf.fill(DEFAULT_NORMAL)
#             self.normal = surf_to_texture(normal_surf, self.scene.glCtx)
#         else:
#             self.normal = normal

#         self.offset = vector(0, 0)
#         self.position = vector(0, 0)
#         self.z = z

#         self.set_shader(DefaultShader(self.scene))

#     def set_shader(self, shader: Shader):
#         self.shader = shader
#         self.shader.initialize(self)
#         x = self.size[0]
#         y = self.size[1]
#         # y values are fliped for pygame
#         quad_buffer = self.scene.glCtx.buffer(
#             data=array(
#                 "f",
#                 [
#                     # position (x, y), uv coords (x,y)
#                     -1.0,
#                     1.0,
#                     0.0,
#                     0.0,  # top left
#                     x,
#                     1.0,
#                     1.0,
#                     0.0,  # top right
#                     -1.0,
#                     -y,
#                     0.0,
#                     1.0,  # bottom left
#                     x,
#                     -y,
#                     1.0,
#                     1.0,  # bottom right
#                 ],
#             )
#         )

#         self.render_object = self.scene.glCtx.vertex_array(
#             self.shader.program, [(quad_buffer, "2f 2f", "vert", "texCoord")]
#         )

#     @property
#     def center(self):
#         return self.position + vector(self.size[0] / 2, self.size[1] / 2)

#     @center.setter
#     def center(self, new):
#         self.position = new - vector(self.size[0] / 2, self.size[1] / 2)

#     def remove(self):
#         self.texture.release()
#         self.normal.release()

#     def update(self, dt):
#         pass

#     def draw(self):
#         albedo = self.scene.texture_locker.add(self.name)
#         normal = self.scene.texture_locker.add(self.normal_name)
#         self.texture.use(albedo)
#         self.normal.use(normal)

#         self.shader.set_uniforms()

#         self.render_object.render(mode=moderngl.TRIANGLE_STRIP)

#         self.scene.texture_locker.remove(self.name)
#         self.scene.texture_locker.remove(self.normal_name)

