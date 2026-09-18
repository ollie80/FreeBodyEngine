from FreeBodyEngine.graphics.material import Material, PropertyType, BlendMode

class PBRMaterial(Material):
    """A Material with the engine's built-in PBR property set."""
    def __init__(self, data, injector=None):
        """Declares the standard PBR property_definitions (albedo/normal/
        emmisive/roughness/metallic) and defers everything else to
        Material.__init__ - picking the forward-lit shader pair as this
        pipeline's default for a non-opaque blend mode (an explicit
        `shader` block in the .fbmat still wins - see Material.__init__),
        since PBRPipeline's deferred G-buffer can only hold one opaque
        surface per pixel and can't represent a blended one at all."""
        property_definitions = {
            'albedo': PropertyType.COLOR_RGBA,
            'normal': PropertyType.COLOR_RG,
            'emmisive': PropertyType.COLOR_RGBA,
            'roughness': PropertyType.COLOR_R,
            'metallic': PropertyType.COLOR_R
        }
        blend_mode = {
            'opaque': BlendMode.OPAQUE,
            'transparent': BlendMode.TRANSPARENT,
            'additive': BlendMode.ADDITIVE,
        }.get(str(data.get('blend', 'opaque')).lower(), BlendMode.OPAQUE)

        if blend_mode == BlendMode.OPAQUE:
            default_vert = 'engine://shader/default_shader.fbvert'
            default_frag = 'engine://shader/default_shader.fbfrag'
        else:
            default_vert = 'engine://shader/default_forward.fbvert'
            default_frag = 'engine://shader/default_forward.fbfrag'

        super().__init__(data, property_definitions, injector, default_vert, default_frag)

