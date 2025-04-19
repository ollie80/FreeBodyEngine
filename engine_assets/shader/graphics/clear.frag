#version 330 core

uniform vec3 normal_color;
uniform vec3 albedo_color;

out vec4 frag_albedo;
out vec4 frag_normal;

void main() {
    frag_albedo = vec4(albedo_color, 1.0);
    frag_normal = vec4(normal_color, 1.0);
}