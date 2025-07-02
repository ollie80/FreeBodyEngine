#version 330 core

in vec2 vert;
in vec2 texCoord;

void main() {
    
    gl_Position = vec4(vert, texCoord.x, 1.0);
}