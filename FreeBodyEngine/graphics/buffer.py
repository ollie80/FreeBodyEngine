from FreeBodyEngine.utils import abstractmethod
import numpy as np

class Buffer:
    """Abstracts different buffer object across grahpics APIs, providing the ability to store and use large amount data on the GPU."""
    @abstractmethod
    def set_data(self, data: np.ndarray):
        pass

    @abstractmethod
    def get_max_size(self) -> int:
        "Returns the max size of the buffer in bytes."
        pass

    @abstractmethod
    def bind(self):
        pass

    @abstractmethod
    def unbind(self):
        pass

    @abstractmethod
    def destroy(self):
        pass
    