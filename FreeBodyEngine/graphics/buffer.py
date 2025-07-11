from FreeBodyEngine.utils import abstractmethod

class Buffer:
    """Abstracts different buffer object across grahpics APIs, providing the ability to store and use large amount data on the GPU."""
    @abstractmethod
    def bind(self):
        pass

    @abstractmethod
    def unbind(self):
        pass

    