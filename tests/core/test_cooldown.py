"""Tests for the @cooldown and @physics_cooldown decorators.

Cooldowns were keyed by object alone, so two decorated methods on one object
blocked each other, and entries were never forgotten. @physics_cooldown
skipped its first call and, once its countdown first ran out, never restarted
it - running the method on every physics step from then on.
"""
import pytest

import FreeBodyEngine.core.time as time_module
from FreeBodyEngine.core.time import CooldownManager, cooldown, physics_cooldown


@pytest.fixture
def manager(monkeypatch):
    manager = CooldownManager()
    monkeypatch.setattr(time_module, 'service_exists', lambda name: name == 'cooldown_manager')
    monkeypatch.setattr(time_module, 'get_service', lambda name: manager)
    monkeypatch.setattr(time_module, 'delta', lambda: 0.1)
    monkeypatch.setattr(time_module, 'physics_delta', lambda: 0.1)
    return manager


class Gun:
    def __init__(self):
        self.calls = []

    @cooldown(0.5)
    def fire(self):
        self.calls.append('fire')

    @cooldown(0.5)
    def reload(self):
        self.calls.append('reload')

    @physics_cooldown(0.25)
    def tick(self):
        self.calls.append('tick')


def test_methods_on_one_object_have_separate_cooldowns(manager):
    gun = Gun()
    gun.fire()
    gun.reload()
    assert gun.calls == ['fire', 'reload']


def test_cooldown_blocks_then_allows_again(manager):
    gun = Gun()
    gun.fire()
    gun.fire()
    for _ in range(5):
        manager.update()
    gun.fire()
    assert gun.calls == ['fire', 'fire']


def test_expired_cooldowns_are_forgotten(manager):
    gun = Gun()
    gun.fire()
    for _ in range(5):
        manager.update()
    assert manager.cooldowns == {}


def test_physics_cooldown_runs_first_then_once_per_period(manager):
    gun = Gun()
    for _ in range(9):          # 0.9s of physics steps at 0.1s each
        gun.tick()
        manager.physics_update()
    # Runs at 0.0, 0.3, 0.6 - not skipped first, not every step once expired.
    assert gun.calls == ['tick'] * 3
