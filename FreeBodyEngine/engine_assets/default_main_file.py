import FreeBodyEngine as fb
import sys

"""This is the default main file for a FreeBodyEngine project. It has only the basic features to take in important args and run an example game. THIS IS MEANT TO BE CHANGED!"""

def register_default_services():
    """Registers the baseline services (event bus, file manager, logger, cooldown manager, scene manager, window, renderer, PBR pipeline, input) a game needs before it can create scenes or nodes - call once during startup before adding the default scene below."""
    # registers services that provide basic engine functionality
    fb.register_service(fb.core.event.EventManager())
    fb.register_service(fb.core.files.get_file_system())
    fb.register_service(fb.core.logger.Logger())
    fb.register_service(fb.core.time.CooldownManager())
    fb.register_service(fb.core.scene.SceneManager())
    fb.register_service(fb.core.window.get_window()((800, 800), 'Game'))
    fb.register_service(fb.graphics.get_renderer()())
    fb.register_service(fb.graphics.pbr.pipeline.PBRPipeline())

    if fb.core.files.path_exists('actions.toml'):
        action_source = fb.core.files.load_file('actions.toml')
    else:
        action_source = {}

    actions = fb.core.input.Input.parse_actions(action_source)

    fb.register_service(fb.core.input.Input(actions))
    fb.register_service(fb.get_service('window').create_mouse())

if __name__ == "__main__":    
    #set flags
    for arg in sys.argv:
        if arg == ("--headless") or arg == "-H":
            fb.set_flag(fb.HEADLESS, True)
            fb.core.logger.print_colored("Headless mode set to true.", color="green")

        if arg == '--terminal':
            fb.set_flag(fb.TERMINAL_WINDOW, True)

        if arg == ("--dev"):
            fb.set_flag(fb.DEVMODE, True)

        if '--path' in arg:
            if "--path=" in arg:
                val = arg.removeprefix('--path=')
                if len(val) == 0:
                    raise ValueError('No path specified, please use: --path=<PATH>')
            else:
                raise ValueError('No path specified, please use: --path=<PATH>')

            fb.set_flag(fb.PROJECT_PATH, val)

    main = fb.init()

    register_default_services()    

    scene = fb.core.scene.Scene('game')
    fb.add_scene(scene)
    fb.set_scene('game')

    main.run()
