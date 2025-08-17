from FreeBodyEngine.utils import abstractmethod
from FreeBodyEngine.graphics.fbusl import compile
from FreeBodyEngine.graphics.fbusl.injector import Injector

import numpy as np

def merge_dicts(d1, d2):
    result = d1.copy()
    for key, val in d2.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = merge_dicts(result[key], val)
        else:
            result[key] = val
    return result


class Shader:
    """
    The shader object. Its purpose is to abstract shaders across different Graphics APIs. It does this by setting uniforms
    """
    def __init__(self, vertex_source, fragment_source, generator, injector: type[Injector] = Injector()):        
        self.data = {}
        self.vertex_source, vert_data = compile(vertex_source, generator, injector,  'vert', 0)
        
        buffer_index = len(vert_data['buffers'])

        self.fragment_source, frag_data = compile(fragment_source, generator, injector, 'frag', buffer_index)
        
        self.data = merge_dicts(vert_data, frag_data)

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

