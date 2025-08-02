#version 330 core

uniform mat4 view;

uniform mat4 proj;

uniform mat4 model;

layout(location = 0) in vec3 vertex;

layout(location = 1) in vec2 uvs;

layout(location = 2) in vec3 normals;

layout(location = 0) out vec2 uv;

layout(location = 1) out vec3 normal;

void main() {
    uv = uvs;
    normal = normals;
    gl_Position = proj*view*model*vec4(vertex.x, vertex.y, vertex.z, 1.0);
};