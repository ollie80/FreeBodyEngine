from abc import ABC, abstractmethod

class Shader(ABC):
    """
    The shader object. Its purpose is to abstract shaders across different Graphics APIs. It does this by setting uniforms
    """
    def __init__(self):
        pass

    @abstractmethod
    def _set_uniform(self, name: str, value: any):
        pass

    @abstractmethod
    def _get_uniform(self, name: str):
        pass

    

    def __getitem__(self, name):
        return self._get_uniform(name)

    def __setitem__(self, name, value):
        self._set_uniform(name, value)

