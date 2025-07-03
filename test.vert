#version 330 core

in vec3 vertex;

in vec2 uvs;

out vec2 uv;

void main() {
    uv = vec2(uvs.x, 1.0);
    gl_Position = vec4(vertex.x, uvs.y, 0.0, 1.0);
};