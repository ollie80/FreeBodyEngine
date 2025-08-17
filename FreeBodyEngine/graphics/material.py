from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.fbusl.injector import Injector
from FreeBodyEngine.graphics.fbusl import fbusl_error
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine import get_main,get_service
from FreeBodyEngine.graphics.image import Image
from FreeBodyEngine.graphics.texture import Texture
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
    def __init__(self, material: 'Material'):
        super().__init__()
        self.material = material
        self.mat_properties = {}

    def parse_property(self, property: PropertyType):
        if property == PropertyType.COLOR_R:
            return 'float'
        if property == PropertyType.COLOR_RG:
            return 'vec2'
        if property == PropertyType.COLOR_RGB:
            return 'vec3'
        if property == PropertyType.COLOR_RGBA:
            return 'vec4'

    def get_builtins(self):
        if self.shader_type == "vert":
            return {} 
        else:
            builtins = {'vars': {}}

            for property in self.material.property_definitions:
                self.mat_properties[property] = self.parse_property(self.material.property_definitions[property])
                builtins['vars'][property.upper()] = self.parse_property(self.material.property_definitions[property])
            return builtins

    def pre_generation_inject(self):
        if self.shader_type == 'frag':
            self.inject_frag()
        return self.tree

    def inject_frag(self):
        main = self.find_main_function()

        for property in self.mat_properties:
            tex_nodes = self.find_nodes('name', property.upper())
            if len(tex_nodes) == 0:
                main.body.append(Set(0, Identifier(0, property), Identifier(0, property.upper())))
            
            self.tree.children.insert(0, UniformDecl(0, Identifier(0, f'{property.capitalize()}_Texture'), Type(0, Identifier(0, 'sampler2D')), None))
            self.tree.children.insert(0, UniformDecl(0, Identifier(0, f'{property.capitalize()}_Color'), Type(0, Identifier(0, 'vec4')), None))
            self.tree.children.insert(0, UniformDecl(0, Identifier(0, f'{property.capitalize()}_UVRect'), Type(0, Identifier(0, 'vec4')), None))
            self.tree.children.insert(0, UniformDecl(0, Identifier(0, f'{property.capitalize()}_useTexture'), Type(0, Identifier(0, 'bool')), None))

            tex_nodes = self.find_nodes('name', property.upper())

            for node in tex_nodes:
                parent = self.find_parent(node)
                custom_sample_pos = False 

                if isinstance(parent, Arg):
                    
                    function = self.find_parent(parent)
                    if function != None:
                        custom_sample_pos = True

                if not custom_sample_pos:
                    uv_coord = Identifier(node.pos, 'uv')
                else:
                    node: Call = function
                    uv_coord = node.args[1].val          

                uv_rect = f"{property.capitalize()}_UVRect"

                sample_pos_left = BinOp(node.pos, MethodIdentifier(node.pos, Identifier(node.pos, uv_rect), 'zw'), "*", uv_coord)
                sample_pos_right = Call(node.pos, Identifier(0, 'vec2'), (Arg(node.pos, MethodIdentifier(node.pos, Identifier(node.pos, uv_rect), 'x')), Arg(node.pos, BinOp(node.pos, BinOp(node.pos, Float(node.pos, 1.0), '-', MethodIdentifier(node.pos, Identifier(node.pos, uv_rect), 'y')), '-', MethodIdentifier(node.pos, Identifier(node.pos, uv_rect), 'w')))))
                sample_pos = BinOp(node.pos, sample_pos_left, '+', sample_pos_right)
                sample_call = Call(node.pos, Identifier(0, 'texture'), (Arg(node.pos, Identifier(node.pos, f"{property.capitalize()}_Texture")), Arg(node.pos, sample_pos)))

                color = Identifier(node.pos, f"{property.capitalize()}_Color")
                use_tex = Identifier(node.pos, f"{property.capitalize()}_useTexture")
                ternary = TernaryExpression(node.pos, sample_call, color, use_tex)

                self.replace_node(node, ternary)

            



class Material:
    def __init__(self, data: dict, property_definitions: dict[str, PropertyType], injector: Injector = None):
        self.data = data
        self.properties = self.parse_properties(property_definitions)
        self.property_definitions = property_definitions

        shader = data.get('shader', {})
        frag_source = shader.get('frag','engine/shader/default_shader.fbfrag')
        vert_source = shader.get('vert', 'engine/shader/default_shader.fbvert')
        
        if injector == None:
            injector = MaterialInjector(self)
        
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
            if isinstance(val, (Texture, Image)):
                return val

            elif isinstance(val, str):
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
            elif isinstance(val, (Texture, Image)):
                if isinstance(val, Texture):
                    tex = val
                elif isinstance(val, Image):
                    tex = val.texture

                self.shader.set_uniform(f"{material_property.capitalize()}_Texture", tex)
                self.shader.set_uniform(f"{material_property.capitalize()}_useTexture", True)
                self.shader.set_uniform("Albedo_UVRect", tex.uv_rect)
            else:
                self.shader.set_uniform(f"{material_property.capitalize()}_Color", Color('#FF00FFFF'))
                self.shader.set_uniform(f"{material_property.capitalize()}_useTexture", False)

        self.shader.set_uniform('model', transform.model)
        self.shader.set_uniform('view', camera.view_matrix)
        self.shader.set_uniform('proj', camera.proj_matrix)
        
        self.shader.use()
        