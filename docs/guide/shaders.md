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

## Loops and `discard`

`while` and Python's `for ... in range(...)` both work, with `break` and
`continue`:

```fbusl
for i in range(8):            # also range(start, stop), range(start, stop, step)
    if done:
        break
    total += sample_texel(Lut, ivec2(i, 0), 0).x
```

As in Python, `stop` is read once before the first iteration. `step` has to be a
non-zero integer constant, because its sign sets the loop's direction. The loop
variable belongs to the loop, so don't read it afterwards.

`discard` is a statement that only exists in a fragment stage. It writes nothing
for this fragment, depth included, and stops the shader for it. It's what cuts a
leaf out of its card:

```fbusl
if sample(Leaf, uv).w < 0.5:
    discard
```

## Reading textures

| Type | Holds | Read with |
|---|---|---|
| `texture` | one image, maybe part of an atlas | `sample`, `sample_level`, `sample_texel` |
| `textureStack` | layers of same-sized images | the same, with the layer index before the coordinate |
| `textureVolume` | a block of voxels | `sample`, `sample_level`, `sample_texel`, by `vec3` |
| `textureCube` | six faces | `sample`, `sample_level`, by direction |
| `textureShadow` | a depth image, by comparison | `sample_shadow` |

- **`sample(tex, uv)`** is the everyday read. It's filtered, and a fragment stage
  picks the mip level from how fast `uv` moves across the screen. Other stages
  read level 0.
- **`sample_level(tex, uv, level)`** is filtered at a mip level you choose. 0 is
  full size and fractions blend two levels. It does the same thing in every stage.
- **`sample_texel(tex, coord, level)`** reads one exact texel by integer position,
  unfiltered. Coordinates count from the corner `sample()` calls uv `(0, 0)`, and
  within the texture's own rect when it's in an atlas.
- **`sample_shadow(tex, uv, depth)`** returns how lit a point is: `0.0` when `depth`
  is behind what the map holds, `1.0` when it's in front, and in between across
  the four texels around `uv`.

Volume, cube and shadow textures come from the renderer's `texture_manager`:

```python
tm = fb.get_service("renderer").texture_manager
noise = tm.create_texture_volume(voxels)   # uint8: (depth, height, width) or (..., 4)
sky = tm.create_texture_cube(faces)        # (6, size, size, 4), +x -x +y -y +z -z. Float keeps radiance past 1.
shadow = tm.wrap_shadow_texture(framebuffer.get_attachment_texture("depth"))

shader["Noise"] = noise
```

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
