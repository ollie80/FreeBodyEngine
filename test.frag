#version 330 core

in vec2 uv;

out float metallic;

out float roughness;

out vec4 emmision;

out vec4 normal;

out vec4 albedo;

uniform vec4 Albedo_Color;

uniform sampler2D Albedo_Texture;

uniform bool Albedo_useTexture;

uniform vec4 Normal_Color;

uniform sampler2D Normal_Texture;

uniform bool Normal_useTexture;

uniform vec4 Emmision_Color;

uniform sampler2D Emmision_Texture;

uniform bool Emmision_useTexture;

uniform float Roughness_Color;

uniform sampler2D Roughness_Texture;

uniform bool Roughness_useTexture;

uniform float Metallic_Color;

uniform sampler2D Metallic_Texture;

uniform bool Metallic_useTexture;

in vec3 normals;

void main() {
    albedo = Albedo_useTexture ? texture(Albedo_Texture, uv).rgba : Albedo_Color;
    albedo = Albedo_useTexture ? texture(Albedo_Texture, uv).rgba : Albedo_Color;
    normal = Normal_useTexture ? texture(Normal_Texture, uv).rgba : Normal_Color;
    emmision = Emmision_useTexture ? texture(Emmision_Texture, uv).rgba : Emmision_Color;
    roughness = Roughness_useTexture ? texture(Roughness_Texture, uv).r : Roughness_Color;
    metallic = Metallic_useTexture ? texture(Metallic_Texture, uv).r : Metallic_Color;
};