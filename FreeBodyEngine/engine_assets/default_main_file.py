import FreeBodyEngine as fb
import sys

class colors: # stolen from some nerd on stack overflow 
    HEADER = '\033[95m' 
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def register_default_services():
    # registers services that provide basic engine functionality
    fb.register_service(fb.core.files.FileManager())
    fb.register_service(fb.core.logger.Logger())
    fb.register_service(fb.core.time.CooldownManager())
    fb.register_service(fb.core.scene.SceneManager())
    fb.register_service(fb.core.window.get_window()((800, 800), 'Game'))
    fb.register_service(fb.graphics.get_renderer()())
    fb.register_service(fb.graphics.pbr.pipeline.PBRPipeline())

    action_source = fb.load_toml('actions.toml')
    actions = fb.core.input.Input.parse_actions(action_source)

    fb.register_service(fb.core.input.Input(actions))
    fb.register_service(fb.get_service('window').create_mouse())

if __name__ == "__main__":

    fb.init()
    main = fb.core.main.Main(max_fps=120)

    #set flags
    for arg in sys.argv:
        if arg == ("--headless") or arg == "-H": 
            fb.set_flag(fb.HEADLESS, True)
            fb.core.logger.print_colored("Headless mode set to true.", color="green")

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

    register_default_services()
    
    scene = fb.core.scene.Scene('game')
    fb.add_scene(scene)
    fb.set_scene('game')

    main.run()
