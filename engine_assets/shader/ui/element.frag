#version 330 core

in vec2 uv;
out vec4 f_color;

uniform vec2 resolution;               // Screen size in pixels

uniform vec4 borderRadius;             // Border radius per corner (pixels): TL, TR, BR, BL
uniform float borderWidth;             // Border width in pixels
uniform vec3 borderColor;  // Border color

uniform vec3 color = vec3(1.0);        // Fill color
uniform float opacity;


float roundedBox(vec2 px, vec2 size, vec4 radius) {
    // Check each corner and return 0.0 if outside the rounded area
    vec2 fromTL = px;
    vec2 fromTR = vec2(size.x - px.x, px.y);
    vec2 fromBR = size - px;
    vec2 fromBL = vec2(px.x, size.y - px.y);

    // Top-left
    if (px.x < radius.x && px.y < radius.x) {
        return length(fromTL - vec2(radius.x)) < radius.x ? 1.0 : 0.0;
    }

    // Top-right
    if (px.x > size.x - radius.y && px.y < radius.y) {
        return length(fromTR - vec2(radius.y)) < radius.y ? 1.0 : 0.0;
    }

    // Bottom-right
    if (px.x > size.x - radius.z && px.y > size.y - radius.z) {
        return length(fromBR - vec2(radius.z)) < radius.z ? 1.0 : 0.0;
    }

    // Bottom-left
    if (px.x < radius.w && px.y > size.y - radius.w) {
        return length(fromBL - vec2(radius.w)) < radius.w ? 1.0 : 0.0;
    }

    return 1.0;
}

void main() {
    vec2 fragPx = uv * resolution;
    vec2 size = resolution;

    float outerAlpha = roundedBox(fragPx, size, borderRadius);
    if (outerAlpha == 0.0) {
        discard; // outside outer rounded box
    }

    // Shrink size and frag position for inner (fill) area
    vec2 innerFrag = fragPx - vec2(borderWidth);
    vec2 innerSize = size - vec2(borderWidth * 2.0);
    vec4 innerRadius = max(borderRadius - vec4(borderWidth), vec4(0.0));

    float innerAlpha = roundedBox(innerFrag, innerSize, innerRadius);

    vec3 finalColor = mix(borderColor, color, innerAlpha);
    f_color = vec4(finalColor, opacity);
}
