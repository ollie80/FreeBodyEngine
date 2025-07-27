class GlobalFlags:
    _flags = {}
    _locked = False

    @classmethod
    def set(cls, key, value):
        if cls._locked:
            raise RuntimeError("Flags are locked.")
        cls._flags[key] = value

    @classmethod
    def get(cls, key, default=None):
        return cls._flags.get(key, default)

    @classmethod
    def lock(cls):
        cls._locked = True