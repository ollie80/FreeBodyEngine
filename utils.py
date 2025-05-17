def abstractmethod(func):
    def wrapper(*args, **kwargs):
        cls_name = args[0].__class__.__name__
        raise NotImplementedError(f"Method '{func.__name__}' is not implemented on '{cls_name}'.")
    return wrapper