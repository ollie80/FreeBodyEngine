class GlobalFlags:
    def __init__(self, starter_flags = {}):
        self._flags = {} | starter_flags
        self._locked = False

    def set(cls, key, value):
        if cls._locked:
            raise RuntimeError("Flags are locked.")
        cls._flags[key] = value

    def get(cls, key, default=None):
        return cls._flags.get(key, default)

    def lock(cls):
        cls._locked = True