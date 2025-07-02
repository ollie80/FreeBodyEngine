#version 330 core

uniform vec2 dir_direction;
uniform vec3 dir_color;
uniform float dir_intensity;

out vec4 frag_color;

void main() {
    // Simulate constant directional light
    vec3 color = dir_color * dir_intensity;
    frag_color = vec4(color, 1.0);
}
