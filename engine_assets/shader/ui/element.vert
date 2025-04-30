#version 330 core

in vec2 texCoord;
in vec2 vert;
out vec2 uv;

uniform vec3 rot;
uniform vec2 resolution;

void main() {
    uv = texCoord;

    // Convert from pixel coords to NDC [-1, 1]
    vec2 ndc = (vert / resolution) * 2.0;
    ndc.y *= 1.0;

    // Rotation matrices
    float cx = cos(rot.x);
    float sx = sin(rot.x);
    float cy = cos(rot.y);
    float sy = sin(rot.y);
    float cz = cos(rot.z);
    float sz = sin(rot.z);

    mat3 rotX = mat3(
        1.0, 0.0,  0.0,
        0.0,  cx, -sx,
        0.0,  sx,  cx
    );

    mat3 rotY = mat3(
         cy, 0.0, sy,
         0.0, 1.0, 0.0,
        -sy, 0.0, cy
    );

    mat3 rotZ = mat3(
        cz, -sz, 0.0,
        sz,  cz, 0.0,
        0.0, 0.0, 1.0
    );

    mat3 rotation = rotZ * rotY * rotX;

    vec3 rotatedVert = rotation * vec3(ndc, 0.0);

    gl_Position = vec4(rotatedVert, 1.0);
}
