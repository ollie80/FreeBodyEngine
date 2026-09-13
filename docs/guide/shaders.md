# Shaders (FBUSL)

FreeBodyEngine shaders are written in **FBUSL** (FreeBody Unified Shader
Language, a separate package) rather than raw GLSL - one shader source
compiles to whichever backend is actually active (`GL33Generator`,
`GL44Generator`, ...) via `fbusl.compile(source, shader_type, generator,
injector)`, so a shader isn't tied to one GL version.

## Anatomy of a shader

```fbusl title="default_shader.fbfrag"
@output
albedo: vec4

@uniform
Albedo_Texture: texture
Albedo_Color: vec4
Albedo_useTexture: bool

@input
uv: vec2

def main() -> void:
    albedo = sample(Albedo_Texture, uv) if Albedo_useTexture else Albedo_Color
```

- **`@output`** fields become that stage's outputs - for a fragment shader,
  each one maps (in declaration order) to a color attachment on whatever
  framebuffer is bound when it runs.
- **`@uniform`** fields are set from Python via `shader[name] = value` (or a
  [`Material`][FreeBodyEngine.graphics.material.Material]'s own property
  system - see below).
- **`@input`** fields must match the previous stage's `@output` fields, in
  the same order - a vertex shader's outputs feed a fragment shader's
  inputs positionally, not by name.

## Materials

A [`Material`][FreeBodyEngine.graphics.material.Material] pairs a compiled
shader with a set of named properties (`albedo`, `normal`, `roughness`,
...), each either a plain color or a [`Texture`][FreeBodyEngine.graphics.texture.Texture] -
`Material.use()` picks the right uniforms (`{Prop}_Color`/`{Prop}_Texture`/
`{Prop}_useTexture`) for whichever one it was given, which is what the
`Albedo_useTexture` ternary above is doing. A `.fbmat` file is just the TOML
form of that same property dict; see
[`load_material`][FreeBodyEngine.core.files.loaders.material.load_material].

## Compute and raytrace kernels

Beyond ordinary vertex/fragment stages, FBUSL also has `@compute` and
`@raytrace` kernels - a single dispatch mechanism ([`ComputeShader`][FreeBodyEngine.graphics.compute.ComputeShader])
that a capability-limited backend (GL33, with no real
`glDispatchCompute`/SSBOs) emulates as one fullscreen draw, one output pixel
per invocation. A `@raytrace` kernel additionally gets `make_ray`/`trace_ray`
builtins backed by a CPU-built BVH (see
[`build_bvh`][FreeBodyEngine.graphics.raytrace.bvh.build_bvh]) uploaded as
buffer textures - real inline ray queries (`RayHit trace_ray(Ray)`), not a
raygen/closest-hit/miss shader binding table, since inline ray query is the
one model a compute-emulated backend can actually implement.

A raytrace kernel is a normal tool for **lighting**, not necessarily for
primary visibility - rasterizing a scene normally and then reading its
G-buffer back into a `@raytrace` pass (for shadows, reflections, or other
effects a rasterizer alone can't do well) is the same rasterize-then-
raytrace split real-time engines use, and is exactly what
[`GLRaytraceShader`][FreeBodyEngine.graphics.gl33.compute.GLRaytraceShader]
is built to support - see its docstring and `upload_scene()` for the actual
buffer layout.
