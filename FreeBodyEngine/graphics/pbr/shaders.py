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

def shadow_tap(u: float, v: float, biased_depth: float) -> float:
    # One shadow-map comparison: 0 if something is nearer the light here.
    map_depth: float = sample(ShadowMap, vec2(u, v)).x

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
    bias: float = 0.0025
    biased_depth: float = frag_depth - bias

    # Percentage-closer filtering: sixteen comparisons on a 4x4 grid around
    # the sample point, averaged.
    #
    # One comparison returns only 0 or 1, so a shadow edge lands exactly on
    # a shadow-map texel boundary and stair-steps along it - at a 2048 map
    # covering a hundred-odd metres, one texel is several screen pixels
    # across, which is far too coarse for a post-process pass like FXAA to
    # do anything with. Averaging the comparisons gives seventeen levels
    # between lit and shadowed instead of two, which is both the
    # antialiasing and the soft edge.
    #
    # Unrolled because FBUSL has no loops. The offsets are the four
    # half-texel positions in each axis, scaled by ShadowSoftnessRadius.
    step: float = ShadowTexelSize * ShadowSoftnessRadius
    near_offset: float = step * 0.5
    far_offset: float = step * 1.5

    u0: float = shadow_uv.x - far_offset
    u1: float = shadow_uv.x - near_offset
    u2: float = shadow_uv.x + near_offset
    u3: float = shadow_uv.x + far_offset
    v0: float = shadow_uv.y - far_offset
    v1: float = shadow_uv.y - near_offset
    v2: float = shadow_uv.y + near_offset
    v3: float = shadow_uv.y + far_offset

    total: float = shadow_tap(u0, v0, biased_depth)
    total = total + shadow_tap(u1, v0, biased_depth)
    total = total + shadow_tap(u2, v0, biased_depth)
    total = total + shadow_tap(u3, v0, biased_depth)
    total = total + shadow_tap(u0, v1, biased_depth)
    total = total + shadow_tap(u1, v1, biased_depth)
    total = total + shadow_tap(u2, v1, biased_depth)
    total = total + shadow_tap(u3, v1, biased_depth)
    total = total + shadow_tap(u0, v2, biased_depth)
    total = total + shadow_tap(u1, v2, biased_depth)
    total = total + shadow_tap(u2, v2, biased_depth)
    total = total + shadow_tap(u3, v2, biased_depth)
    total = total + shadow_tap(u0, v3, biased_depth)
    total = total + shadow_tap(u1, v3, biased_depth)
    total = total + shadow_tap(u2, v3, biased_depth)
    total = total + shadow_tap(u3, v3, biased_depth)

    return total * 0.0625

def light_visibility(world_pos: vec3, light_pos: vec3, l_type: int, lit: bool) -> float:
    # Whether a light reaches a point, or a wall is in the way.
    #
    # A 2D occlusion march rather than a shadow map: the occluders are the
    # tilemap's own solid tiles, uploaded as a world-space mask (see
    # PBRPipeline.set_occluders), and this walks the straight line from the
    # surface to the light looking for one. That suits a tile world exactly -
    # the occluders are already a grid, so a texture lookup *is* the
    # intersection test, and there is no per-light render pass and nothing to
    # rebuild when a light moves.
    #
    # Unrolled because FBUSL has no `for`; the step count is a Python constant
    # in this file, so the cost is fixed and visible rather than hidden in a
    # loop bound.
    if OccluderEnabled == False:
        return 1.0
    if lit == False:
        return 1.0

    # Directional light only - 1 in the uniform encoding (POINT is 0, see
    # PBRPipeline._light_uniform_values). It has no position to march toward,
    # and it already has a real shadow map of its own.
    if l_type == 1:
        return 1.0

    ray: vec2 = vec2(light_pos.x - world_pos.x, light_pos.y - world_pos.y)
    dist: float = length(ray)
    if dist < 0.001:
        return 1.0

    # The march starts a little away from the surface and stops a little
    # short of the light. Without the first, a wall shadows itself and every
    # wall face in the room goes black; without the second, a light sitting
    # inside a wall tile - a sconce mounted on one - puts out nothing.
    # The bias is in world units, so it does not shrink with distance.
    bias: float = clamp(10.0 / dist, 0.0, 0.4)
    span: float = 0.9 - bias

    # Softness is the light's apparent size in world units. Each step samples
    # across a band perpendicular to the ray, and that band widens along the
    # ray toward the light - so an occluder close to the light throws a broad,
    # soft edge and one pressed against the surface throws a sharp one, which
    # is how a real penumbra behaves. At zero the three taps collapse onto each
    # other and the edge is as hard as the mask's own texel.
    perp: vec2 = vec2(ray.y * -1.0 / dist, ray.x / dist)

    coverage: float = 0.0
    f0: float = bias + span * 0.00000
    p0: vec2 = vec2(world_pos.x + ray.x * f0, world_pos.y + ray.y * f0)
    w0: float = ShadowSoftness * f0
    o0: vec2 = vec2(perp.x * w0, perp.y * w0)
    m0: float = sample(OccluderMap, vec2((p0.x - OccluderOrigin.x) / OccluderExtent.x, (p0.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a0: float = sample(OccluderMap, vec2((p0.x + o0.x - OccluderOrigin.x) / OccluderExtent.x, (p0.y + o0.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b0: float = sample(OccluderMap, vec2((p0.x - o0.x - OccluderOrigin.x) / OccluderExtent.x, (p0.y - o0.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m0 + a0 + b0) * 0.3333333)
    f1: float = bias + span * 0.07692
    p1: vec2 = vec2(world_pos.x + ray.x * f1, world_pos.y + ray.y * f1)
    w1: float = ShadowSoftness * f1
    o1: vec2 = vec2(perp.x * w1, perp.y * w1)
    m1: float = sample(OccluderMap, vec2((p1.x - OccluderOrigin.x) / OccluderExtent.x, (p1.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a1: float = sample(OccluderMap, vec2((p1.x + o1.x - OccluderOrigin.x) / OccluderExtent.x, (p1.y + o1.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b1: float = sample(OccluderMap, vec2((p1.x - o1.x - OccluderOrigin.x) / OccluderExtent.x, (p1.y - o1.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m1 + a1 + b1) * 0.3333333)
    f2: float = bias + span * 0.15385
    p2: vec2 = vec2(world_pos.x + ray.x * f2, world_pos.y + ray.y * f2)
    w2: float = ShadowSoftness * f2
    o2: vec2 = vec2(perp.x * w2, perp.y * w2)
    m2: float = sample(OccluderMap, vec2((p2.x - OccluderOrigin.x) / OccluderExtent.x, (p2.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a2: float = sample(OccluderMap, vec2((p2.x + o2.x - OccluderOrigin.x) / OccluderExtent.x, (p2.y + o2.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b2: float = sample(OccluderMap, vec2((p2.x - o2.x - OccluderOrigin.x) / OccluderExtent.x, (p2.y - o2.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m2 + a2 + b2) * 0.3333333)
    f3: float = bias + span * 0.23077
    p3: vec2 = vec2(world_pos.x + ray.x * f3, world_pos.y + ray.y * f3)
    w3: float = ShadowSoftness * f3
    o3: vec2 = vec2(perp.x * w3, perp.y * w3)
    m3: float = sample(OccluderMap, vec2((p3.x - OccluderOrigin.x) / OccluderExtent.x, (p3.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a3: float = sample(OccluderMap, vec2((p3.x + o3.x - OccluderOrigin.x) / OccluderExtent.x, (p3.y + o3.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b3: float = sample(OccluderMap, vec2((p3.x - o3.x - OccluderOrigin.x) / OccluderExtent.x, (p3.y - o3.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m3 + a3 + b3) * 0.3333333)
    f4: float = bias + span * 0.30769
    p4: vec2 = vec2(world_pos.x + ray.x * f4, world_pos.y + ray.y * f4)
    w4: float = ShadowSoftness * f4
    o4: vec2 = vec2(perp.x * w4, perp.y * w4)
    m4: float = sample(OccluderMap, vec2((p4.x - OccluderOrigin.x) / OccluderExtent.x, (p4.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a4: float = sample(OccluderMap, vec2((p4.x + o4.x - OccluderOrigin.x) / OccluderExtent.x, (p4.y + o4.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b4: float = sample(OccluderMap, vec2((p4.x - o4.x - OccluderOrigin.x) / OccluderExtent.x, (p4.y - o4.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m4 + a4 + b4) * 0.3333333)
    f5: float = bias + span * 0.38462
    p5: vec2 = vec2(world_pos.x + ray.x * f5, world_pos.y + ray.y * f5)
    w5: float = ShadowSoftness * f5
    o5: vec2 = vec2(perp.x * w5, perp.y * w5)
    m5: float = sample(OccluderMap, vec2((p5.x - OccluderOrigin.x) / OccluderExtent.x, (p5.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a5: float = sample(OccluderMap, vec2((p5.x + o5.x - OccluderOrigin.x) / OccluderExtent.x, (p5.y + o5.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b5: float = sample(OccluderMap, vec2((p5.x - o5.x - OccluderOrigin.x) / OccluderExtent.x, (p5.y - o5.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m5 + a5 + b5) * 0.3333333)
    f6: float = bias + span * 0.46154
    p6: vec2 = vec2(world_pos.x + ray.x * f6, world_pos.y + ray.y * f6)
    w6: float = ShadowSoftness * f6
    o6: vec2 = vec2(perp.x * w6, perp.y * w6)
    m6: float = sample(OccluderMap, vec2((p6.x - OccluderOrigin.x) / OccluderExtent.x, (p6.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a6: float = sample(OccluderMap, vec2((p6.x + o6.x - OccluderOrigin.x) / OccluderExtent.x, (p6.y + o6.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b6: float = sample(OccluderMap, vec2((p6.x - o6.x - OccluderOrigin.x) / OccluderExtent.x, (p6.y - o6.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m6 + a6 + b6) * 0.3333333)
    f7: float = bias + span * 0.53846
    p7: vec2 = vec2(world_pos.x + ray.x * f7, world_pos.y + ray.y * f7)
    w7: float = ShadowSoftness * f7
    o7: vec2 = vec2(perp.x * w7, perp.y * w7)
    m7: float = sample(OccluderMap, vec2((p7.x - OccluderOrigin.x) / OccluderExtent.x, (p7.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a7: float = sample(OccluderMap, vec2((p7.x + o7.x - OccluderOrigin.x) / OccluderExtent.x, (p7.y + o7.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b7: float = sample(OccluderMap, vec2((p7.x - o7.x - OccluderOrigin.x) / OccluderExtent.x, (p7.y - o7.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m7 + a7 + b7) * 0.3333333)
    f8: float = bias + span * 0.61538
    p8: vec2 = vec2(world_pos.x + ray.x * f8, world_pos.y + ray.y * f8)
    w8: float = ShadowSoftness * f8
    o8: vec2 = vec2(perp.x * w8, perp.y * w8)
    m8: float = sample(OccluderMap, vec2((p8.x - OccluderOrigin.x) / OccluderExtent.x, (p8.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a8: float = sample(OccluderMap, vec2((p8.x + o8.x - OccluderOrigin.x) / OccluderExtent.x, (p8.y + o8.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b8: float = sample(OccluderMap, vec2((p8.x - o8.x - OccluderOrigin.x) / OccluderExtent.x, (p8.y - o8.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m8 + a8 + b8) * 0.3333333)
    f9: float = bias + span * 0.69231
    p9: vec2 = vec2(world_pos.x + ray.x * f9, world_pos.y + ray.y * f9)
    w9: float = ShadowSoftness * f9
    o9: vec2 = vec2(perp.x * w9, perp.y * w9)
    m9: float = sample(OccluderMap, vec2((p9.x - OccluderOrigin.x) / OccluderExtent.x, (p9.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a9: float = sample(OccluderMap, vec2((p9.x + o9.x - OccluderOrigin.x) / OccluderExtent.x, (p9.y + o9.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b9: float = sample(OccluderMap, vec2((p9.x - o9.x - OccluderOrigin.x) / OccluderExtent.x, (p9.y - o9.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m9 + a9 + b9) * 0.3333333)
    f10: float = bias + span * 0.76923
    p10: vec2 = vec2(world_pos.x + ray.x * f10, world_pos.y + ray.y * f10)
    w10: float = ShadowSoftness * f10
    o10: vec2 = vec2(perp.x * w10, perp.y * w10)
    m10: float = sample(OccluderMap, vec2((p10.x - OccluderOrigin.x) / OccluderExtent.x, (p10.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a10: float = sample(OccluderMap, vec2((p10.x + o10.x - OccluderOrigin.x) / OccluderExtent.x, (p10.y + o10.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b10: float = sample(OccluderMap, vec2((p10.x - o10.x - OccluderOrigin.x) / OccluderExtent.x, (p10.y - o10.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m10 + a10 + b10) * 0.3333333)
    f11: float = bias + span * 0.84615
    p11: vec2 = vec2(world_pos.x + ray.x * f11, world_pos.y + ray.y * f11)
    w11: float = ShadowSoftness * f11
    o11: vec2 = vec2(perp.x * w11, perp.y * w11)
    m11: float = sample(OccluderMap, vec2((p11.x - OccluderOrigin.x) / OccluderExtent.x, (p11.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a11: float = sample(OccluderMap, vec2((p11.x + o11.x - OccluderOrigin.x) / OccluderExtent.x, (p11.y + o11.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b11: float = sample(OccluderMap, vec2((p11.x - o11.x - OccluderOrigin.x) / OccluderExtent.x, (p11.y - o11.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m11 + a11 + b11) * 0.3333333)
    f12: float = bias + span * 0.92308
    p12: vec2 = vec2(world_pos.x + ray.x * f12, world_pos.y + ray.y * f12)
    w12: float = ShadowSoftness * f12
    o12: vec2 = vec2(perp.x * w12, perp.y * w12)
    m12: float = sample(OccluderMap, vec2((p12.x - OccluderOrigin.x) / OccluderExtent.x, (p12.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a12: float = sample(OccluderMap, vec2((p12.x + o12.x - OccluderOrigin.x) / OccluderExtent.x, (p12.y + o12.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b12: float = sample(OccluderMap, vec2((p12.x - o12.x - OccluderOrigin.x) / OccluderExtent.x, (p12.y - o12.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m12 + a12 + b12) * 0.3333333)
    f13: float = bias + span * 1.00000
    p13: vec2 = vec2(world_pos.x + ray.x * f13, world_pos.y + ray.y * f13)
    w13: float = ShadowSoftness * f13
    o13: vec2 = vec2(perp.x * w13, perp.y * w13)
    m13: float = sample(OccluderMap, vec2((p13.x - OccluderOrigin.x) / OccluderExtent.x, (p13.y - OccluderOrigin.y) / OccluderExtent.y)).x
    a13: float = sample(OccluderMap, vec2((p13.x + o13.x - OccluderOrigin.x) / OccluderExtent.x, (p13.y + o13.y - OccluderOrigin.y) / OccluderExtent.y)).x
    b13: float = sample(OccluderMap, vec2((p13.x - o13.x - OccluderOrigin.x) / OccluderExtent.x, (p13.y - o13.y - OccluderOrigin.y) / OccluderExtent.y)).x
    coverage = max(coverage, (m13 + a13 + b13) * 0.3333333)

    # Mapped through a narrow ramp rather than a threshold: at zero softness
    # the taps coincide and the mask's own linear filtering makes this a one
    # texel transition, which reads as the hard edge it was before.
    return 1.0 - clamp((coverage - 0.35) / 0.3, 0.0, 1.0)

def accumulate_lighting(world_pos: vec3, normal: vec3, view_pos: vec3, albedo: vec3, roughness: float, metallic: float, emissive: vec3, ambient: vec3) -> vec3:
    view_dir: vec3 = normalize(view_pos - world_pos)
    f0: vec3 = mix(vec3(0.04, 0.04, 0.04), albedo, metallic)

    total: vec3 = vec3(0.0, 0.0, 0.0)
""" + "\n".join(
    f"""    c{i}: vec3 = light_contribution(world_pos, normal, view_dir, albedo, f0, roughness, metallic, Light{i}_Active, Light{i}_Type, Light{i}_Position, Light{i}_Direction, Light{i}_Color, Light{i}_Intensity, Light{i}_Range, Light{i}_SpotCos)
    v{i}: float = light_visibility(world_pos, Light{i}_Position, Light{i}_Type, Light{i}_Active)"""
    + ("\n    total = total + c0 * shadow_factor(world_pos) * v0" if i == 0 else f"\n    total = total + c{i} * v{i}")
    for i in range(MAX_LIGHTS)
) + """
    return albedo * ambient + total + emissive
"""

_LIGHT_UNIFORM_BLOCK = f"""
@uniform
{_LIGHT_UNIFORMS}

Ambient: vec3
ViewPos: vec3
Unlit: bool

ShadowEnabled: bool
ShadowMap: texture
# One texel of the shadow map in UV space (1 / SHADOW_MAP_SIZE), and how
# many texels wide the PCF kernel reaches - see shadow_factor.
ShadowTexelSize: float
ShadowSoftnessRadius: float
# Distance fog. `FogColor` is what a surface fades to, `FogStart` the
# distance it begins at and `FogEnd` where it is fully fogged; `FogDensity`
# scales the whole effect (0 disables it). Fog is applied in the composite
# rather than per material so it covers everything the G-buffer holds,
# which is the point - a city that fades into its own sky needs the fade on
# the buildings, not on one material.
FogColor: vec3
FogStart: float
FogEnd: float
FogDensity: float
ShadowMatrix: mat4

OccluderEnabled: bool
OccluderMap: texture
OccluderOrigin: vec2
OccluderExtent: vec2
ShadowSoftness: float
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
    # UV is derived from the clip-space position, not taken from the quad's
    # own `uvs` attribute. The fullscreen quad comes from generate_quad(),
    # whose UVs are authored for the engine's *standalone* textures - those
    # are uploaded rotated 180 degrees (see decode_image_bytes), so its u
    # runs 1 -> 0 left to right to compensate. A G-buffer attachment is not
    # rotated: it was rendered in normal screen orientation. Sampling it
    # through that quad's attribute therefore mirrored the entire composited
    # frame horizontally - every 2D scene came out flipped left-to-right,
    # while the raw 'albedo' channel (blitted straight to the window, never
    # resampled) looked correct, which is what made it look like a
    # per-sprite UV problem rather than one in this pass.
    #
    # Deriving it here instead means this pass makes no assumption about any
    # texture-orientation convention: the quad is already in NDC (model is
    # identity), so this is just the standard NDC -> [0,1] remap, and v
    # still runs with +y, matching GL's bottom-origin framebuffer textures.
    clip: vec4 = model * vec4(vertex.x, vertex.y, vertex.z, 1.0)
    uv = vec2(clip.x * 0.5 + 0.5, clip.y * 0.5 + 0.5)
    VERTEX_POSITION = clip
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
gNormal: texture
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

        # The geometric (interpolated surface) normal.
        geom_normal: vec3 = normalize(vec3(sample(gWorldNormal, uv).x, sample(gWorldNormal, uv).y, sample(gWorldNormal, uv).z))

        # The 'normal' G-buffer channel - the normal *map* - is now read.
        # It was written by every shader that fills the G-buffer but no pass
        # ever sampled it: this frag declared gAlbedo/gEmmisive/gRoughness/
        # gMetallic/gWorldPos/gWorldNormal and simply had no gNormal, so a
        # normal map changed nothing anywhere in the engine. Lighting used
        # the flat facing normal for every surface, which for 2D means every
        # sprite and tile was lit by distance falloff alone, with no surface
        # relief at all - and 2D art in this engine ships a normal map per
        # sheet precisely to get that relief.
        #
        # Applied in world space rather than through a tangent basis: the
        # G-buffer carries no tangents, and for the 2D case every surface is
        # a quad facing +Z, so tangent space and world space coincide and a
        # map's RGB is already its world-space normal. A 3D mesh with a
        # normal map wants a real TBN and does not get one here.
        normal_sample: vec4 = sample(gNormal, uv)
        mapped_normal: vec3 = vec3(normal_sample.x * 2.0 - 1.0, normal_sample.y * 2.0 - 1.0, normal_sample.z * 2.0 - 1.0)

        normal: vec3 = geom_normal
        # A surface with no normal map leaves this channel at zero (see
        # Material.use()'s own fallback, and TilemapRenderer's), which decodes
        # to (-1,-1,-1) - a direction, not a "no data" value, so it has to be
        # detected before decoding, on the raw sample. Summed into a local
        # first because FBUSL's parser does not accept a parenthesised
        # expression as a comparison's left operand in an `if`.
        normal_sum: float = normal_sample.x + normal_sample.y + normal_sample.z
        if normal_sum > 0.0:
            normal = normalize(mapped_normal)

        albedo4: vec4 = sample(gAlbedo, uv)
        albedo: vec3 = vec3(albedo4.x, albedo4.y, albedo4.z)
        emissive: vec3 = vec3(sample(gEmmisive, uv).x, sample(gEmmisive, uv).y, sample(gEmmisive, uv).z)
        roughness: float = clamp(sample(gRoughness, uv).x, 0.04, 1.0)
        metallic: float = sample(gMetallic, uv).x

        shaded: vec3 = vec3(albedo.x + emissive.x, albedo.y + emissive.y, albedo.z + emissive.z)
        if Unlit == False:
            shaded = accumulate_lighting(world_pos, normal, ViewPos, albedo, roughness, metallic, emissive, Ambient)

        # Distance fog, from the camera to this fragment's world position.
        # Linear between FogStart and FogEnd rather than exponential: a
        # linear ramp has an exact distance at which something is fully
        # gone, which is what lets it be matched to the camera's far plane
        # so geometry fades out instead of popping out.
        fog_dx: float = world_pos.x - ViewPos.x
        fog_dy: float = world_pos.y - ViewPos.y
        fog_dz: float = world_pos.z - ViewPos.z
        fog_distance: float = sqrt(fog_dx * fog_dx + fog_dy * fog_dy + fog_dz * fog_dz)
        fog_span: float = max(FogEnd - FogStart, 0.0001)
        # gWorldNormal.w doubles as a per-surface fog mask: 1 fogs normally,
        # 0 exempts the surface. Every shader in the engine already writes
        # 1.0 there (it was a "real geometry was rasterized here" sentinel
        # and nothing read it - only .xyz is sampled), so this costs no
        # channel and changes nothing that existed. A skybox needs it: it is
        # real geometry at a real distance, so distance fog would otherwise
        # fog the sky into flat grey, which is both wrong and exactly what
        # the fog is meant to make the buildings fade *into*.
        fog_mask: float = sample(gWorldNormal, uv).w
        fog_amount: float = clamp((fog_distance - FogStart) / fog_span, 0.0, 1.0) * FogDensity * fog_mask

        shaded = mix(shaded, FogColor, fog_amount)

        result = vec4(shaded.x, shaded.y, shaded.z, albedo4.w)
"""


# FXAA, as the pipeline's final pass - see PBRPipeline._draw_fxaa.
#
# Why post-process antialiasing and not MSAA: this is a deferred renderer.
# MSAA antialiases by keeping several samples per pixel and resolving them at
# the end, which works when the thing being resolved is shaded colour. Here
# the thing rasterized into the G-buffer is raw surface data - world
# positions, normals, roughness - and the lighting composite reads it back
# per pixel afterwards. Averaging world positions and normals across an edge
# produces a surface that was never there and lights it accordingly, so the
# G-buffer would have to stay multisampled all the way through the composite
# (every attachment a multisample texture, the composite running per sample)
# to be correct. That is several times the bandwidth and a rewrite of the
# composite. FXAA runs on the finished image instead, costs one fullscreen
# pass, and needs nothing from the rest of the pipeline.
FXAA_VERT = """
@uniform
model: mat4

@input
vertex: vec3
uvs: vec2
normal: vec3

@output
uv: vec2

def main():
    # UV from the clip-space position rather than the quad's own attribute,
    # for the same reason the lighting composite does it - see
    # LIGHTING_COMPOSITE_VERT's note. generate_quad's UVs are authored for
    # the engine's rotated standalone textures; a framebuffer attachment is
    # not rotated, and sampling it through that attribute mirrors the frame.
    clip: vec4 = model * vec4(vertex.x, vertex.y, vertex.z, 1.0)
    uv = vec2(clip.x * 0.5 + 0.5, clip.y * 0.5 + 0.5)
    VERTEX_POSITION = vec4(clip.x, clip.y, 0.0, 1.0)
"""


FXAA_FRAG = """
@uniform
Screen: texture
# One texel in UV space: (1/width, 1/height) of the framebuffer being
# filtered, not of the window. The two differ whenever the window is scaled.
InverseResolution: vec2
# Speed lines, drawn after the AA resolve in this same pass - they are a
# screen-space overlay, so they belong at the very end and get the finished
# image for free rather than costing another fullscreen pass.
# 0 disables them entirely.
SpeedLineStrength: float
SpeedLineColor: vec3
# How far out from the centre the lines begin, as a fraction of the
# half-diagonal. Keeping them off the middle of the screen is what makes
# them read as speed rather than as a dirty lens.
SpeedLineInnerRadius: float
# Width of each streak, and how many there are around the circle.
SpeedLineWidth: float
SpeedLineCount: float
# Aspect ratio (width / height), so the lines stay radial instead of being
# squashed into ellipses on a wide window.
ScreenAspect: float
# How strong an edge has to be before it is smoothed at all, as a fraction
# of the brighter side's luma, plus an absolute floor so near-black areas
# are not filtered on noise alone.
EdgeThreshold: float
EdgeThresholdMin: float
# How far along an edge the blur may reach, in texels.
SpanMax: float

@output
result: vec4

@input
uv: vec2

def luma(color: vec3) -> float:
    # Perceptual weighting. FXAA works entirely on luminance, because that is
    # what the eye reads an aliased edge from - a pure hue change at equal
    # brightness barely registers as a staircase.
    return color.x * 0.299 + color.y * 0.587 + color.z * 0.114

def speed_line_hash(n: float) -> float:
    # One pseudo-random value per streak, so they are not all the same
    # length and width - evenly spaced identical spokes read as a wheel,
    # not as motion.
    return fract(sin(n * 78.233) * 43758.5453123)

def speed_lines(color: vec3, uv: vec2) -> vec3:
    if SpeedLineStrength <= 0.0:
        return color

    # Centre-relative, with x scaled by the aspect ratio so "radial" means
    # radial on screen rather than in UV space.
    dx: float = (uv.x - 0.5) * ScreenAspect
    dy: float = uv.y - 0.5
    radius: float = sqrt(dx * dx + dy * dy)

    if radius <= 0.0001:
        return color

    # Angle around the centre. This is the whole reason atan had to be added
    # to FBUSL - without it there is no way to turn a direction into an
    # angle, and these lines are a function of angle.
    angle: float = atan(dy, dx)

    # Which streak this fragment belongs to, and how far across it we are.
    position: float = (angle * 0.15915494) * SpeedLineCount
    index: float = floor(position)
    across: float = position - index

    seed: float = speed_line_hash(index)

    # Distance from the centre line of this streak, scaled by a per-streak
    # width so they vary.
    offset: float = abs(across - 0.5) * 2.0
    width: float = SpeedLineWidth * (0.45 + seed * 0.55)
    line: float = 1.0 - smoothstep(0.0, width, offset)

    # Each streak starts at its own radius, so they have different lengths
    # and the effect does not have one hard inner edge all the way round.
    start: float = SpeedLineInnerRadius * (0.72 + seed * 0.55)
    reach: float = smoothstep(start, start + 0.34, radius)

    return color + SpeedLineColor * (line * reach * SpeedLineStrength)

def main() -> void:
    inv_x: float = InverseResolution.x
    inv_y: float = InverseResolution.y

    rgb_m: vec3 = sample(Screen, uv).xyz
    rgb_nw: vec3 = sample(Screen, vec2(uv.x - inv_x, uv.y - inv_y)).xyz
    rgb_ne: vec3 = sample(Screen, vec2(uv.x + inv_x, uv.y - inv_y)).xyz
    rgb_sw: vec3 = sample(Screen, vec2(uv.x - inv_x, uv.y + inv_y)).xyz
    rgb_se: vec3 = sample(Screen, vec2(uv.x + inv_x, uv.y + inv_y)).xyz

    luma_m: float = luma(rgb_m)
    luma_nw: float = luma(rgb_nw)
    luma_ne: float = luma(rgb_ne)
    luma_sw: float = luma(rgb_sw)
    luma_se: float = luma(rgb_se)

    luma_min: float = min(luma_m, min(min(luma_nw, luma_ne), min(luma_sw, luma_se)))
    luma_max: float = max(luma_m, max(max(luma_nw, luma_ne), max(luma_sw, luma_se)))
    luma_range: float = luma_max - luma_min

    # Flat enough to leave alone. Skipping here is most of why FXAA is cheap
    # on a scene like this one, where large flat areas of road and sky have
    # no edge in them at all.
    # Hoisted into a local, and parenthesised: FBUSL's parser cannot take a
    # call as the right operand of a comparison in an `if`, and a condition
    # whose last token is a bare identifier is speculatively read as the
    # start of a `name: type` declaration (see shadow_factor's note).
    edge_limit: float = max(EdgeThresholdMin, luma_max * EdgeThreshold)
    # Flat enough that the AA resolve would change nothing - but the speed
    # lines still have to be applied, so this returns through the same exit
    # as everything else rather than short-circuiting the whole shader.
    # Returning early here meant the overlay only ever drew on the handful
    # of pixels FXAA considered an edge, which looked like scattered dots
    # along geometry rather than like speed lines.
    if luma_range < (edge_limit):
        flat_out: vec3 = speed_lines(rgb_m, uv)
        result = vec4(flat_out.x, flat_out.y, flat_out.z, 1.0)
        return

    # The edge's direction, as the luma gradient across the four diagonal
    # neighbours, turned 90 degrees so it runs *along* the edge rather than
    # across it. Blurring along an edge is what removes the staircase while
    # leaving the edge itself sharp.
    dir_x: float = 0.0 - ((luma_nw + luma_ne) - (luma_sw + luma_se))
    dir_y: float = (luma_nw + luma_sw) - (luma_ne + luma_se)

    # Scale the step up on weak gradients and down on strong ones, with a
    # floor so a near-zero gradient cannot blow the direction up.
    reduce_floor: float = max((luma_nw + luma_ne + luma_sw + luma_se) * 0.03125, 0.0078125)
    rcp_dir_min: float = 1.0 / (min(abs(dir_x), abs(dir_y)) + reduce_floor)

    dir_x = clamp(dir_x * rcp_dir_min, 0.0 - SpanMax, SpanMax) * inv_x
    dir_y = clamp(dir_y * rcp_dir_min, 0.0 - SpanMax, SpanMax) * inv_y

    # Two pairs of taps along that direction. The inner pair (rgb_a) is a
    # conservative blur; the outer pair widens it. If the wider one has
    # strayed outside the luma range of the original neighbourhood it has
    # reached past the edge onto something unrelated, so the narrow one is
    # used instead - that test is what stops FXAA smearing thin features.
    inner_1: vec3 = sample(Screen, vec2(uv.x + dir_x * (0.0 - 0.16666667), uv.y + dir_y * (0.0 - 0.16666667))).xyz
    inner_2: vec3 = sample(Screen, vec2(uv.x + dir_x * 0.16666667, uv.y + dir_y * 0.16666667)).xyz
    rgb_a: vec3 = (inner_1 + inner_2) * 0.5

    outer_1: vec3 = sample(Screen, vec2(uv.x + dir_x * (0.0 - 0.5), uv.y + dir_y * (0.0 - 0.5))).xyz
    outer_2: vec3 = sample(Screen, vec2(uv.x + dir_x * 0.5, uv.y + dir_y * 0.5)).xyz
    rgb_b: vec3 = rgb_a * 0.5 + (outer_1 + outer_2) * 0.25

    luma_b: float = luma(rgb_b)

    # Written as two ifs rather than one or-chained condition: FBUSL's
    # expression parser does not fold keyword-lexed and/or into its operator
    # precedence climb, so a chained boolean condition truncates silently.
    # See shadow_factor above, which has the same note.
    use_wide: bool = True
    if luma_b < (luma_min):
        use_wide = False
    if luma_b > (luma_max):
        use_wide = False

    resolved: vec3 = rgb_a
    if use_wide == True:
        resolved = rgb_b

    resolved = speed_lines(resolved, uv)
    result = vec4(resolved.x, resolved.y, resolved.z, 1.0)
"""
