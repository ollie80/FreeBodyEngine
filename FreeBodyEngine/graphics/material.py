from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.shader import Shader
from fbusl.injector import Injector
from fbusl import fbusl_error, ShaderType
from fbusl.node import *
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
    """The kinds of value a Material property can hold - a plain scalar/
    color, or a texture. Drives both how `Material.parse_property_val`
    interprets a `.fbmat`'s raw data for a property and what GLSL type
    `MaterialInjector.parse_property` resolves a color property to for a
    shader referencing it as a bare identifier."""

    FLOAT = auto()
    INT = auto()

    COLOR_R = auto()
    COLOR_RG = auto()
    COLOR_RGB = auto()
    COLOR_RGBA = auto()

    TEXTURE = auto()

class MaterialInjector(Injector):
    """Lets a shader reference a material property (e.g. `ALBEDO`) as a bare
    identifier and have it transparently resolve to `sample(prop_Texture, uv)`
    or `prop_Color` depending on whether the material was given a texture or a
    plain color, without the shader author writing that branch by hand.
    """
    def __init__(self, material: 'Material'):
        """Stores the Material this injector rewrites shader references for.
        `mat_properties` is left empty here and filled lazily by
        `_property_types()`."""
        super().__init__()
        self.material = material
        self.mat_properties: dict[str, str] = {}

    def parse_property(self, property: PropertyType) -> str:
        """Maps a COLOR_* PropertyType to the GLSL type its backing uniform
        is declared as (e.g. `COLOR_RGB` -> `'vec3'`)."""
        return {
            PropertyType.COLOR_R: 'float',
            PropertyType.COLOR_RG: 'vec2',
            PropertyType.COLOR_RGB: 'vec3',
            PropertyType.COLOR_RGBA: 'vec4',
        }[property]

    def _property_types(self) -> dict[str, str]:
        # `compile()` calls ast_inject() *before* get_builtins() (the tree is
        # rewritten, then handed to the semantic analyser along with the
        # builtins dict) - so this can't be computed once in get_builtins()
        # and read back later in ast_inject(); both call this independently.
        if not self.mat_properties:
            self.mat_properties = {
                name: self.parse_property(ptype)
                for name, ptype in self.material.property_definitions.items()
            }
        return self.mat_properties

    def get_builtins(self):
        """Fragment-shader-only: declares each material property's
        capitalized name (e.g. `ALBEDO`) as a `uniform`-kind builtin so it
        type-checks during semantic analysis even if `ast_inject()` below
        somehow doesn't get to rewrite it first - belt-and-braces, since
        `ast_inject()` is what actually performs the real rewrite."""
        if self.shader_type != ShaderType.FRAGMENT:
            return {}

        # Declared as "uniform" builtins so a bare `ALBEDO` identifier would
        # type-check during semantic analysis even if ast_inject() somehow
        # left one behind - belt-and-braces, since ast_inject() below is what
        # actually rewrites every such identifier into the real ternary
        # expression and injects the real backing uniforms it references.
        return {
            name.upper(): {"kind": "uniform", "type": glsl_type}
            for name, glsl_type in self._property_types().items()
        }

    def ast_inject(self, tree: list[ASTNode]):
        """Fragment-shader-only: rewrites every bare `PROPERTY` identifier
        (e.g. `ALBEDO`) into `useTexture ? sample(Texture, uv) : Color`, and
        injects the `{Prop}_Texture`/`{Prop}_Color`/`{Prop}_useTexture`
        uniforms that ternary references - letting a shader author write
        `ALBEDO` directly instead of hand-writing the texture-vs-color
        branch themselves."""
        if self.shader_type != ShaderType.FRAGMENT:
            return tree

        injected_uniforms = []
        for prop, glsl_type in self._property_types().items():
            cap = prop.capitalize()
            injected_uniforms += [
                Uniform(f"{cap}_Texture", {"name": "texture"}, None),
                Uniform(f"{cap}_Color", {"name": glsl_type}, None),
                Uniform(f"{cap}_useTexture", {"name": "bool"}, None),
            ]

            def matcher(node, prop=prop):
                """Matches a bare `Identifier` referencing this property's
                uppercase name (e.g. `ALBEDO`) - `prop` is captured as a
                default arg to bind the loop variable's current value
                rather than whatever `prop` is by the time `replace_expr`
                calls this."""
                return isinstance(node, Identifier) and node.value == prop.upper()

            def replacer(node, cap=cap):
                """Builds the `useTexture ? sample(Texture, uv) : Color`
                ternary that replaces a matched `PROPERTY` identifier;
                `cap` is captured as a default arg for the same
                late-binding reason as `matcher`'s `prop`."""
                return InlineIf(
                    then_expr=FuncCall("sample", [Identifier(f"{cap}_Texture"), Identifier("uv")]),
                    condition=Identifier(f"{cap}_useTexture"),
                    else_expr=Identifier(f"{cap}_Color"),
                )

            for node in tree:
                if isinstance(node, FunctionDef):
                    for stmt in self.walk_body(node.body):
                        self.replace_expr(stmt, matcher, replacer)

        return injected_uniforms + tree

class Material:
    """A shader plus a set of named properties (colors or textures) that
    drive its uniforms - built from parsed `.fbmat` TOML `data` against a
    `property_definitions` schema (see e.g. PBRMaterial's albedo/normal/
    roughness/... set). Property values are readable/writable both as plain
    attributes (`material.albedo`) and as dict items (`material['albedo']`),
    transparently redirected to `self.properties` via `__getattribute__`/
    `__setattr__`/`__getitem__`/`__setitem__` below."""
    def __init__(self, data: dict, property_definitions: dict[str, PropertyType], injector: Injector = Injector()):
        """Parses `data` against `property_definitions` into
        `self.properties`, and compiles this material's shader (from
        `data['shader']`, defaulting to the engine's default_shader) via the
        renderer."""
        self.data = data
        self.properties = self.parse_properties(property_definitions)
        self.property_definitions = property_definitions
        # Pixel art needs nearest-neighbor sampling - the default linear
        # filtering (see GLTextureManager._create_standalone_texture) blurs
        # every texel edge together, which reads as "blurry" on a sprite
        # sheet whose whole look depends on crisp pixel boundaries.
        self.pixel_filter = str(data.get('filter', 'linear')).lower() == 'nearest'

        shader = data.get('shader', {})
        frag_source = shader.get('frag','engine://shader/default_shader.fbfrag')
        vert_source = shader.get('vert', 'engine://shader/default_shader.fbvert')
        geom_source = shader.get('geom', None)

        # Remembered (as plain path strings, not the FileResource itself) so
        # dev-mode hot reload can re-fetch and recompile against whatever's
        # on disk *right now* - see reload_shader() below. Re-fetching
        # through get_file() rather than re-reading the FileResource this
        # constructor already made matters for editors that save via
        # write-to-temp-then-rename: that leaves any already-open file
        # handle pointing at the old (now-unlinked) inode, silently never
        # seeing the new content.
        self._vert_source_path = vert_source
        self._frag_source_path = frag_source
        self._geom_source_path = geom_source
        self._shader_injector = injector

        files = get_service('files')
        geom_file = files.get_file(geom_source) if geom_source is not None else None

        self.shader: Shader = get_service('renderer').load_shader(files.get_file(vert_source), files.get_file(frag_source), injector, geom_file)

    def reload(self, data: dict):
        """Re-applies freshly loaded `.fbmat` TOML data to this SAME
        Material object in place - every Sprite/Model/etc. already holding
        a reference keeps working, no re-wiring needed. Used by dev-mode
        hot reload (see core/files/hot_reload.py). Only property data
        (colors/texture paths) is re-applied here; call reload_shader()
        separately if the shader *source* files changed instead."""
        self.data = data
        self.pixel_filter = str(data.get('filter', 'linear')).lower() == 'nearest'
        self.properties = self.parse_properties(self.property_definitions)

    def reload_shader(self):
        """Recompiles this material's shader in place (same Shader object,
        same GL program id) from whatever its vert/frag/geom source files
        currently contain - for when one of *those* files changed, not the
        `.fbmat` itself."""
        files = get_service('files')
        vert_file = files.get_file(self._vert_source_path)
        frag_file = files.get_file(self._frag_source_path)
        geom_file = files.get_file(self._geom_source_path) if self._geom_source_path is not None else None
        self.shader.rebuild(self._shader_injector, vert_file, frag_file, geom_file)

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

    def __getitem__(self, name):
        return object.__getattribute__(self, name)

    def __setitem__(self, name, value):
        object.__setattr__(self, name, value) 

    def parse_properties(self, property_definitions):
        """Builds `{property_name: parsed_value}` from `self.data`, keeping
        only the properties declared in `property_definitions` and ignoring
        anything else the `.fbmat` TOML might contain (e.g. `shader`/
        `filter`, which are handled separately)."""
        properties = {}
        for data in self.data:
            if data in property_definitions:
                val = self.data[data]

                properties[data] = self.parse_property_val(val, data, property_definitions)
        
        return properties

    def parse_property_val(self, val: any, property, property_definitions):
        """Interprets one property's raw TOML value against its declared
        PropertyType - currently only implemented for COLOR_RGB/COLOR_RGBA:
        a Texture/Image is passed through as-is, a `#`-prefixed string is
        parsed as a hex Color, and a 2-4 length sequence of numbers is
        parsed as a Color too. Warns and returns None (silently, since no
        `return` follows the warning) for anything that doesn't match, or
        for any other PropertyType."""
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
                        if not isinstance(v, (int, float)):
                            correct_type = False
                            break
                    if correct_type:
                        return Color(val)
                    else:
                        warning(f"Couldn't parse material color value, '{property}' did not contain numbers.")
                else:
                    warning(f"Couldn't parse material color value, '{property}' only contained {len(val)} values, minimum of 3 is required.")

    
    def use(self):
        """Uploads every property's current value to the shader as uniforms
        - a Color property sets `{Prop}_Color` and `{Prop}_useTexture =
        False`; a Texture/Image property applies this material's
        `pixel_filter` to it and sets `{Prop}_Texture` and
        `{Prop}_useTexture = True` - then activates the shader for
        drawing."""
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

                tex.manager.set_texture_filter(tex.id, self.pixel_filter)
                self.shader.set_uniform(f"{material_property.capitalize()}_Texture", tex)
                self.shader.set_uniform(f"{material_property.capitalize()}_useTexture", True)
            else:
                self.shader.set_uniform(f"{material_property.capitalize()}_Color", Color('#FF00FFFF'))

        self.shader.use()
