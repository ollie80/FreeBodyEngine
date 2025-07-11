from OpenGL.GL import *
from FreeBodyEngine.graphics.buffer import Buffer
import numpy as np

class UBOBuffer(Buffer):
    """The OpenGL 3.3 implementation of the buffer class."""
    def __init__(self, data: np.ndarray):
        self.buffer_size = data.nbytes
        self.data = data

        self.ubo = glGenBuffers(1)        
        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)
        glBufferData(GL_UNIFORM_BUFFER, self.buffer_size, None, GL_DYNAMIC_DRAW) 
    
        glBufferSubData(GL_UNIFORM_BUFFER, 0, self.buffer_size, self.data)

        self.binding_point



        glBindBuffer(GL_UNIFORM_BUFFER, self.ubo)