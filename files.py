import json
from pathlib import Path
import FreeBodyEngine as engine
import pygame
import sys
import ast
from pygame import Vector2 as vector

import os
import io

import struct

def read_assets(path):
    assets = {}
    with open(path, "rb") as f:
        while True:
            len_bytes = f.read(2)
            if not len_bytes:
                break
            name_len = struct.unpack("<H", len_bytes)[0]
            name = f.read(name_len).decode("utf-8")
            data_len = struct.unpack("<I", f.read(4))[0]
            data = f.read(data_len)
            assets[name] = data
    return assets


class FileManager:
    def __init__(self, main: engine.core.Main, path):
        self.path = "game"
        self.game_name = main.game_name
        self.image_cache: dict[str, pygame.surface.Surface] = {}
        self.spritesheet_cache: dict[str, engine.graphics.Spritesheet] = {}
        self.shader_cache: dict[str, str] = {}
        self.main: engine.core.Main = main

        #loading assets
        asset_path = path
        self.images = read_assets(asset_path+"images.pak")
        self.data = read_assets(asset_path+"data.pak")

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
        img = pygame.image.load(io.BytesIO(self.images[path])).convert_alpha()
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
        text = io.BytesIO(self.data[path]).read()
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
    
