#version 330 core

const float PI = 3.14159265359;

in vec2 uv;
out vec4 f_color;

uniform bool inverse;
uniform float time; // assumed to be in range [0.0, 1.0]

float angleBetween(vec2 from, vec2 to) {
    vec2 delta = to - from;
    float angle = atan(delta.y, delta.x);
    return mod(angle + 2.0 * PI, 2.0 * PI);
}

void main() {
    float alpha = 1.0;

    float t = clamp(time, 0.0, 1.0);
    float angle = (1.0 - t) * 2.0 * PI;

    float between = angleBetween(uv, vec2(0.5, 0.5));
    float margin = 0.05 * 2.0 * PI;

    float edge0 = angle - margin;
    float edge1 = angle;
    if (between < angle) {
        alpha = smoothstep(edge0, edge1, between);
    }

    f_color = vec4(0.0, 0.0, 0.0, alpha);
}
