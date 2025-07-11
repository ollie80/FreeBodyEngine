from FreeBodyEngine import get_main, warning

def abstractmethod(func):
    def wrapper(*args, **kwargs):
        cls_name = args[0].__class__.__name__
        raise NotImplementedError(f"Method '{func.__name__}' is not implemented on '{cls_name}'.")
    return wrapper

def load_sprite(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_sprite(path)
    else:
        warning("Cannot load a sprite while in headless mode as it requires a renderer.")

def load_image(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_image(path)
    else:
        warning("Cannot load an image while in headless mode as it requires a renderer.")

def load_material(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_material(path)
    else:
        warning("Cannot load a material while in headless mode as it requires a renderer.")


def load_sound(path: str):
    return get_main().files.load_sound(path)


def load_shader(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_shader(path)
    else:
        warning("Cannot load a shader while in headless mode as it requires a renderer.")

def load_sprite(path: str):
    if not get_main().headless_mode:
        return get_main().files.load_sprite(path)
    else:
        warning("Cannot load a shader while in healess mode as it requires a renderer.")
