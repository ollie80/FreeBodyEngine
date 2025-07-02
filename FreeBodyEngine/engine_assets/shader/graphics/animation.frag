#version 330 core

in vec2 uv;
out vec4 frag_albedo;
out vec4 frag_normal;

uniform sampler2D albedo;
uniform sampler2D normal;

uniform vec2 spritesheet_size;
uniform vec2 img_size;
uniform vec2 img_pos;

void main() {
    spritesheet_size;
    vec2 tile_pos = vec2(img_size * img_pos)/ spritesheet_size;
    vec2 tile_percentage = vec2(img_size/ spritesheet_size * uv);
    vec2 sample_pos = vec2(tile_pos + tile_percentage);
    frag_albedo = vec4(texture(albedo, sample_pos).rgba); 
    frag_normal = vec4(texture(normal, sample_pos).rgba); 
}