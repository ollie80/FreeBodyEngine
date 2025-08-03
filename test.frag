#version 330 core

uniform bool Metallic_useTexture;

uniform vec4 Metallic_UVRect;

uniform vec4 Metallic_Color;

uniform sampler2D Metallic_Texture;

uniform bool Roughness_useTexture;

uniform vec4 Roughness_UVRect;

uniform vec4 Roughness_Color;

uniform sampler2D Roughness_Texture;

uniform bool Emmisive_useTexture;

uniform vec4 Emmisive_UVRect;

uniform vec4 Emmisive_Color;

uniform sampler2D Emmisive_Texture;

uniform bool Normal_useTexture;

uniform vec4 Normal_UVRect;

uniform vec4 Normal_Color;

uniform sampler2D Normal_Texture;

uniform bool Albedo_useTexture;

uniform vec4 Albedo_UVRect;

uniform vec4 Albedo_Color;

uniform sampler2D Albedo_Texture;

layout(location = 0) out vec4 albedo;

layout(location = 1) out vec4 normal;

layout(location = 2) out vec4 emmisive;

layout(location = 3) out vec4 roughness;

layout(location = 4) out vec4 metallic;

layout(std140) uniform testBuffer {
  vec4 vector;
};

layout(location = 0) in vec2 uv;

layout(location = 1) in vec3 normals;

void main() {
    albedo = Albedo_useTexture ? texture(Albedo_Texture, Albedo_UVRect.zw*1.0-uv+vec2(Albedo_UVRect.x, 1.0-Albedo_UVRect.y-Albedo_UVRect.w)) : Albedo_Color;
    normal = Normal_useTexture ? texture(Normal_Texture, Normal_UVRect.zw*uv+vec2(Normal_UVRect.x, 1.0-Normal_UVRect.y-Normal_UVRect.w)) : Normal_Color;
    emmisive = Emmisive_useTexture ? texture(Emmisive_Texture, Emmisive_UVRect.zw*uv+vec2(Emmisive_UVRect.x, 1.0-Emmisive_UVRect.y-Emmisive_UVRect.w)) : Emmisive_Color;
    roughness = Roughness_useTexture ? texture(Roughness_Texture, Roughness_UVRect.zw*uv+vec2(Roughness_UVRect.x, 1.0-Roughness_UVRect.y-Roughness_UVRect.w)) : Roughness_Color;
    metallic = Metallic_useTexture ? texture(Metallic_Texture, Metallic_UVRect.zw*uv+vec2(Metallic_UVRect.x, 1.0-Metallic_UVRect.y-Metallic_UVRect.w)) : Metallic_Color;
};