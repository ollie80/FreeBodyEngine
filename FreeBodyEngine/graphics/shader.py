from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.fbusl import compile
from FreeBodyEngine.graphics.fbusl.injector import Injector

class Shader:
    """
    The shader object. Its purpose is to abstract shaders across different Graphics APIs. It does this by setting uniforms
    """
    def __init__(self, vertex_source, fragment_source, generator, injector: type[Injector] = Injector()):        
        self.vertex_source = compile(vertex_source, generator, injector, 'vert')
        self.fragment_source = compile(fragment_source, generator, injector, 'frag')

    @abstractmethod
    def set_uniform(self, name: str, value: any):
        pass

    @abstractmethod
    def get_uniform(self, name: str):
        pass
 
    @abstractmethod
    def use(self):
        pass

    def __getitem__(self, name):
        return self.get_uniform(name)

    def __setitem__(self, name, value):
        self.set_uniform(name, value)

