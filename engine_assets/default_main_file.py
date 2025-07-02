from FreeBodyEngine import * 

import sys
import os

"""This is the default main file for a FreeBodyEngine project. It has only the basic features to take in important args and run an example game."""


class colors:
    HEADER = '\033[95m' 
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


if __name__ == "__main__":
    screen_size = (800, 800)
    fps = 60
    path = './'
    headless = False
    display = 0
    dev_mode = False
    production = False

    for arg in sys.argv:
        if arg.startswith("--fps"):
            value = arg.removeprefix("--fps=")
            if len(arg) == 0:
                core.logger.print_colored("FPS Cap was not set because no value was provided.", color="green")
                continue

            if not value.isnumeric():
                core.logger.print_colored("FPS Cap was not set because the provided value was not an integer.", color="green")
                continue

            fps = int(value)
            core.logger.print_colored(f"FPS Cap was set to {fps}.", color="green")

        if arg.startswith("--display"):
            display = int(arg.removeprefix("--display="))

        if arg.startswith("--size"):
            string = arg.removeprefix("--size=")
            if arg.find(":") == -1:
                core.logger.print_colored("Screen Size not set because of invalid syntax, please use:" + " --size=x:y", color="green")
                continue

            i = string.index(":")
            x = string[0:i]
            if not x.isnumeric():
                core.logger.print_colored("Screen Size not set because the x value was invalid.", color="green")
                continue

            if len(string) == i+1:
                core.logger.print_colored("Screen Size not set because only one value was provided.", color="green")
                continue

            y = string[i+1:len(string)]
            if not y.isnumeric():
                core.logger.print_colored("Screen Size not set because the y value was invalid.", color="green")
                continue

            screen_size = (int(x), int(y))
            core.logger.print_colored(f"Screen Size set to {screen_size}.", color="green")

        if arg == "--fullscreen":
            screen_size = (0,0)


        if arg == ("--headless") or arg == "-H": 
            headless = True
            core.logger.print_colored("Headless mode set to true.", color="green")

        if arg == ("--dev"):
            dev_mode = True
            asset_dir = "./dev/assets/"

        if "--path=" in arg:
            path = arg.removeprefix('--path=')

        if arg == "--production":
            production = True

    init()

    main = core.main.Main(path=path, dev=dev_mode, headless=headless, window_size=screen_size, fps=fps)
    game = core.scene.Scene("game")
    main.add(game)

    main.change_scene("game")
    body = core.physics.PhysicsBody()
    body.add(core.collider.Collider2D(core.collider.RectangleCollisionShape))
    game.add(body)
    cam = core.camera.Camera2D()
    game.add(cam)
    
    game.camera = cam
    
    body.add(core.node.Node2D())
    main.run()