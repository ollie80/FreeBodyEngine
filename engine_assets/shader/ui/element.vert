#version 330 core

in vec2 texCoord;
in vec2 vert;
out vec2 uv;

uniform vec3 rot;

void main() {
    uv = texCoord;

    // Rotation matrices
    float cx = cos(rot.x);
    float sx = sin(rot.x);
    float cy = cos(rot.y);
    float sy = sin(rot.y);
    float cz = cos(rot.z);
    float sz = sin(rot.z);

    // Rotation around X-axis
    mat3 rotX = mat3(
        1.0, 0.0,  0.0,
        0.0,  cx, -sx,
        0.0,  sx,  cx
    );

    // Rotation around Y-axis
    mat3 rotY = mat3(
         cy, 0.0, sy,
         0.0, 1.0, 0.0,
        -sy, 0.0, cy
    );

    // Rotation around Z-axis
    mat3 rotZ = mat3(
        cz, -sz, 0.0,
        sz,  cz, 0.0,
        0.0, 0.0, 1.0
    );

    // Combine rotations: Z * Y * X (standard order)
    mat3 rotation = rotZ * rotY * rotX;

    vec3 rotatedVert = rotation * vec3(vert, 0.0);

    gl_Position = vec4(rotatedVert, 1.0);
}
