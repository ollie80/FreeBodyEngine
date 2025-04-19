#version 330 core

uniform sampler2D tex;

in vec2 uv;
out vec4 f_color;

void main() {
    f_color = vec4(texture(tex, uv).rgba);
}