"""`freebody profile` / `fb profile` - opens the external performance
profiler, a real (if minimal) FreeBodyEngine app in its own window, built
with the engine's own UI, that connects to a currently-running app's
FreeBodyEngine.core.profiler_server.ProfilerServer and renders its live
CPU/GPU/memory/draw-call data - see cli/profiler/app.py for the actual
UI, client.py for the connection, logs.py for the on-disk log it writes
the whole time it runs.

The target app has to have registered a ProfilerServer itself
(`fb.register_service(fb.core.profiler_server.ProfilerServer())`) for
there to be anything to connect to - this tool doesn't inject anything
into another process, it just speaks the plain TCP/JSON protocol that
service exposes on 127.0.0.1."""
import os
import sys

import FreeBodyEngine as fb

# The profiler is pure engine tooling, not a real FreeBodyEngine project -
# but get_file_system() only returns a DevFileSystem (needed to resolve
# every engine://... asset this app's own UI loads: fonts, ui/element.fbmat,
# text/text.fbmat, the renderer's line shader, ...) when the DEVMODE flag
# is set, and DEVMODE requires a real fbproject.toml to load (see
# core.dev.find_project()/load_project()) even though this app never
# touches project-specific assets. _project/ is a minimal shipped project
# (empty assets/code dirs) that exists solely to satisfy that requirement.
_DUMMY_PROJECT_PATH = os.path.join(os.path.dirname(__file__), "_project")


def profile_handler(env, args):
    """CLI entry point. `args` may include `--host=<host>` / `--port=<n>`
    to point at something other than the default 127.0.0.1:47821 (e.g.
    profiling a real Android device reachable over `adb forward`), and
    `--test-window` (undocumented - for this engine's own test harnesses,
    not a real user-facing flag) to run headless against a TestWindow
    instead of opening a real one."""
    from FreeBodyEngine.core.profiler_server import DEFAULT_PORT

    host = "127.0.0.1"
    port = DEFAULT_PORT
    for a in args:
        if a.startswith("--host="):
            host = a.removeprefix("--host=")
        elif a.startswith("--port="):
            port = int(a.removeprefix("--port="))

    run_profiler_app(host, port, test_window="--test-window" in args)


def run_profiler_app(host: str = "127.0.0.1", port: int = None, test_window: bool = False, size=(980, 760)):
    """Boots a standalone FreeBodyEngine app (its own window/renderer/UI,
    no project directory involved at all - this lives entirely inside
    the engine's own CLI tooling) whose one scene is cli.profiler.app.
    ProfilerApp. Blocks (main.run()) until the window is closed, same as
    any other FreeBodyEngine app's own main.py."""
    from FreeBodyEngine.core.profiler_server import DEFAULT_PORT
    from FreeBodyEngine.cli.profiler.client import ProfilerClient
    from FreeBodyEngine.cli.profiler.app import ProfilerApp

    if port is None:
        port = DEFAULT_PORT

    fb.set_flag(fb.DEVMODE, True)
    fb.set_flag(fb.PROJECT_PATH, _DUMMY_PROJECT_PATH)
    fb.set_flag(fb.NAME, "freebody-profiler")
    if test_window:
        fb.set_flag(fb.TEST_WINDOW, True)

    main = fb.init()

    fb.register_service(fb.core.event.EventManager())
    fb.register_service(fb.core.files.get_file_system())
    fb.register_service(fb.core.logger.Logger())
    fb.register_service(fb.core.time.CooldownManager())
    fb.register_service(fb.core.scene.SceneManager())
    fb.register_service(fb.core.window.get_window()(size, "FreeBodyEngine Profiler"))

    actions = fb.core.input.Input.parse_actions({})
    fb.register_service(fb.core.input.Input(actions))

    fb.register_service(fb.ui.UIManager(styles={"base_color": (0.03, 0.05, 0.04, 1.0), "layout": "vertical"}))
    fb.register_service(fb.graphics.get_renderer()())
    # This app is pure UI (no 3D content of its own) - PBRPipeline is only
    # here because UIRenderer's material (engine://ui/element.fbmat) is
    # loaded through the 'graphics' service's create_material(), same as
    # every other GraphicsPipeline subclass (see phonon's own main.py,
    # which uses its VisualizerPipeline for the exact same reason). Any
    # concrete GraphicsPipeline would do; PBRPipeline is the engine's own
    # generic default, so nothing project-specific is needed here.
    from FreeBodyEngine.graphics.pbr.pipeline import PBRPipeline
    fb.register_service(PBRPipeline())
    fb.register_service(fb.get_service("window").create_mouse())
    fb.register_service(fb.ui.get_ui_renderer()())
    fb.register_service(fb.graphics.text.TextRenderer())

    fb.register_service(ProfilerClient(host=host, port=port))

    fb.add_scene(ProfilerApp())
    fb.set_scene("profiler")

    try:
        main.run()
    except KeyboardInterrupt:
        pass
