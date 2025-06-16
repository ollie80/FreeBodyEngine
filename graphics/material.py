from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.graphics.shader import Shader
from FreeBodyEngine import get_main

class Material:
    def __init__(self, data: dict):
        self.albedo = Color(data.get('albedo', '#FFFFFF'))
        self.normal = Color(data.get('normal', '#8080FF'))
        self.emmision = Color(data.get('emmision', '#000000'))
        self.roughness = data.get('roughness', 1)
        self.metallic = data.get('metallic', 0)
        self.opactiy = data.get('opacity', 1)

        self.render_mode = data.get('render_mode', 'lit') # lit | unlit | wireframe
        shader = data.get('shader', {})
        frag_source = shader.get('frag','engine/shader/default_shader.fbfrag')
        vert_source = shader.get('vert', 'engine/shader/default_shader.fbvert')
        
        self.shader: Shader = get_main().renderer.load_shader(get_main().files.load_data(frag_source), get_main().files.load_data(vert_source))
    
    def set_uniform(self, name: str, val: any):
        self.shader[name] = val
    
    def get_uniform(self, name: str):
        return self.shader[name]