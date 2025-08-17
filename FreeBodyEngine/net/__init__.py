"""
A small, low level, networking library built on UDP. It provides features of TCP, such as ordering and reliability, while also having the ability to be fast.
"""

from FreeBodyEngine.net.interface import NetworkInterface, PacketType, LOCAL

__all__ = ["NetworkInterface", "PacketType", "LOCAL"]

