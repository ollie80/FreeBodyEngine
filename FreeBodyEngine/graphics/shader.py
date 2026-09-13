import sys
from FreeBodyEngine.utils import abstractmethod
from fbusl import compile, ShaderType
from fbusl.injector import Injector

import numpy as np

class Shader:
    """Backend-agnostic compiled shader: compiles FBUSL vertex/fragment(/geometry)
    source through `generator` into backend GLSL. Building a runnable GPU
    program from that GLSL, and binding uniforms/buffers to it, is left to a
    concrete subclass (e.g. GLShader)."""
    def __init__(self, vertex_source, fragment_source, generator, injector: type[Injector] = Injector(), geometry_source=None):
        """Compiles `vertex_source`/`fragment_source` (and `geometry_source`,
        if given) through `generator` via FBUSL. The original sources are
        kept alongside the compiled output so `rebuild()` and dev-mode hot
        reload (see Material.reload_shader()) can recompile from the same
        inputs, or from freshly re-fetched ones, without needing them passed
        in again."""
        self.data = {}
        if injector == None:
            injector = Injector()

        self.fbusl_vertex_source = compile(vertex_source, ShaderType.VERTEX, generator, injector)
        self.fbusl_fragment_source = compile(fragment_source, ShaderType.FRAGMENT, generator, injector)

        self.fbusl_geometry_source = None
        if geometry_source is not None:
            self.fbusl_geometry_source = compile(geometry_source, ShaderType.GEOMETRY, generator, injector)

        self.fragment_source = fragment_source
        self.vertex_source = vertex_source
        self.geometry_source = geometry_source

        self.generator = generator


    @abstractmethod
    def rebuild(self, injector: type[Injector] = Injector(), vertex_source=None, fragment_source=None, geometry_source=...):
        """Recompiles this shader in place. `vertex_source`/`fragment_source`
        default to this shader's existing ones; `geometry_source` defaults
        to the existing one unchanged (via the `...` sentinel, since `None`
        is itself a valid "no geometry shader" value)."""
        pass

    @abstractmethod
    def set_uniform(self, name: str, value: any):
        """Sets uniform `name` to `value`."""
        pass

    @abstractmethod
    def get_uniform(self, name: str):
        """Returns this shader's internal record for uniform `name` - its
        shape is backend-specific (e.g. GLShader returns location/type
        metadata, not the uniform's current value)."""
        pass

    @abstractmethod
    def set_buffer(self, name: str, data: np.array):
        """Binds `data` to the buffer block declared as `name` in this
        shader's source."""
        pass

    @abstractmethod
    def use(self):
        """Activates this shader as the current GPU program for subsequent
        draw calls."""
        pass

    def __getitem__(self, name):
        return self.get_uniform(name)

    def __setitem__(self, name, value):
        self.set_uniform(name, value)