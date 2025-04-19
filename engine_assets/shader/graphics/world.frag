#version 330 core

uniform sampler2D tex;
uniform sampler2D normal_tex;

in vec2 uv;
out vec4 frag_albedo;  // Diffuse color
out vec4 frag_normal;  // Normal data

void main() {
    frag_albedo = texture(tex, uv);
    
    // Convert normal map from [0,1] to [-1,1] range
    vec4 normal = texture(normal_tex, uv).rgba;
    frag_normal = normal;
}