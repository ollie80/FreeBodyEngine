#version 330 core

uniform int chunk_size;
uniform vec2[256] img_positions;
uniform sampler2D spritesheet;
uniform sampler2D normal;
uniform vec2 spritesheet_size; 
uniform int tile_size;

in vec2 uv;
out vec4 frag_albedo;  // Diffuse color
out vec4 frag_normal;  // Normal data


vec2 get_tile_percentage() {
    float x = uv.x * chunk_size;
    float y = uv.y * chunk_size;
    return vec2(x - floor(x), y - floor(y));
}


int get_tile_index() {
    int x = int(floor(uv.x * chunk_size));
    int y = int(floor(uv.y * chunk_size));
    return x + y;
}

void main() {
    vec2 tile_percentage = get_tile_percentage();
    int tile_index = get_tile_index(); 
    vec2 img_pos = img_positions[tile_index];
   
    vec2 sample_pos = vec2(((abs(img_pos.x) * tile_size) + (tile_size * tile_percentage.x)) / spritesheet_size.x, ((abs(img_pos.y) * tile_size) + (tile_size * tile_percentage.y)) / spritesheet_size.y);
    vec4 albedo = texture(spritesheet, sample_pos);
    
    float a = albedo.a;
    if (img_pos.x < 0.0) {
        a = 0.0;
    }
    frag_albedo = vec4(albedo.rgb, a);
    frag_normal = vec4(texture(normal, sample_pos).rgb, a);
}