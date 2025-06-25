from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine.graphics.fbusl.injector import Injector
from FreeBodyEngine.graphics.fbusl import throw_error
from FreeBodyEngine.graphics.fbusl.ast_nodes import *
from FreeBodyEngine import get_main

from FreeBodyEngine.math import Transform, Vector3, Vector

from typing import Literal, TYPE_CHECKING
if TYPE_CHECKING:
    from FreeBodyEngine.core.camera import Camera2D

class Material:
    def __init__(self, data: dict):
        self.albedo = Color(data.get('albedo', '#FFFFFFFF'))
        self.normal = Color(data.get('normal', '#8080FFFF'))
        self.emmision = Color(data.get('emmision', '#00000000'))
        self.roughness = data.get('roughness', 1.0)
        self.metallic = data.get('metallic', 0.0)
        self.opactiy = data.get('opacity', 1.0)

        self._render_mode = data.get('render_mode', 'lit') # cannot be change
        shader = data.get('shader', {})
        frag_source = shader.get('frag','engine/shader/default_shader.fbfrag')
        vert_source = shader.get('vert', 'engine/shader/default_shader.fbvert')
        self.shader: Shader = get_main().renderer.load_shader(get_main().files.load_data(vert_source), get_main().files.load_data(frag_source), MaterialInjector)

    @property
    def render_mode(self) -> Literal["lit", "unlit", "wireframe"]: 
        return self._render_mode

    def set_uniform(self, name: str, val: any):
        self.shader[name] = val
    
    def get_uniform(self, name: str):
        return self.shader[name]
    
    def _set_default_uniforms(self, transform: Transform, camera: 'Camera2D'):
        #frag
        self.set_uniform('u_Albedo', self.albedo.float_normalized_a)
        self.set_uniform('u_Normal', self.normal.float_normalized_a)
        self.set_uniform('u_Emmision', self.emmision.float_normalized_a)
        self.set_uniform('u_Roughness', self.roughness)
        self.set_uniform('u_Metallic', self.metallic)
        
        #vert
        self.set_uniform('u_Position', transform.model())
        self.set_uniform('u_View', camera.view_matrix)
        self.set_uniform('u_Projection', camera.proj_matrix)

    def use(self, transform: Transform, camera: 'Camera2D'):
        """Must be called before drawing."""
        self._set_default_uniforms(transform, camera)
        

class MaterialInjector(Injector):
    def __init__(self, tree: Tree, shader_type, file_path):
        super().__init__(tree, shader_type, file_path)

    @classmethod
    def get_builtins():
        return {"vars": [{'ALBEDO': {"type": "sampler2D"}}, {'NORMAL': {"type": "sampler2D"}}, {'EMMISION': {"type": "sampler2D"}}, {'ROUGHNESS': {"type": "sampler2D"}}, {'METALLIC': {"type": "sampler2D"}}]}

    def inject(self):
        self.inject_main()
        return self.tree
        
    def inject_main(self):
        main = None
        for node in self.tree.children:
            if isinstance(node, FuncDecl):
                if node.name == 'main':
                    main = node

        if main == None:
            throw_error("No main function defined", 0, self.file_path)

        if self.shader_type == "frag":
            self.inject_main_frag(main)
        else:
            self.inject_main_vert(main)

    def inject_main_frag(self, main: FuncDecl):
        defaults = {"albedo": 'vec4', "normal": 'vec4', 'emmision': 'vec4', 'roughness': 'float', 'metallic': 'float'}
        
        for name, type in reversed(defaults.items()):
            self.tree.children.insert(1, UniformDecl(0, f'u_{name.capitalize()}', f'{type}', None))

        remaining_defaults = set(defaults.keys())

        for node in main.body:
            if isinstance(node, Set):
                if isinstance(node, Set) and node.ident.name in remaining_defaults:
                    remaining_defaults.remove(node.ident.name)
                    node.value = BinOp(node.pos, Identifier(node.pos, f'u_{node.ident.name.capitalize()}'), '*', node.value)

        for name in remaining_defaults:
            self.tree.children.insert(1, OutputDecl(0, f'{name}', f'{defaults[name]}', None))
            main.body.append(Set(main.pos, Identifier(main.pos, name), Identifier(main.pos, f"u_{name.capitalize()}")))
        

    def inject_main_vert(self, main: FuncDecl):
        
        main.body.append(Set())