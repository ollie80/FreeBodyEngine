#version 330 core
out vec4 color;
uniform vec4 line_color;

void main() {
    color = line_color;
}