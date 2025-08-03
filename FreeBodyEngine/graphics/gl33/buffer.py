from OpenGL.GL import *
from FreeBodyEngine.graphics.buffer import Buffer
import numpy as np

class UBOBuffer(Buffer):
    """The OpenGL 3.3 implementation of the buffer class."""
    def __init__(self, data: np.ndarray):
        self.buffer_size = data.nbytes
        self.data = data
        self._current_slot = 0

        self.ubo = glGenBuffers(1)        
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        glBufferData(GL_UNIFORM_BUFFER, self.buffer_size, None, GL_DYNAMIC_DRAW) 
    
        glBufferSubData(GL_UNIFORM_BUFFER, 0, self.buffer_size, self.data)

        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def bind(self, point: int):

        glBindBufferBase(GL_UNIFORM_BUFFER, point, self.ubo)
        self._current_slot = point

    def unbind(self):
        glBindBufferBase(GL_UNIFORM_BUFFER, self._current_slot, 0)

    def set_data(self, new_data: np.ndarray):
        self.data = new_data
        new_size = new_data.nbytes

        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)

        if new_size != self.buffer_size:
            glBufferData(GL_UNIFORM_BUFFER, new_size, None, GL_DYNAMIC_DRAW)
            self.buffer_size = new_size

        glBufferSubData(GL_UNIFORM_BUFFER, 0, new_size, new_data)
        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def get_data(self):
        return self.data

    def get_max_size(self) -> int:
        return glGetIntegerv(GL_MAX_UNIFORM_BLOCK_SIZE)


    def update(self, data: np.ndarray, offset: int = 0):
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        glBufferSubData(GL_UNIFORM_BUFFER, offset, data.nbytes, data)
        glBindBuffer(GL_UNIFORM_BUFFER, 0)

    def destroy(self):
        glDeleteBuffers(1, [self.ubo])