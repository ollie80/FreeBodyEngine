"""
FreeBody Engine created by ollie80
"""

from FreeBodyEngine import core
from FreeBodyEngine import math
# from FreeBodyEngine import net
# from FreeBodyEngine import ui
from FreeBodyEngine import graphics
from FreeBodyEngine import utils


_main_object: core.main.Main = None

def get_main():
    if _main_object == None:
        raise RuntimeError("No main object has been created.")
    return _main_object

__all__ = [ "graphics", "utils", "core", "math", "get_main"]



