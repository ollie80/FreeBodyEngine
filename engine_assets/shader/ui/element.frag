#version 330 core

in vec2 uv;
out vec4 f_color;

uniform vec2 resolution; 


uniform vec4 borderRadius;
uniform float borderWidth;
uniform float borderColor;

vec2 getAspect() {
    if (resolution.y > resolution.x) {
        return vec2(resolution.x / resolution.y, 1.0);
    } 
    return vec2(1.0, resolution.y / resolution.x);
}

float applyBorderRadius(vec4 radius, vec2 uvs) {
    vec2 aspect = getAspect();
    vec2 cornerDist;
    float r = 0.0;
    bool inCorner = false;

   // Bottom-left
    if (uvs.x < radius.w && uvs.y < radius.w * aspect.y) {
        cornerDist = uvs;
        r = radius.w;
        inCorner = true;

    // Bottom-right
    } else if (uvs.x > 1.0 - radius.z && uvs.y < radius.z * aspect.y) {
        cornerDist = vec2(1.0 - uvs.x, uvs.y);
        r = radius.z;
        inCorner = true;

    // Top-left
    } else if (uvs.x < radius.x && uvs.y > 1.0 - radius.x * aspect.y) {
        cornerDist = vec2(uvs.x, 1.0 - uvs.y);
        r = radius.x;
        inCorner = true;

    // Top-right
    } else if (uvs.x > 1.0 - radius.y && uvs.y > 1.0 - radius.y * aspect.y) {
        cornerDist = 1.0 - uvs;
        r = radius.y;
        inCorner = true;
    }
    if (inCorner) {
        vec2 center = vec2(r);
        vec2 offset = (cornerDist - center) / aspect;
        float dist = length(offset);
        if (dist > r) {
            return 0.0;
        }
    }


    return 1.0; // Inside or not in a corner
}

void main() {
    float alpha = 1.0;

    alpha = applyBorderRadius(borderRadius, uv);
    
    // Distance from rounded corner's arc center
    vec3 texColor = vec3(uv, 1.0);
    f_color = vec4(texColor.rgb, alpha);
}