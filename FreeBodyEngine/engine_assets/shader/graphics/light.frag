#version 330 core
#define MAX_LIGHTS 20

struct Light {
    vec2 position;
    vec3 color;
    float intensity;
    float radius;
};

struct SpotLight {
    vec2 position;
    vec2 direction;
    vec3 color;
    float angle;
    float intensity;
    float radius;
};

struct DirectionalLight {
    vec2 direction;
    vec3 color;
    float intensity;
};

uniform sampler2D albedo_texture;
uniform sampler2D normal_texture;

uniform vec2 screen_size;

uniform Light lights[MAX_LIGHTS];
uniform int light_count;

uniform SpotLight spotLights[MAX_LIGHTS];
uniform int spot_light_count;

uniform DirectionalLight dirLights[MAX_LIGHTS];
uniform int dir_light_count;

uniform vec3 global_light;

uniform mat4 view;
uniform mat4 proj;
uniform float zoom;

in vec2 uv;
out vec4 frag_color;

void main() {
    vec3 albedo = texture(albedo_texture, uv).rgb;
    vec3 normal = texture(normal_texture, uv).rgb;
    normal = normalize(normal * 2.0 - 1.0);


    // Process each light
    // Convert fragment position from screen space to NDC
    vec4 frag_pos_ndc = vec4((gl_FragCoord.xy / screen_size) * 2.0 - 1.0, 0.0, 1.0);

    // Transform from NDC to world space
    vec4 frag_pos_world = inverse(proj * view) * frag_pos_ndc;
    frag_pos_world /= frag_pos_world.w; // Perspective divide

    // Start with global ambient lighting
    vec3 lighting = global_light;

    // Process each light
    if (light_count > 0) {
        for (int i = 0; i < dir_light_count; i++) {
            vec3 light_vec = normalize(vec3(dirLights[i].direction, 1.0));
            float diff = max(dot(normal, light_vec), 0.0);

            lighting += dirLights[i].color * diff * dirLights[i].intensity;
        }

        for (int i = 0; i < spot_light_count; i++) {
            vec2 light_pos_world = spotLights[i].position;
            vec2 to_frag = normalize(frag_pos_world.xy - light_pos_world);
            vec2 spot_dir = normalize(spotLights[i].direction);

            // Calculate spotlight effect
            float angle_diff = dot(to_frag, spot_dir);
            float spot_effect = smoothstep(cos(spotLights[i].angle), cos(spotLights[i].angle * 0.9), angle_diff);

            // Compute attenuation
            float dist = length(light_pos_world - frag_pos_world.xy);
            if (dist > spotLights[i].radius) continue;
            float attenuation = 1.0 - (dist / spotLights[i].radius);
            attenuation = max(attenuation, 0.0);

            // Diffuse lighting
            vec3 light_vec = normalize(vec3(to_frag, 1.0));
            float diff = max(dot(normal, light_vec), 0.0);

            lighting += spotLights[i].color * diff * spotLights[i].intensity;
        }
        
        for (int i = 0; i < light_count; i++) {
            // Light position is already in world space
            vec2 light_pos_world = lights[i].position;

            // Compute world-space distance
            float dist = length(light_pos_world - frag_pos_world.xy);
            if (dist > lights[i].radius) continue;

            // Calculate lighting contribution
            vec2 light_dir = normalize(light_pos_world - frag_pos_world.xy);
            vec3 light_vec = normalize(vec3(light_dir, 1.0));
            float diff = max(dot(normal, light_vec), 0.0);
            float attenuation = 1.0 - (dist / lights[i].radius);
            attenuation = max(attenuation, 0.0);

            lighting += lights[i].color * diff * lights[i].intensity * attenuation;
        }
    }

    frag_color = vec4(albedo * lighting, 1.0);
}