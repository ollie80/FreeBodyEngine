import sys
from FreeBodyEngine.utils import abstractmethod
from fbusl import compile, ShaderType
from fbusl.injector import Injector

import numpy as np

class Shader:
    def __init__(self, vertex_source, fragment_source, generator, injector: type[Injector] = Injector()):        
        self.data = {}
        if injector == None:
            injector = Injector()
        
        self.fbusl_vertex_source = compile(vertex_source, ShaderType.VERTEX, generator, injector)
        self.fbusl_fragment_source = compile(fragment_source, ShaderType.FRAGMENT, generator, injector)
        
        self.fragment_source = fragment_source
        self.vertex_source = vertex_source
        
        self.generator = generator


    @abstractmethod
    def rebuild(self, injector: type[Injector] = Injector()):
        pass

    @abstractmethod
    def set_uniform(self, name: str, value: any):
        pass

    @abstractmethod
    def get_uniform(self, name: str):
        pass

    @abstractmethod
    def set_buffer(self, name: str, data: np.array):
        pass

    @abstractmethod
    def use(self):
        pass

    def __getitem__(self, name):
        return self.get_uniform(name)

    def __setitem__(self, name, value):
        self.set_uniform(name, value)

