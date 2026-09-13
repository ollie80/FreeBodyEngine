class GlobalFlags:
    """A simple lockable key-value store for global engine flags (see
    `FreeBodyEngine.get_flag`/`set_flag`) - once `lock()`ed, `set()` refuses
    any further changes."""

    def __init__(self, starter_flags = {}):
        """Seeds the flag store with `starter_flags` - `Main.__init__` uses
        this to carry over any flags set via `fb.set_flag()` before the
        engine was initialized."""
        self._flags = {} | starter_flags
        self._locked = False

    def set(cls, key, value):
        """Sets flag `key` to `value`.

        Raises:
            RuntimeError: if the flags have been locked (see `lock()`)."""
        if cls._locked:
            raise RuntimeError("Flags are locked.")
        cls._flags[key] = value

    def get(cls, key, default=None):
        """Returns the value of flag `key`, or `default` if it isn't set."""
        return cls._flags.get(key, default)

    def lock(cls):
        """Locks the flag store, causing any further `set()` call to raise."""
        cls._locked = True