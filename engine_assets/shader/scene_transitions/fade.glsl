#version 330 core


out vec4 f_color;

uniform float time; 

void main() {

    f_color = vec4(0.0, 0.0, 0.0, time);
}