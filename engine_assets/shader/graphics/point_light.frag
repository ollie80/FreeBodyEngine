#version 330 core

uniform vec2 screen_size;

uniform vec2 light_position;
uniform vec3 light_color;
uniform float light_intensity;
uniform float light_radius;

uniform mat4 view;
uniform mat4 proj;

out vec4 frag_color;

void main() {
    vec4 frag_ndc = vec4((gl_FragCoord.xy / screen_size) * 2.0 - 1.0, 0.0, 1.0);
    vec4 frag_world = inverse(proj * view) * frag_ndc;
    frag_world /= frag_world.w;

    float dist = length(light_position - frag_world.xy);

    if (dist > light_radius) discard;

    float attenuation = 1.0 - (dist / light_radius);
    vec3 color = light_color * light_intensity * attenuation;

    frag_color = vec4(color, 1.0);
}
