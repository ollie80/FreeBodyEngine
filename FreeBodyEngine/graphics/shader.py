from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.fbusl import compile

class Shader:
    """
    The shader object. Its purpose is to abstract shaders across different Graphics APIs. It does this by setting uniforms
    """
    def __init__(self, vertex_source, fragment_source, generator, injector):
        
        # self.vertex_source = compile(vertex_source, generator, injector, 'vert')
        self.fragment_source = compile(fragment_source, generator, injector, 'frag')
        self.vertex_source = vertex_source
        # self.fragment_source = fragment_source

    @abstractmethod
    def set_uniform(self, name: str, value: any):
        pass

    @abstractmethod
    def get_uniform(self, name: str):
        pass
 
    def __getitem__(self, name):
        return self.get_uniform(name)

    def __setitem__(self, name, value):
        self.set_uniform(name, value)

