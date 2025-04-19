#version 330 core

uniform mat4 proj;
uniform mat4 view;
uniform vec2 position;

in vec2 vert;
in vec2 texCoord;
out vec2 uv;

void main() {
    uv = texCoord;

    gl_Position = proj * view * vec4(vec2(vert + position).x, vec2(vert + position).y, 0.0, 1.0);
}