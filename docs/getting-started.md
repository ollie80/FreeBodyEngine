# Getting Started

## Install

FreeBodyEngine isn't on PyPI yet - install straight from GitHub:

```
pip install git+https://github.com/ollie80/FreeBodyEngine.git
```

This also installs the `freebody`/`fb` CLI (both names run the same tool).

## Create a project

```
freebody create project my_game
cd my_game
```

This scaffolds a project directory with an `fbproject.toml` (project
settings - name, entry point, asset/code paths), an `assets/` folder, and a
`code/` folder for your own Python modules.

## Run it

```
freebody run
```

`freebody run` (or `fb r`) launches your project against the local, unbuilt
source - the normal loop while developing. `freebody build` (`fb b`)
produces a packaged build for distribution; see the CLI's own `--help` on
either command for the flags each one takes.

## A minimal scene

A FreeBodyEngine project boots by registering the services it needs, adding
at least one [`Scene`][FreeBodyEngine.core.scene.Scene], and starting the
main loop:

```python
import FreeBodyEngine as fb
from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine.graphics.sprite import Sprite2D

class GameScene(Scene):
    def __init__(self):
        super().__init__("game")

    def on_initialize(self):
        sprite = Sprite2D(fb.core.files.load_file("player.fbspr"))
        self.add(sprite)

        camera = fb.core.camera.Camera2D()
        self.add(camera)
        self.camera = camera


def register_services():
    fb.register_service(fb.core.event.EventManager())
    fb.register_service(fb.core.files.get_file_system())
    fb.register_service(fb.core.logger.Logger())
    fb.register_service(fb.core.time.CooldownManager())
    fb.register_service(fb.core.scene.SceneManager())
    fb.register_service(fb.core.window.get_window()((900, 600), "my_game"))
    fb.register_service(fb.graphics.get_renderer()())
    fb.register_service(fb.graphics.pbr.pipeline.PBRPipeline())

    actions = fb.core.input.Input.parse_actions({})
    fb.register_service(fb.core.input.Input(actions))
    fb.register_service(fb.get_service("window").create_mouse())


if __name__ == "__main__":
    main = fb.init()
    register_services()
    fb.add_scene(GameScene())
    fb.set_scene("game")
    main.run()
```

Everything in the engine is reached through a small set of core services
(`files`, `renderer`, `graphics`, `window`, `scene_manager`, ...) fetched
with [`fb.get_service(name)`][FreeBodyEngine.get_service] - registering the
ones your project actually uses is the one piece of boilerplate every
project's entry point repeats.

From here, the [Guide](guide/scenes-and-nodes.md) covers the scene/node
system and the shader pipeline in more depth, and the
[API Reference](reference/index.md) is generated straight from the engine's
own docstrings.
