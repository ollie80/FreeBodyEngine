import json
from pathlib import Path
import FreeBodyEngine as engine
import pygame
import moderngl

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
    """
    The asset manager loads the files packaged by the engine. You must use paths that are relative to your asset folder.
    """
    def __init__(self, main: engine.core.Main, path):
        self.path = "game"
        self.game_name = main.game_name
        self.main: engine.core.Main = main

        #loading assets
        asset_path = path
        self.images = read_assets(asset_path+"images.pak")
        self.data = read_assets(asset_path+"data.pak")


    def load_image(self, path, scene: engine.core.Scene, normal:str|None=None, size: tuple = None):
        tex = self.load_texture(path)

        normal_tex = None
        if normal != None:
            normal_tex = self.load_texture(normal)
        
        if size != None:
            img_size = size
        else:
            img_size = tex.size
            
        return engine.graphics.Image(tex, 'image', scene, img_size, normal=normal_tex)
    
    def load_composite(self, path, scene: engine.core.Scene):
        data = self.load_json(path)

        images: list[engine.graphics.Image] = []
        img_types = ["composite", "image", "animated"]
        for image_data in data['images']:
            img_type = image_data['type']
            if img_type in img_types:
                img_path = image_data['path']                
                if img_type == "image":
                    normal = image_data.get("normal", None)
                    size = image_data.get("size", None)
                    image = self.load_image(img_path, scene, normal, size)
                    
                    shader = image_data.get('shader', None)
                    if shader != None:
                        vert_data = image_data["shader"].get("vert")
                        if vert_data != None:
                            vert = self.load_text(vert_data)
                        else:
                            vert = self.load_text("engine/shader/graphics/world.vert")

                        frag_data = image_data["shader"].get("frag")
                        if frag_data != None:
                            frag = self.load_text(frag_data)
                        else:
                            frag = self.load_text("engine/shader/graphics/world.frag")
                        
                        image.set_shader(engine.graphics.Shader(self.main.active_scene, vert, frag))
                        
                
                elif img_type == "animated":
                    image = self.load_animation(img_path, scene)

                    shader = image_data.get('shader', None)
                    if shader != None:
                        vert_data = image_data["shader"].get("vert")
                        if vert_data != None:
                            vert = self.load_text(vert_data)
                        else:
                            vert = self.load_text("engine/shader/graphics/world.vert")

                        frag_data = image_data["shader"].get("frag")
                        if frag_data != None:
                            frag = self.load_text(frag_data)
                        else:
                            frag = self.load_text("engine/shader/graphics/animation.frag")
                        
                        image.set_shader(engine.graphics.AnimatedShader(self.main.active_scene, vert, frag))

                elif img_type == "composite":
                    image = self.load_composite(img_path)
                
                image.offset = vector(image_data.get("offset", (0, 0)))
                images.append(image)


            else:
                raise ValueError(f"Composite images types must be one of the following: {img_types}, instead got: {img_type}")

        return engine.graphics.CompositeImage('composite_image', images, self.main.active_scene)    

    def load_animation(self, path, scene):
        anim_data = self.load_json(path)

        anims = {}
        for animation in anim_data['animations']:
            anims[animation] = engine.graphics.Animation(anim_data['animations'][animation])
        player = engine.graphics.AnimationPlayer(self.load_spritesheet(anim_data['spritesheet']), anims)
        print(self.main.active_scene)
        return engine.graphics.AnimatedImage(player, "animated_image", scene)

    def load_shader(self, path):
        self.load_text(path) # ik its just a wrapper but most people arent gonna know to use the load_text function, bc a lot of people have a misunderstanding of how files work
            
    def load_texture(self, path, aa=moderngl.NEAREST):
        img = pygame.image.load(io.BytesIO(self.images[path])).convert_alpha()
        return engine.graphics.surf_to_texture(img, self.main.glCtx, aa)

    def load_tileset(self, path: str, scene) -> engine.tilemap.Tileset:
        data = self.load_json(path)
        if data['type'] == "static" or data['type'] == "auto":
            return engine.tilemap.Tileset(scene, data)
        else:
            raise NotImplementedError("Animated tiles are not yet implemented.")
    
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

    def write_save_data(self, location: str, name: str, data: any, file_type=".json"):
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
    
    def load_spritesheet(self, path: str):
        data = self.load_json(path)
        image_path = data['general']
        general = self.load_texture(image_path)
        normal = None
        use_normal = "normal" in data
        if use_normal:
            normal = self.load_texture(image_path)

        return engine.graphics.Spritesheet(general, normal, use_normal, (data["size"][0], data['size'][1]))

