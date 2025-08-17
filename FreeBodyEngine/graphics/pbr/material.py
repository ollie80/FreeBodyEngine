from FreeBodyEngine.graphics.material import Material, PropertyType

class PBRMaterial(Material):
    def __init__(self, data, injector=None):
        property_definitions = {
            'albedo': PropertyType.COLOR_RGBA,
            'normal': PropertyType.COLOR_RG,
            'emmisive': PropertyType.COLOR_RGBA,
            'roughness': PropertyType.COLOR_R,
            'metallic': PropertyType.COLOR_R
        }
        super().__init__(data, property_definitions, injector)

