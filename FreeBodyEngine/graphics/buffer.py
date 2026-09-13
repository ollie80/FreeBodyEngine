from FreeBodyEngine.utils import abstractmethod
import numpy as np

class Buffer:
    """Abstracts different buffer object across grahpics APIs, providing the ability to store and use large amount data on the GPU."""
    @abstractmethod
    def set_data(self, data: np.ndarray):
        """Uploads `data` to the buffer, replacing its current contents."""
        pass

    @abstractmethod
    def get_data(self):
        """Returns the data last passed to `set_data()`."""
        pass

    @abstractmethod
    @staticmethod
    def get_max_size() -> int:
        "Returns the max size of the buffer in bytes."
        pass

    @abstractmethod
    def bind(self):
        """Binds the buffer for use."""
        pass

    @abstractmethod
    def unbind(self):
        """Unbinds the buffer."""
        pass

    @abstractmethod
    def destroy(self):
        """Releases the buffer's underlying GPU resources."""
        pass
    