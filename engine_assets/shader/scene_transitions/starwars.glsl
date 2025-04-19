#version 330 core

const float PI = 3.14159265359;

in vec2 uv;
out vec4 f_color;

uniform float time; 

float angleBetween(vec2 from, vec2 to) {
    vec2 delta = to - from;
    return atan(delta.y, delta.x);
}

void main() {
    float alpha = 1.0;
    float angle = time * (2*PI); 
    float between = angleBetween();

    if (between < angle) {
        alpha = 0.0;
    }
    f_color = vec4(1.0, 1.0, 1.0, alpha);
}