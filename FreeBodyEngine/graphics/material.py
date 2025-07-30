from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.fbusl.injector import Injector
from FreeBodyEngine.graphics.fbusl import fbusl_error
from FreeBodyEngine.graphics.fbusl.semantic import FuncCall
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine import get_main,get_service
from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine import warning
import numpy as np
from enum import Enum, auto
from FreeBodyEngine.math import Transform, Vector3, Vector
import sys
from FreeBodyEngine.utils import abstractmethod
from typing import Literal, TYPE_CHECKING


if TYPE_CHECKING:
    from FreeBodyEngine.core.camera import Camera


class PropertyType(Enum):
    
    FLOAT = auto()
    INT = auto()
    
    COLOR_R = auto()
    COLOR_RG = auto()
    COLOR_RGB = auto()
    COLOR_RGBA = auto()

    TEXTURE = auto()
    
    



class MaterialInjector(Injector):
    def __init__(self, shader_type, file_path, material: 'Material'):
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
    def __init__(self, data: dict, property_definitions: dict[str, str], injector: Injector = MaterialInjector):
        self.data = data
        self.properties = self.parse_properties(property_definitions)

        shader = data.get('shader', {})
        frag_source = shader.get('frag','engine/shader/default_shader.fbfrag')
        vert_source = shader.get('vert', 'engine/shader/default_shader.fbvert')
        self.shader: Shader = get_service('renderer').load_shader(get_service('files').load_data(vert_source), get_service('files').load_data(frag_source), injector) 

    def __getattribute__(self, name):
        if name not in ('data', 'properties'):
            props = object.__getattribute__(self, "__dict__").get("properties", None)
            if props and name in props:
                return props[name]
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name not in ('data', 'properties'):
            props = object.__getattribute__(self, "__dict__").get("properties", None)
            if props and name in props:
                props[name] = value
                return
        object.__setattr__(self, name, value)

    def parse_properties(self, property_definitions):
        properties = {}
        for data in self.data:
            if data in property_definitions:
                val = self.data[data]

                properties[data] = self.parse_property_val(val, data, property_definitions)
        
        return properties

    def parse_property_val(self, val: any, property, property_definitions):
        type = property_definitions[property]
        if type in (PropertyType.COLOR_RGBA, PropertyType.COLOR_RGB):
            if isinstance(val, str):
                if val.startswith('#'):
                    return Color(val)
                else:
                    warning(f"Couldn't parse material color value, '{property}' is a string that doesn't contain a hex color.")
            else:
                if len(val) >= 2 and len(val) <= 4:
                    correct_type = True
                    for v in val:
                        if isinstance(v, (int, float)):
                            correct_type = False
                            break
                    if correct_type:
                        return Color(val)
                    else:
                        warning(f"Couldn't parse material color value, '{property}' did not contain numbers.")
                else:
                    warning(f"Couldn't parse material color value, '{property}' only contained {len(val)} values, minimum of 3 is required.")

    
    def use(self, transform: 'Transform', camera: 'Camera'):
        for material_property in self.properties:

            val = self.properties[material_property]
            if isinstance(val, Color):
                self.shader.set_uniform(f"{material_property.capitalize()}_Color", val)
                self.shader.set_uniform(f"{material_property.capitalize()}_useTexture", False)
            else:
                self.shader.set_uniform(f"{material_property.capitalize()}_Texture", val)
                self.shader.set_uniform(f"{material_property.capitalize()}_useTexture", True)
                self.shader.set_uniform("Albedo_UVRect", val.texture.uv_rect)

        self.shader.set_uniform('model', transform.model)
        self.shader.set_uniform('view', camera.view_matrix)
        self.shader.set_uniform('proj', camera.proj_matrix)
        
        self.shader.use()
        