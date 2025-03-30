# this is a simple program for testing shaders, includes hot reloading

import os
import sys

sys.path.append(os.path.abspath("..."))  # Add parent directory to Python's module search path

import engine

import pygame

from pygame.math import Vector2 as vector

def remake_image():
    pass


class ShaderTestingScene(engine.core.Scene):
    def __init__(self, scene, path):
        super().__init__(scene)
        self.shader_path = os.path.abspath(path)
        self.check_timer = engine.core.Timer(0.1)    
        self.check_timer.activate()
        self.surf = pygame.Surface((32, 32))
        self.surf.fill("white")
        self.actor = engine.core.Actor(vector(0, 0), self, self.surf, "test")
        self.shader_text = engine.graphics.WORLD_VERT_SHADER

    def remake_shader(self):
        self.actor.image.set_shader(engine.graphics.Shader(engine.graphics.WORLD_VERT_SHADER, self.shader_text))


    def file_change_check(self) -> bool:
        new = self.files.load_text(self.shader_path)
        check = not new == self.shader_text
        self.shader_text = new
        return check

    def on_update(self, dt):
        self.check_timer.update(dt)
        if self.check_timer.complete:

            if self.file_change_check():
                self.remake_shader()
                print("hi")
            
            self.check_timer.activate()
            

if __name__ == "__main__":
        flags = pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.OPENGL
        main = engine.core.Main(window_size=(800, 800), flags=flags, fps=60)
        scene = ShaderTestingScene(main, sys.argv[1])
        main.add_scene(scene, "game")
        main.set_scene("game")
        main.run(0, 0)
        

