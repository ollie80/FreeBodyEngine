from FreeBodyEngine.graphics.material import Material, PropertyType


class LiteMaterial(Material):
    """A surface in a 2D scene: what colour it is, which way it faces, and
    whether any of it glows.

    Three properties against PBRMaterial's five. Roughness and metallic
    describe how a surface scatters light at a glancing angle, which is a
    question flat art never asks - and dropping them takes a specular term,
    two texture lookups and a Fresnel evaluation per light out of the shader
    with it.

    A `.fbmat` written for PBRPipeline still loads here; the two it no longer
    understands are simply not among this material's properties, so they are
    never parsed and never uploaded.
    """

    def __init__(self, data, injector=None):
        property_definitions = {
            'albedo': PropertyType.COLOR_RGBA,
            'normal': PropertyType.COLOR_RGBA,
            'emmisive': PropertyType.COLOR_RGBA,
        }

        # One shader pair for every blend mode, unlike PBRMaterial's deferred/
        # forward split. Nothing here is lit at the point it is drawn - the
        # surface pass only records what is there - so a transparent surface
        # needs no separate forward-lit path to be lit correctly.
        super().__init__(data, property_definitions, injector,
                         'engine://shader/lite/surface.fbvert',
                         'engine://shader/lite/surface.fbfrag')
