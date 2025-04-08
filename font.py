import glfw
from OpenGL.GL import *
import freetype
import numpy as np
import glm

SCR_WIDTH = 800
SCR_HEIGHT = 600

VAO = None
VBO = None
Characters = {}

FRAG = """
#version 330 core
in vec2 TexCoords;
out vec4 color;

uniform sampler2D text;
uniform vec3 textColor;

void main()
{    
    vec4 sampled = vec4(1.0, 1.0, 1.0, texture(text, TexCoords).r);
    color = vec4(textColor, 1.0) * sampled;
}  
"""

VERT = """
#version 330 core
layout (location = 0) in vec4 vertex; // <vec2 pos, vec2 tex>
out vec2 TexCoords;

uniform mat4 projection;

void main()
{
    gl_Position = projection * vec4(vertex.xy, 0.0, 1.0);
    TexCoords = vertex.zw;
}  
"""

# ---------- Shader Loader ----------
class Shader:
    def __init__(self, vert, frag):

        self.ID = glCreateProgram()
        vertex = self._compile_shader(vert, GL_VERTEX_SHADER)
        fragment = self._compile_shader(frag, GL_FRAGMENT_SHADER)
        glAttachShader(self.ID, vertex)
        glAttachShader(self.ID, fragment)
        glLinkProgram(self.ID)

        # Check for linking errors
        if glGetProgramiv(self.ID, GL_LINK_STATUS) != GL_TRUE:
            print(glGetProgramInfoLog(self.ID))
        glDeleteShader(vertex)
        glDeleteShader(fragment)

    def use(self):
        glUseProgram(self.ID)

    def _compile_shader(self, source, shader_type):
        shader = glCreateShader(shader_type)
        glShaderSource(shader, source)
        glCompileShader(shader)

        # Check for compilation errors
        if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
            print(glGetShaderInfoLog(shader))
        return shader

# ---------- FreeType Text Rendering ----------
class Character:
    def __init__(self, texture_id, size, bearing, advance):
        self.TextureID = texture_id
        self.Size = size
        self.Bearing = bearing
        self.Advance = advance

def load_font(path):
    face = freetype.Face(path)
    face.set_pixel_sizes(0, 48)

    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

    for c in range(128):
        face.load_char(chr(c))
        bitmap = face.glyph.bitmap
        width, height = bitmap.width, bitmap.rows

        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, width, height, 0, GL_RED, GL_UNSIGNED_BYTE, bitmap.buffer)

        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        ch = Character(
            texture,
            glm.ivec2(width, height),
            glm.ivec2(face.glyph.bitmap_left, face.glyph.bitmap_top),
            face.glyph.advance.x
        )
        Characters[chr(c)] = ch

def render_text(shader, text, x, y, scale, color):
    shader.use()
    glUniform3f(glGetUniformLocation(shader.ID, "textColor"), *color)
    glActiveTexture(GL_TEXTURE0)
    glBindVertexArray(VAO)

    for c in text:
        ch = Characters.get(c)
        if not ch:
            continue

        xpos = x + ch.Bearing.x * scale
        ypos = y - (ch.Size.y - ch.Bearing.y) * scale
        w = ch.Size.x * scale
        h = ch.Size.y * scale

        vertices = np.array([
            xpos,     ypos + h,   0.0, 0.0,
            xpos,     ypos,       0.0, 1.0,
            xpos + w, ypos,       1.0, 1.0,

            xpos,     ypos + h,   0.0, 0.0,
            xpos + w, ypos,       1.0, 1.0,
            xpos + w, ypos + h,   1.0, 0.0
        ], dtype=np.float32)

        glBindTexture(GL_TEXTURE_2D, ch.TextureID)
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferSubData(GL_ARRAY_BUFFER, 0, vertices.nbytes, vertices)

        glDrawArrays(GL_TRIANGLES, 0, 6)

        x += (ch.Advance >> 6) * scale  # Bitshift by 6 to convert from 1/64 pixels to pixels

    glBindVertexArray(0)
    glBindTexture(GL_TEXTURE_2D, 0)

def framebuffer_size_callback(window, width, height):
    glViewport(0, 0, width, height)

def process_input(window):
    if glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
        glfw.set_window_should_close(window, True)

def main():
    global VAO, VBO

    if not glfw.init():
        return

    window = glfw.create_window(SCR_WIDTH, SCR_HEIGHT, "Text Rendering", None, None)
    if not window:
        glfw.terminate()
        return

    glfw.make_context_current(window)
    glfw.set_framebuffer_size_callback(window, framebuffer_size_callback)

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    shader = Shader(VERT, FRAG)
    projection = glm.ortho(0.0, SCR_WIDTH, 0.0, SCR_HEIGHT)
    shader.use()
    glUniformMatrix4fv(glGetUniformLocation(shader.ID, "projection"), 1, GL_FALSE, glm.value_ptr(projection))

    load_font("game/assets/graphics/fonts/rubik.ttf")

    VAO = glGenVertexArrays(1)
    VBO = glGenBuffers(1)

    glBindVertexArray(VAO)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, 6 * 4 * 4, None, GL_DYNAMIC_DRAW)

    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(0))
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindVertexArray(0)

    while not glfw.window_should_close(window):
        process_input(window)

        glClearColor(0.1, 0.1, 0.1, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        render_text(shader, "The quick brown fox jumps over the lazy dog", 25.0, 25.0, 0.7, glm.vec3(0.5, 0.8, 0.2))

        glfw.swap_buffers(window)
        glfw.poll_events()

    glfw.terminate()

if __name__ == "__main__":
    main()
