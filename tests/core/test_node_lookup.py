"""Tests for finding nodes and for the node/scene lifecycle hooks.

Nodes had no names and the only search was find_nodes_with_type() with a
class name string, walking the whole tree. kill() gave a node's children
nothing, and remove()/Scene.remove() skipped on_kill() even for the node
itself. set_scene() switched to any name, added or not, and told no one.
"""
import FreeBodyEngine as fb
from FreeBodyEngine.core.scene import SceneManager


class Enemy(fb.Node2D):
    pass


class Boss(Enemy):
    pass


class Logged(fb.Node2D):
    def __init__(self, log, label):
        super().__init__()
        self.log, self.label = log, label

    def on_kill(self):
        self.log.append(self.label)


def _scene():
    scene = fb.Scene('test')
    player = fb.Node2D()
    player.name = 'Player'
    weapon = fb.Node2D()
    weapon.name = 'Weapon'
    muzzle = fb.Node2D()
    muzzle.name = 'Muzzle'
    weapon.add(muzzle)
    player.add(weapon)
    scene.add(player, Enemy(), Boss())
    return scene, player, weapon, muzzle


def test_get_node_by_path():
    scene, player, weapon, muzzle = _scene()
    assert scene.get_node('Player/Weapon/Muzzle') is muzzle
    assert player.get_node('Weapon') is weapon
    assert muzzle.get_node('../..') is player
    assert scene.get_node('Player/Nope') is None


def test_names_default_to_the_class_name():
    scene, *_ = _scene()
    assert isinstance(scene.get_node('Enemy'), Enemy)


def test_find_by_class_includes_subclasses():
    scene, player, *_ = _scene()
    assert len(scene.find_all(Enemy)) == 2
    assert isinstance(scene.find(Boss), Boss)
    assert scene.find_all('Boss') == scene.find_all(Boss)
    assert player.find_all(Enemy) == []


def test_the_scene_index_follows_nodes_in_and_out():
    scene, player, weapon, muzzle = _scene()
    late = fb.Node2D()
    muzzle.add(late)                       # added under a subtree already in the scene
    assert late in scene.find_all(fb.Node2D)
    weapon.kill()
    assert weapon not in scene.find_all(fb.Node2D)
    assert late not in scene.find_all(fb.Node2D)
    assert scene.root.find_nodes_with_type('Node2D') == scene.find_all('Node2D')


def test_kill_tells_children_first_then_the_node():
    log = []
    scene = fb.Scene('test')
    parent, child, grandchild = Logged(log, 'parent'), Logged(log, 'child'), Logged(log, 'grandchild')
    child.add(grandchild)
    parent.add(child)
    scene.add(parent)
    parent.kill()
    parent.kill()                          # a second kill is a no-op
    assert log == ['grandchild', 'child', 'parent']


def test_remove_calls_on_kill():
    log = []
    scene = fb.Scene('test')
    node = Logged(log, 'node')
    scene.add(node)
    scene.remove(node.id)
    assert log == ['node']


def test_a_sibling_removed_mid_update_is_not_updated():
    updated = []
    scene = fb.Scene('test')

    class Victim(fb.Node2D):
        def on_update(self):
            updated.append(self)

    victim = Victim()

    class Killer(fb.Node2D):
        def on_update(self):
            victim.kill()

    scene.add(Killer(), victim)
    scene.root.update()
    assert updated == []


class Level(fb.Scene):
    def __init__(self, name, log):
        super().__init__(name)
        self.log = log

    def on_enter(self):
        self.log.append(f'enter {self.name}')

    def on_exit(self):
        self.log.append(f'exit {self.name}')


def test_scene_enter_and_exit():
    log = []
    manager = SceneManager()
    manager.add_scene(Level('a', log))
    manager.add_scene(Level('b', log))
    manager.set_scene('a')
    manager.set_scene('a')                 # already active: nothing
    manager.set_scene('b')
    manager.remove_scene('b')
    assert log == ['enter a', 'exit a', 'enter b', 'exit b']


def test_set_scene_with_an_unknown_name_changes_nothing(capsys):
    manager = SceneManager()
    manager.add_scene(fb.Scene('a'))
    manager.set_scene('a')
    manager.set_scene('typo')
    assert manager.active_scene == 'a'
    assert 'no scene by that name' in capsys.readouterr().out
