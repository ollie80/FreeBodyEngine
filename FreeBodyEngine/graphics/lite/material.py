from FreeBodyEngine import get_service
from FreeBodyEngine.graphics.material import Material, PropertyType

SURFACE_VERT = 'engine://shader/lite/surface.fbvert'
SURFACE_FRAG = 'engine://shader/lite/surface.fbfrag'
INSTANCED_VERT = 'engine://shader/lite/surface_instanced.fbvert'


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
        super().__init__(data, property_definitions, injector, SURFACE_VERT, SURFACE_FRAG)

    def instanced_shader(self):
        """surface.fbvert's instanced twin (surface_instanced.fbvert) with the
        same fragment stage and property injection - for the default surface
        shader only: a `.fbmat` naming its own shader has no twin to use.

        Built once and kept on the shader it shadows, which every instance()
        of this material shares, so it compiles once rather than once a
        sprite."""
        if self._vert_source_path != SURFACE_VERT or self._frag_source_path != SURFACE_FRAG \
                or self._geom_source_path is not None:
            return None
        shader = self.shader
        twin = shader.__dict__.get('_instanced_twin')
        if twin is None:
            files = get_service('files')
            twin = get_service('renderer').load_shader(files.get_file(INSTANCED_VERT), files.get_file(SURFACE_FRAG),
                                                       self._shader_injector)
            shader.__dict__['_instanced_twin'] = twin
        return twin
