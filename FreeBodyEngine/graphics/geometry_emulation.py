"""Geometry shaders on backends without a geometry stage - WebGL2 and
GLES 3.0 (the GLSL ES generator has no "geometry.native" capability).

Shader.__init__ compiles a vertex + geometry pair into one vertex shader
with fbusl.geometry's "pull" emulation (see fbusl/geometry.py for how it
works): no vertex buffers, `primitives * slots` vertices drawn, and the
mesh read back from data textures instead. "compute" isn't an option
here: these backends' compute is itself emulated in fragment shaders,
with no atomics to append primitives with, so it would only add a pass.

The backend's part (GLShader/WebGL2Shader.draw_emulated) is uploading
the arrays from mesh_arrays() as one-channel float data textures named by
sampler_name(), setting `_gs_prim_count`/`_gs_index_mode`, and drawing.
Everything goes up as float: the GLSL ES generator reads every buffer
field from a float texture (ints through int()), exact up to 2^24.

The Vulkan backend has its own path (graphics/vulkan/shader.py): native
when the GPU has geometry shaders, otherwise either emulation, on real
storage buffers.
"""
import numpy as np

from fbusl import ShaderType, geometry as fbusl_geometry
from fbusl.parser import Lexer, Parser
from fbusl.semantic import SemanticAnalyser
from fbusl.optimizer import Optimizer

from FreeBodyEngine import warning

GL_PRIMITIVES = ("triangles", "lines", "points")


def needs_emulation(generator) -> bool:
    from FreeBodyEngine import get_flag, FORCE_GEOMETRY_MODE
    native = "geometry.native" in getattr(generator, "CAPABILITIES", ())
    return not native or get_flag(FORCE_GEOMETRY_MODE, None) == "pull"


def _parse(source, stage, injector):
    if not isinstance(source, str):
        path, text = source.data.path, source.read()
    else:
        path, text = None, source
    injector.initialize(stage)
    tree = injector.ast_inject(Parser(Lexer(injector.source_inject(text), path).tokenize()).parse())
    return tree, dict(injector.get_builtins() or {})


def compile_pulled_vertex(vertex_source, geometry_source, generator, injector):
    """(vertex shader code, fbusl.geometry.Emulation) for a vertex +
    geometry pair, as one vertex shader for `generator`."""
    vertex_tree, vertex_builtins = _parse(vertex_source, ShaderType.VERTEX, injector)
    geometry_tree, geometry_builtins = _parse(geometry_source, ShaderType.GEOMETRY, injector)
    em = fbusl_geometry.emulate(vertex_tree, geometry_tree, "pull")
    program = em.program
    injector.initialize(ShaderType.VERTEX)
    SemanticAnalyser(program, ShaderType.VERTEX, {**vertex_builtins, **geometry_builtins}).analyse()
    program = Optimizer(program).optimize()
    return generator(program, ShaderType.VERTEX).generate(), em


def sampler_name(block: str) -> str:
    """The uniform a backend's generator declares for `block`'s data."""
    return f"_ENGINE_{block}_data"


def mesh_arrays(mesh, em):
    """(input primitives, index mode, {block: float32 array}) for drawing
    `mesh` through emulation `em` - or (0, 0, None) if it can't be."""
    attributes = list(mesh.attributes.values())
    if len(attributes) < len(em.attributes):
        warning(f"The geometry shader's vertex stage reads {len(em.attributes)} attributes, the mesh has "
                f"{len(attributes)} - draw skipped.")
        return 0, 0, None
    if mesh.indices is not None:
        index = np.asarray(mesh.indices, dtype=np.float32).reshape(-1)
        count, mode = len(index), 2
    else:
        # The GL meshes' own convention for an unindexed draw: the first
        # attribute is a 3-component position.
        count, mode = len(np.asarray(attributes[0][1]).reshape(-1)) // 3, 0
        index = np.zeros(1, dtype=np.float32)
    arrays = {"gs_index": index}
    for (name, *_), (_, data) in zip(em.attributes, attributes):
        arrays[f"gs_attr_{name}"] = np.asarray(data, dtype=np.float32).reshape(-1)
    return count // em.input_vertices, mode, arrays


def data_texture_shape(length: int, max_width: int) -> tuple[int, int]:
    """(width, height) of the 2D data texture holding `length` values, as
    the GLSL ES generator's _ENGINE_buf_idx() addresses it."""
    width = max(1, min(length, max_width))
    return width, max(1, -(-length // width))


def mesh_version(mesh):
    """Changes whenever the mesh's data does - what cached data textures
    are keyed by. set_data() bumps `_version`; TextRenderer-style index
    swaps change the indices object."""
    indices = mesh.indices
    return (getattr(mesh, "_version", 0), id(indices), None if indices is None else len(indices))
