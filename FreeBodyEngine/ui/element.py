
class GenericElement:
    def __init__(self):
        pass

    def update(self):
        pass

    



class UIElement(GenericElement):
    def __init__(self):
        self.state = "normal"
        self.styles: dict[str, any] = {}
        self.parent: GenericElement