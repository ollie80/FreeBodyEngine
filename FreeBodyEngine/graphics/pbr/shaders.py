"""FBUSL source for PBRPipeline's internal shaders - the lighting composite
pass (deferred, reads the G-buffer back) and the light-list/PBR math it
shares with default_forward.fbfrag (forward-shaded transparent objects -
see graphics/material.py's BlendMode and PBRMaterial's shader defaults).

MAX_LIGHTS is a hard cap: every slot is a flat set of named uniforms
(`LightN_...`) rather than a true GLSL uniform array, unrolled `MAX_LIGHTS`
times in source. This is a deliberate, lower-risk choice over FBUSL's
`@buffer` blocks - see graphics/pbr/pipeline.py's module docstring for why.
Raising this constant costs one recompile of both shaders (see
graphics/pbr/pipeline.py, which reads it from here) and linearly more
uniform-set calls per frame; it is not a per-object cost.

Shadows: only slot 0 is ever sampled against a shadow map (see
PBRPipeline._collect_lights - the shadow-casting DirectionalLight3D, if any,
is always placed there). Every other slot is unshadowed. See
graphics/pbr/lighting.py's module docstring for why 2D lights and non-slot-0
3D lights don't cast shadows yet.
"""

MAX_LIGHTS = 8

_LIGHT_UNIFORMS = "\n".join(
    f"""Light{i}_Active: bool
Light{i}_Type: int
Light{i}_Position: vec3
Light{i}_Direction: vec3
Light{i}_Color: vec3
Light{i}_Intensity: float
Light{i}_Range: float
Light{i}_SpotCos: float"""
    for i in range(MAX_LIGHTS)
)

# Both LIGHTING_COMPOSITE_FRAG and default_forward.fbfrag draw with only
# 'lit' active as a draw buffer (see PBRPipeline._draw_composite()/draw()),
# which on WebGL2 specifically must be a full-width drawBuffers array
# ([NONE, NONE, ..., COLOR_ATTACHMENT7]) rather than the 1-element
# [COLOR_ATTACHMENT7] desktop GL happily remaps location 0 into - WebGL2
# requires array position i to be exactly COLOR_ATTACHMENTi or NONE, with
# no reordering (see graphics/webgl/framebuffer.py's set_draw_buffers()).
# That means a fragment shader's real output must itself sit at location 7
# to land in the active slot at all; GL33Generator/WebGL2Generator both
# assign @output locations purely by declaration order starting at 0 (see
# WebGL2Generator.generate_inout()), so 7 throwaway leading fields shift
# the real one into position 7 - one per G-buffer channel PBRPipeline
# creates before 'lit' (albedo, normal, emmisive, roughness, metallic,
# gWorldPos, gWorldNormal - see PBRPipeline.on_initialize()'s
# main_framebuffer attachment dict). Never read back; their type doesn't
# need to match the real channel they're standing in for.
_LIT_ONLY_OUTPUT_PADDING = "\n".join(f"_pad{i}: vec4" for i in range(7))

# The PBR math (GGX distribution, Smith geometry, Schlick Fresnel) and the
# per-light falloff/shadow accumulation loop - identical text shared by the
# deferred composite pass and the forward-transparent pass, so both light
# scenes with the same formulas rather than two hand-maintained copies
# drifting apart.
_LIGHTING_FUNCTIONS = """
def pbr_distribution_ggx(n_dot_h: float, roughness: float) -> float:
    a: float = roughness * roughness
    a2: float = a * a
    d: float = (n_dot_h * n_dot_h) * (a2 - 1.0) + 1.0
    # 3.14159265 (pi) inlined directly - @define is parsed but never
    # actually registered anywhere in semantic analysis or codegen in this
    # FBUSL version (grep fbusl/semantic.py and fbusl/generator.py for
    # "Define" - neither references it), so a named @define constant
    # compiles the section itself fine but is unresolvable everywhere it's
    # actually used.
    return a2 / max(3.14159265 * d * d, 0.0001)

def pbr_geometry_schlick_ggx(n_dot_x: float, roughness: float) -> float:
    r: float = roughness + 1.0
    k: float = (r * r) / 8.0
    return n_dot_x / max(n_dot_x * (1.0 - k) + k, 0.0001)

def pbr_geometry_smith(n_dot_v: float, n_dot_l: float, roughness: float) -> float:
    return pbr_geometry_schlick_ggx(n_dot_v, roughness) * pbr_geometry_schlick_ggx(n_dot_l, roughness)

def pbr_fresnel_schlick(cos_theta: float, f0: vec3) -> vec3:
    p: float = pow(clamp(1.0 - cos_theta, 0.0, 1.0), 5.0)
    return f0 + (vec3(1.0, 1.0, 1.0) - f0) * p

def light_contribution(world_pos: vec3, normal: vec3, view_dir: vec3, albedo: vec3, f0: vec3, roughness: float, metallic: float, l_active: bool, l_type: int, l_pos: vec3, l_dir: vec3, l_color: vec3, l_intensity: float, l_range: float, l_spot_cos: float) -> vec3:
    if l_active == False:
        return vec3(0.0, 0.0, 0.0)

    to_light: vec3 = vec3(0.0, 0.0, 0.0)
    atten: float = 1.0

    if l_type == 1:
        # DIRECTIONAL - l_dir is the direction the light shines *toward*.
        to_light = normalize(l_dir * -1.0)
    else:
        diff: vec3 = l_pos - world_pos
        dist: float = length(diff)
        to_light = diff / max(dist, 0.0001)
        falloff: float = clamp(1.0 - (dist / max(l_range, 0.0001)), 0.0, 1.0)
        atten = falloff * falloff

        if l_type == 2:
            # SPOT - restrict POINT's falloff to a cone around l_dir.
            surface_dir: vec3 = normalize(diff * -1.0)
            spot_dot: float = dot(l_dir, surface_dir)
            edge: float = 0.08
            spot_factor: float = clamp((spot_dot - l_spot_cos) / max(edge, 0.0001), 0.0, 1.0)
            atten = atten * spot_factor

    n_dot_l: float = max(dot(normal, to_light), 0.0)
    if n_dot_l <= 0.0:
        return vec3(0.0, 0.0, 0.0)

    half_vec: vec3 = normalize(to_light + view_dir)
    n_dot_v: float = max(dot(normal, view_dir), 0.0001)
    n_dot_h: float = max(dot(normal, half_vec), 0.0)
    v_dot_h: float = max(dot(view_dir, half_vec), 0.0)

    d: float = pbr_distribution_ggx(n_dot_h, roughness)
    g: float = pbr_geometry_smith(n_dot_v, n_dot_l, roughness)
    f: vec3 = pbr_fresnel_schlick(v_dot_h, f0)

    specular: vec3 = (f * (d * g)) / (4.0 * n_dot_v * n_dot_l + 0.0001)
    kd: vec3 = (vec3(1.0, 1.0, 1.0) - f) * (1.0 - metallic)
    diffuse: vec3 = (kd * albedo) / 3.14159265

    radiance: vec3 = l_color * (l_intensity * atten)
    return (diffuse + specular) * radiance * n_dot_l

def shadow_factor(world_pos: vec3) -> float:
    if ShadowEnabled == False:
        return 1.0

    clip: vec4 = ShadowMatrix * vec4(world_pos.x, world_pos.y, world_pos.z, 1.0)
    ndc: vec3 = vec3(clip.x, clip.y, clip.z) / clip.w
    shadow_uv: vec2 = vec2(ndc.x * 0.5 + 0.5, ndc.y * 0.5 + 0.5)

    # Written as separate ifs rather than one `or`-chained condition -
    # FBUSL's expression parser doesn't fold keyword-lexed "and"/"or" into
    # its binary-operator precedence climb (they have PRECEDENCE table
    # entries but the parser's main loop only continues for
    # TokenType.OPERATOR, never TokenType.KEYWORD), so a chained boolean
    # condition silently truncates instead of raising - a real FBUSL parser
    # gap, not something to work around per-shader with a guess.
    in_bounds: bool = True
    if shadow_uv.x < 0.0:
        in_bounds = False
    if shadow_uv.x > 1.0:
        in_bounds = False
    if shadow_uv.y < 0.0:
        in_bounds = False
    if shadow_uv.y > 1.0:
        in_bounds = False

    if in_bounds == False:
        return 1.0

    frag_depth: float = ndc.z * 0.5 + 0.5
    map_depth: float = sample(ShadowMap, shadow_uv).x
    bias: float = 0.0025
    biased_depth: float = frag_depth - bias

    # The trailing (map_depth) parens are load-bearing, not style: FBUSL's
    # parser mis-parses a condition whose very last token is a bare
    # identifier directly followed by ":" - it speculatively treats that
    # identifier as the start of a new `name: type` var-decl statement
    # (see parse_identifier's `tok.value == ":"` branch in fbusl/parser.py)
    # and then fails looking for a type annotation that was never meant to
    # be there. Any bare identifier ending a condition needs this same
    # wrapping (a literal or a `== True`/`== False` comparison doesn't).
    if biased_depth > (map_depth):
        return 0.0
    return 1.0

def accumulate_lighting(world_pos: vec3, normal: vec3, view_pos: vec3, albedo: vec3, roughness: float, metallic: float, emissive: vec3, ambient: vec3) -> vec3:
    view_dir: vec3 = normalize(view_pos - world_pos)
    f0: vec3 = mix(vec3(0.04, 0.04, 0.04), albedo, metallic)

    total: vec3 = vec3(0.0, 0.0, 0.0)
""" + "\n".join(
    f"""    c{i}: vec3 = light_contribution(world_pos, normal, view_dir, albedo, f0, roughness, metallic, Light{i}_Active, Light{i}_Type, Light{i}_Position, Light{i}_Direction, Light{i}_Color, Light{i}_Intensity, Light{i}_Range, Light{i}_SpotCos)"""
    + ("\n    total = total + c0 * shadow_factor(world_pos)" if i == 0 else f"\n    total = total + c{i}")
    for i in range(MAX_LIGHTS)
) + """
    return albedo * ambient + total + emissive
"""

_LIGHT_UNIFORM_BLOCK = f"""
@uniform
{_LIGHT_UNIFORMS}

Ambient: vec3
ViewPos: vec3

ShadowEnabled: bool
ShadowMap: texture
ShadowMatrix: mat4
"""

LIGHTING_COMPOSITE_VERT = """
@uniform
model: mat4

@input
vertex: vec3
uvs: vec2
normal: vec3

@output
uv: vec2

def main():
    uv = uvs
    VERTEX_POSITION = model * vec4(vertex.x, vertex.y, vertex.z, 1.0)
"""

LIGHTING_COMPOSITE_FRAG = f"""
@output
{_LIT_ONLY_OUTPUT_PADDING}
result: vec4

@uniform
gAlbedo: texture
gEmmisive: texture
gRoughness: texture
gMetallic: texture
gWorldPos: texture
gWorldNormal: texture
{_LIGHT_UNIFORM_BLOCK}
@input
uv: vec2

{_LIGHTING_FUNCTIONS}

def main() -> void:
    world_pos4: vec4 = sample(gWorldPos, uv)

    if world_pos4.w < 0.5:
        result = vec4(0.0, 0.0, 0.0, 0.0)
    else:
        world_pos: vec3 = vec3(world_pos4.x, world_pos4.y, world_pos4.z)
        normal: vec3 = normalize(vec3(sample(gWorldNormal, uv).x, sample(gWorldNormal, uv).y, sample(gWorldNormal, uv).z))
        albedo4: vec4 = sample(gAlbedo, uv)
        albedo: vec3 = vec3(albedo4.x, albedo4.y, albedo4.z)
        emissive: vec3 = vec3(sample(gEmmisive, uv).x, sample(gEmmisive, uv).y, sample(gEmmisive, uv).z)
        roughness: float = clamp(sample(gRoughness, uv).x, 0.04, 1.0)
        metallic: float = sample(gMetallic, uv).x

        lit: vec3 = accumulate_lighting(world_pos, normal, ViewPos, albedo, roughness, metallic, emissive, Ambient)
        result = vec4(lit.x, lit.y, lit.z, albedo4.w)
"""
