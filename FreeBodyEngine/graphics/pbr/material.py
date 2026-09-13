from FreeBodyEngine.graphics.material import Material, PropertyType

class PBRMaterial(Material):
    """A Material with the engine's built-in PBR property set."""
    def __init__(self, data, injector=None):
        """Declares the standard PBR property_definitions (albedo/normal/
        emmisive/roughness/metallic) and defers everything else to
        Material.__init__."""
        property_definitions = {
            'albedo': PropertyType.COLOR_RGBA,
            'normal': PropertyType.COLOR_RG,
            'emmisive': PropertyType.COLOR_RGBA,
            'roughness': PropertyType.COLOR_R,
            'metallic': PropertyType.COLOR_R
        }
        super().__init__(data, property_definitions, injector)
        
