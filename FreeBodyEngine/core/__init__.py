

from FreeBodyEngine.core import files
from FreeBodyEngine.core import state
from FreeBodyEngine.core import window
from FreeBodyEngine.core import node
from FreeBodyEngine.core import timer
from FreeBodyEngine.core import logger
from FreeBodyEngine.core import scene
from FreeBodyEngine.core import camera
from FreeBodyEngine.core import particle
from FreeBodyEngine.core import main
from FreeBodyEngine.core import time
from FreeBodyEngine.core import input
from FreeBodyEngine.core import collider
from FreeBodyEngine.core.collider import Collider2D, CollisionShape, CircleCollisionShape, RectangleCollisionShape
from FreeBodyEngine.core import physics
from FreeBodyEngine.core import dev
from FreeBodyEngine.core import event
from FreeBodyEngine.core import profiler
from FreeBodyEngine.core import perf_profiler
from FreeBodyEngine.core import profiler_server

__all__ = ["files", "state", "main", "event", "dev", "camera", 'window', "tilemap", "time", "collider", "Collider2D", "CircleCollisionShape", "RectangleCollisionShape", "CollisionShape", "scene", "input", "timer", "node", "physics", "logger", "profiler", "perf_profiler", "profiler_server"]


# tilemap is resolved on first access rather than imported here.
#
# Its module-level @fbnjit decorators compile through numba, which costs
# ~300ms and drags scipy in behind it, and `import FreeBodyEngine` was
# paying that unconditionally - a project with no tilemap in it never
# touches any of it. Everything else in this package is cheap and stays
# eager; this is the one that was worth the indirection.
#
# `from FreeBodyEngine.core import tilemap` still works either way: that
# is a submodule import, not an attribute lookup. This covers the
# attribute form (fb.core.tilemap), and caches the result in globals()
# so it is a plain lookup from the second access on.
def __getattr__(name):
    if name == "tilemap":
        # import_module, not `from . import tilemap`: the from-form asks
        # the package for the attribute, which lands straight back in
        # here and recurses until the stack runs out.
        import importlib
        module = importlib.import_module("FreeBodyEngine.core.tilemap")
        globals()["tilemap"] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
