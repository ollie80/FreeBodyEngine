from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.fbusl.injector import Injector
from FreeBodyEngine.graphics.fbusl import fbusl_error
from FreeBodyEngine.graphics.fbusl.semantic import FuncCall
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine import get_main,get_service
from FreeBodyEngine.graphics.image import Image
import numpy as np

from FreeBodyEngine.math import Transform, Vector3, Vector
import sys
from typing import Literal, TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.camera import Camera2D


class MaterialInjector(Injector):
    def __init__(self, shader_type, file_path):
        super().__init__(shader_type, file_path)

    def get_builtins(shader_type):
        if shader_type == "frag":
            return {"vars": {"ALBEDO": {"type": "sampler2D"}, "NORMAL": {"type": "sampler2D"}, "EMMISION": {"type": "sampler2D"}, "ROUGHNESS": {"type": "sampler2D"}, "METALLIC": {"type": "sampler2D"}}}
        else:
            return {'vars': {"WORLD_POS": {"type": "vec4"}}}
        
    def inject_main_frag(self, main: FuncDecl):
        defaults = {"albedo": 'vec4', "normal": 'vec4', 'emmision': 'vec4', 'roughness': 'float', 'metallic': 'float'}
        
        for name, type in reversed(defaults.items()):
            self.tree.children.insert(1, UniformDecl(0, f'{name.capitalize()}_useTexture', 'bool', None))
            self.tree.children.insert(1, UniformDecl(0, f'{name.capitalize()}_Texture', 'sampler2D', None))
            self.tree.children.insert(1, UniformDecl(0, f'{name.capitalize()}_Color', f'{type}', None))

        remaining_defaults = set(defaults.keys())

        for node in main.body:
            if isinstance(node, Set):
                if isinstance(node, Set) and node.ident.name in remaining_defaults:
                    remaining_defaults.remove(node.ident.name)

        for name in defaults:
            self.tree.children.insert(1, OutputDecl(0, f'{name}', f'{defaults[name]}', None))
            main.body.append(Set(main.pos, Identifier(main.pos, name), Call(main.pos, "texture", [Arg(main.pos, Identifier(main.pos, f"{name.upper()}")), Arg(main.pos, Identifier(main.pos, "uv"))])))
            
        builtins = self.__class__.get_builtins('frag').get('vars', {})
        self.replace_texture_calls(main, builtins, defaults)


class Material:
    def __init__(self, data: dict, injector: Injector = MaterialInjector):
        self.albedo: Color | Image = Color(data.get('albedo', '#FFFFFFFF'))
        self.normal: Color | Image  = Color(data.get('normal', '#8080FFFF'))
        self.emmision: Color | Image  = Color(data.get('emmision', '#00000000'))
        self.roughness: float | Image  = data.get('roughness', 1.0)
        self.metallic: float | Image = data.get('metallic', 0.0)
        self.opactiy: float | Image = data.get('opacity', 1.0)
        
        self._render_mode = data.get('render_mode', 'lit') # cannot be change
        shader = data.get('shader', {})
        frag_source = shader.get('frag','engine/shader/default_shader.fbfrag')
        vert_source = shader.get('vert', 'engine/shader/default_shader.fbvert')
        self.shader: Shader = get_service('renderer').load_shader(get_service('files').load_data(vert_source), get_service('files').load_data(frag_source), injector) 

    @property
    def render_mode(self) -> Literal["lit", "unlit", "wireframe"]:
        return self._render_mode

    def set_uniform(self, name: str, val: any):
        self.shader.set_uniform(name, val)

    def get_uniform(self, name: str):
        return self.shader.get_uniform(name)
    
    def _set_default_uniforms(self, transform: Transform, camera: 'Camera2D'):
        #frag
        if isinstance(self.albedo, Color):
            self.set_uniform("Albedo_Color", self.albedo.float_normalized_a)
            self.set_uniform("Albedo_useTexture", False)
        else:
            self.set_uniform("Albedo_Texture", self.albedo)
            self.set_uniform("Albedo_useTexture", True)
            self.set_uniform("Albedo_UVRect", self.albedo.texture.uv_rect)

        if isinstance(self.normal, Color):
            self.set_uniform("Normal_Color", self.normal.float_normalized_a)
            self.set_uniform("Normal_useTexture", False)
        else:
            self.set_uniform("Normal_Texture", self.normal)
            self.set_uniform("Normal_useTexture", True)
        
        if isinstance(self.emmision, Color):
            self.set_uniform("Emmision_Color", self.emmision.float_normalized_a)
            self.set_uniform("Emmision_useTexture", False)
        else:
            self.set_uniform("Emmision_Texture", self.emmision)
            self.set_uniform("Emmision_useTexture", True)
        
        if isinstance(self.roughness, float):
            self.set_uniform("Roughness_Color", self.roughness)
            self.set_uniform("Roughness_useTexture", False)
        else:
            self.set_uniform("Roughness_Texture", self.roughness)
            self.set_uniform("Roughness_useTexture", True)
        
        if isinstance(self.metallic, float):
            self.set_uniform("Metallic_Color", self.metallic)
            self.set_uniform("Metallic_useTexture", False)
        else:
            self.set_uniform("Metallic_Texture", self.metallic)
            self.set_uniform("Metallic_useTexture", True)
            self.set_uniform("Metallic_UVRect", self.metallic.uv_rect)
        
        #vert
        self.set_uniform('model', transform.model)
        self.set_uniform('view', camera.view_matrix)
        self.set_uniform('proj', camera.proj_matrix)

    def use(self, transform: Transform, camera: 'Camera2D'):
        """Must be called before drawing."""
        self._set_default_uniforms(transform, camera)
        
