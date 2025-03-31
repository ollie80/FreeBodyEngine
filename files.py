import json
from pathlib import Path
import FreeBodyEngine as engine
import pygame
import sys
import ast
from pygame import Vector2 as vector

import os


class FileManager:
    def __init__(self, scene):
        self.path = "game"
        self.game_name = "FactoryGame"
        self.image_cache: dict[str, pygame.surface.Surface] = {}
        self.spritesheet_cache: dict[str, engine.graphics.Spritesheet] = {}
        self.shader_cache: dict[str, str] = {}
        self.scene: engine.core.Scene = scene

    def get_image(self, location: str, name: str, file_type: str = ".png", normal=None):
        if file_type == ".png":
            return self.parse_image(location, name, file_type, normal)
        if file_type == 'tex':
            return self.load_image(f"{self.path}/assets/graphics/{location}/{name}.png")
        if file_type == ".animation":
            return self.parse_animation(location, name)
        if file_type == ".composite":
            return self.parse_composite(location, name)

    def parse_image(self, location, name, file_type, normal:str|None=None):
        path = location+"/"+name
        
        file_path = os.path.abspath(self.path + "/assets" + "/graphics/image/" + path + file_type)
        tex = self.load_image(file_path)

        if normal == None:
            normal_path = os.path.abspath(self.path + '/assets' + '/graphics/image/' + path + "_normal" + file_type)
        else:
            normal_path = os.path.abspath(self.path + '/assets' + '/graphics/image/' + normal + file_type)
            
        normal_tex = None
        if os.path.exists(normal_path):
            normal_tex = self.load_image(normal_path)
        else:
            print("no file at path at: " + normal_path)
        return engine.graphics.Image(tex, name, self.scene, tex.size, normal=normal_tex)
    
    def parse_composite(self, location, name):
        path = self.path + f"/assets/graphics/image/{location}/{name}.composite"
        data = self.load_text(path)
        data = json.loads(data)
        images: list[engine.graphics.Image] = []
        i = 0
        for image in data['images']:

            split = image['path'].split('/')
            image_location = split[0] 

            image_name = split[1].split('.')[0]
            image_filetype = split[1].split('.')[1]

            normal_path = None
            if 'normal' in image.keys():
                normal_path = image['normal']
            images.append(self.get_image(image_location, image_name, '.' + image_filetype, normal_path))
            if 'shader' in image.keys():
                shader_data = image['shader']

                if 'location' in shader_data:
                    shader_location = shader_data['location']
                else:
                    shader_location = image_location

                if 'vert' in shader_data:
                    vert = self.load_shader(shader_location, shader_data['vert'])
                else:
                    vert = images[i].shader.vert

                if 'frag' in shader_data:
                    frag = self.load_shader(shader_location, shader_data['frag'])
                else:
                    frag = images[i].shader.frag
                
                shader: engine.graphics.Shader = self.parse_shader(shader_location, vert, frag)
                images[i].set_shader(shader)
                images[i].offset = vector(image['offset'])

            i+=1

        return engine.graphics.CompositeImage(name, images, self.scene)

    def parse_animation(self, location, name):
        anim_data = self.load_animation(location, name)
        anims = {}
        for animation in anim_data:
            anims[animation] = engine.graphics.Animation(anim_data[animation])
        player = engine.graphics.AnimationPlayer(self.get_spritesheet(location, name), anims)
        return engine.graphics.AnimatedImage(player, name, self.scene)

    def parse_shader(self, location, vert, frag):

        return engine.graphics.Shader(self.scene, vert, frag)

    def load_shader(self, location, name):
        path = location + "/" + name
        if self.shader_cache.get(path) != None:
            return self.shader_cache[path]
        else:
            file_path = os.path.abspath(self.path  + "/assets" + "/graphics/shader/" + path + ".glsl")

            try:
                file = open(file_path, "r")
                text = file.read()
                file.close()
                self.shader_cache[path] = text 
                return text
            except:

                print("couldn't shader file with path: " + file_path)
            

    def load_image(self, path):
        img = pygame.image.load(path).convert_alpha()
        return engine.graphics.surf_to_texture(img, self.scene.glCtx)

    def load_tileset(self, name: str) -> dict:
        file_path = os.path.abspath(self.path + "/assets" + "/tilesets/" + name + ".json")
        file = open(file_path, "r")
        text = file.read()
        file.close()
        return json.loads(text)
    
    def get_save_path(self):
        if sys.platform == "win32":  # Windows
            path = Path(os.getenv("APPDATA")) / self.game_name
        elif sys.platform == "darwin":  # macOS
            path = Path.home() / "Library" / "Application Support" / self.game_name
        else:  # Linux
            path = Path.home() / ".local" / "share" / self.game_name

        path.mkdir(parents=True, exist_ok=True) 
        return path

    def load_text(self, path):
        file = open(path, "r")
        text = file.read()
        file.close()
        return text
    
    def load_json(self, path):
        txt = self.load_text(path)
        return json.loads(txt)

    def load_animation(self, location, name):
        path = os.path.abspath(self.path + "/assets/graphics/animation/" + location + "/" + name + ".animation")
        text = self.load_text(path)
        return json.loads(text)

    def write_save_data(self, location: str, name: str, data: str, file_type=".json"):
        file_path = self.get_save_path() / location / (name + file_type)
        
        # Ensure the directory exists
        os.makedirs(file_path.parent, exist_ok=True)
        
        # Create the file only if it does not exist

        with open(file_path, "w") as file:
            file.write(data)  # Write as a string (JSON should be a string)
    

    def load_save_data(self, location: str, name: str, file_type = ".json") -> str:
        file_path = self.get_save_path() / location / (name + file_type)
        if os.path.exists(file_path):
            file = open(file_path, "r")
        else:
            return None
        text = file.read()
        
        file.close()
        return text
    
    def load_machine_data(self, name):
        path = self.path + "/assets/machines/" + name + ".json"
        text = self.load_text(path)
        return json.loads(text)

    def load_chunk_data(self, name: str):
        data = self.load_save_data("chunk", name, ".chk")
        print(data)
        if data != None:
            data_list = ast.literal_eval(data)
            return data_list 
        return None
    
    def save_chunk_data(self, name, data):
        self.write_save_data("chunk", name, str(data), ".chk")
    
    def parse_spritesheet(self, data: dict):
        image_path = self.path + "/assets" + "/graphics/image/"
        general = self.load_image(image_path + data['general'])
        normal = None
        use_normal = data["useNormal?"]
        if use_normal:    
            normal = self.load_image(image_path + data['normal'])
        return engine.graphics.Spritesheet(general, normal, use_normal, (data["size"][0], data["size"][1]))

    def get_spritesheet(self, location, name):
        path = location + "/" + name
        if path in self.spritesheet_cache.keys():
            return self.spritesheet_cache[path]
        else:
            file_path = os.path.abspath(self.path + "/assets" + "/graphics/image/" + path + ".spritesheet")
            data = self.load_json(file_path)
            self.spritesheet_cache[path] = self.parse_spritesheet(data)
            return self.spritesheet_cache[path]
    
