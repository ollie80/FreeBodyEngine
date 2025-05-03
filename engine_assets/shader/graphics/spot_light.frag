#version 330 core

uniform vec2 screen_size;

uniform vec2 spot_position;
uniform vec2 spot_direction;
uniform vec3 spot_color;
uniform float spot_angle;
uniform float spot_intensity;
uniform float spot_radius;

uniform mat4 view;
uniform mat4 proj;

out vec4 frag_color;

void main() {
    vec4 frag_ndc = vec4((gl_FragCoord.xy / screen_size) * 2.0 - 1.0, 0.0, 1.0);
    vec4 frag_world = inverse(proj * view) * frag_ndc;
    frag_world /= frag_world.w;

    float dist = length(spot_position - frag_world.xy);
    if (dist > spot_radius) discard;

    vec2 to_frag = normalize(frag_world.xy - spot_position);
    float angle_diff = dot(to_frag, normalize(spot_direction));
    float spot_effect = smoothstep(cos(spot_angle), cos(spot_angle * 0.9), angle_diff);

    float attenuation = 1.0 - (dist / spot_radius);
    vec3 color = spot_color * spot_intensity * attenuation * spot_effect;

    frag_color = vec4(color, 1.0);
}
