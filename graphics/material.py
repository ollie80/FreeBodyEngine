from abc import ABC, abstractmethod
from FreeBodyEngine.graphics.color import Color

class Material(ABC):
    def __init__(self, data: dict[str, any]):
        self.albedo = Color(data.get("albedo", "#FFFFFF"))
        self.normal = Color(data.get("normal", "#8080FF"))
        self.emmisive = Color(data.get("emmisive", "#000000"))
            