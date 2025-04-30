from typing import Optional, Union, Literal
import numpy as np
import FreeBodyEngine as engine
import pygame
import random
import moderngl


class UIAnimation:
    def __init__(self, element: "UIElement", target_style: str, duration: int, end_val: any):
        self.element: UIElement = element
        self.target_style = target_style
        
        self.elapsed = 0
        self.duration = duration

        self.start = self.element[target_style]
        self.end = end_val

        if not (self.start.__class__ == self.end.__class__):
            raise ValueError(f"UIAnimation with target style: {self.target_style}. Start value ({self.start.__class__}) is not the same type as end value {self.start.__class__}.")

    def _lerp(self, x, y, t):
        pass

    def _lerp_num_tuple(self, x: tuple, y: tuple, t: int):
        new = []
        if len(x) != len(y):
            raise ValueError("Iterable values must be the same length. On Animation")
        
        for i in range(x):    
            new.append(self._lerp(x[i], y[i], t))

    def __repr__(self):
        return f"{self.__class__}({self.element}, duration={self.duration}, target_style={self.target_style}, eng_val={self.end}, start_val: {self.start})"

    def _lerp_num_list(x, y, t): # probably not required
        pass

    def update(self, dt):
        self.elapsed += dt
        t = self.duration / self.elapsed
        self.element.draw()

class UIElement:  
    def __init__(self, manager: "UIManager", style: dict[str, any]):
        self.animations: list[UIAnimation] = []
        
        self.parent = UIElement
        self.children: list[UIElement] = []
        
        self.manager: UIManager = manager

        self.style = style
        self.z = 0

        # graphics
        self.program = self._generate_shader_program()
    
        #rects
        self.container: pygame.FRect
        
        self.rect: pygame.FRect
        self.interior_rect: pygame.FRect
        
    def _generate_shader_program(self) -> moderngl.Program:
        return self.manager.graphics.ctx.program(self.manager.scene.files.load_text('engine/shader/ui/element.vert'), self.manager.scene.files.load_text('engine/shader/ui/image.frag'))
    
    def _calculate_rect(self):
        size = self._get_size()
        pos = self._get_pos(size)

        self.rect = pygame.FRect(*pos, *size)
 
    def _calculate_interior(self):
        style = self._get_padding()
        padding = (style[0] * self.rect.size[0], style[1] * self.rect.size[0], style[2] * self.rect.size[1], style[3]* self.rect.size[1])
        
        left, top = (self.rect.left + padding[0], self.rect.top + padding[2]) 
        width, height = (self.rect.size[0] - padding[0] - padding[1], self.rect.size[1] - padding[2] - padding[3])

        self.interior_rect = pygame.FRect(left, top, width, height)

    def start_animation(self, style: str, end: any, duration: int):
        self.animations.append(UIAnimation(self, style, duration, end))
    
    def _apply_style(self):
        for uniform in self.program:
            if uniform == "rot":
                self.program['rot'] = self.style.get("rotation", (0, 0, 0))
            if uniform == "borderRadius":
                self.program['borderRadius'] = self._get_border_radius()
            if uniform == "resolution":
                self.program['resolution'] = self.manager.scene.main.window_size

    def _get_border_radius(self):
        style = self.style.get("border-radius", 0)
        if isinstance(style, tuple):
            if len(style) == 2:
                x = style[0]/100
                y = style[1]/100
                return (x, x, y, y)
            elif len(style) == 4:
                return (style[0]/100, style[1]/100, style[2]/100, style[3]/100)
            
            else:
                ValueError("Incorect border radius format, must be (x, y) or (left, right, top, bottom)")
        
        elif isinstance(style, int) or isinstance(style, float):
            x = style/100
            return (x, x, x, x)

    def _get_padding(self):
        style = self.style.get("padding", 0)
        if isinstance(style, tuple):
            if len(style) == 2:
                x = style[0]
                y = style[1]
                return (x, x, y, y)
            elif len(style) == 4:
                return style
            
            else:
                ValueError("Incorect padding format, must be (x, y) or (left, right, top, bottom)")
        
        elif isinstance(style, int) or isinstance(style, float):
            return (style, style, style, style)
    
    def _calculate_grid(self):
        pass

    def _calculate_layout(self):
        self._calculate_rect()
        self._calculate_interior()

    def _connvert_coord_val(self, val):
        if isinstance(val, str):
            if val.endswith('%h'):
                perectage = int(val.removesuffix('%h')) / 100
                val = self.container.height * perectage
                return val

            if val.endswith('%w'):
                perectage = int(val.removesuffix('%w')) / 100
                val = self.container.width * perectage
                return val

            else:
                ValueError(f"{val.capitalize()} has invalid suffix {val}. On Element: {repr(self)}")

        if isinstance(val, int):
            return val

        
    def _get_pos(self, size: tuple[int, int]):

        x = self._connvert_coord_val(self.style.get('x', 0))
        y = self._connvert_coord_val(self.style.get('y', 0))
        left = x - (size[0]/2)
        top = y - (size[1]/2)

        anchor = self.style.get('anchor', None)
        if anchor:
            
            if 'left' in anchor:
                left = x 
            elif 'right' in anchor:
                left = x + size[0]
            
            if 'top' in anchor:
                top = y
            elif 'bottom' in anchor:
                left = y + size[1]
    
        return (left, top)

    def _get_size(self) -> tuple[int, int]:
        aspect_ratio: tuple = self.style.get('aspect-ratio', None)

        if aspect_ratio != None:
            width = self._connvert_coord_val(self.style.get('width', None))
            height = self._connvert_coord_val(self.style.get('height', None))

            if width and height:
                if aspect_ratio[0] > aspect_ratio[1]:
                    multi = aspect_ratio[1] / aspect_ratio[0]
                    height = width * multi

                else:
                    multi = aspect_ratio[0] / aspect_ratio[1]
                    width = height * multi

            if width:
                multi = aspect_ratio[1] / aspect_ratio[0]
                height = width * multi

            elif height:
                multi = aspect_ratio[0] / aspect_ratio[1]
                width = height * multi

            else:
                raise ValueError(f"At least one size value must be set if aspect ratio is used. On Element {repr(self)}")

        else:
            width = self._connvert_coord_val(self.style.get('width', 100))
            height = self._connvert_coord_val(self.style.get('height', 100))

        return (width, height)

    def __repr__(self):
        return f"{self.__class__}({self.manager}, {self.style})"
        

    def _generate_graphics_objects(self):
        left = self.rect.left
        right = self.rect.right
        top = self.rect.top
        bottom = self.rect.bottom

        vbo = self.manager.graphics.ctx.buffer(data=np.array([
            # position (x, y), uv coords (u, v)
            left, -top, 0.0, 0.0,       
            right, -top, 1.0, 0.0,      
            right, -bottom, 1.0, 1.0, 
            left, -bottom, 0.0, 1.0        
        ], dtype="f4"))
        
        indices = self.manager.graphics.ctx.buffer(np.array([
        0, 1, 2,  # First triangle
        2, 3, 0   # Second triangle
        ], dtype="i4"))


        self.vao = self.manager.graphics.ctx.vertex_array(self.program, [(vbo, '2f 2f',  'vert', 'texCoord')], indices)

    def _draw_to_screen(self):
        self.manager.start_draw()
        self._calculate_layout()
        print(self.rect)
        self._generate_graphics_objects()
        self._apply_style()
        self.vao.render(moderngl.TRIANGLE_STRIP)
        self.manager.end_draw()

    def _check_click(self):
        if pygame.mouse.get_pressed()[0]:
            if self.rect.collidepoint(self.manager.scene.mouse_screen_pos):
                if self.manager.clicked_element.z <= self.z:
                    self.manager.clicked_element = self
    
    def _process_click(self):
        self.click()

    def click(self):
        pass

    def draw(self):
        self._draw_to_screen()
        for child in self.children:
            child.container = self.rect
            child.draw()

    def resize(self):
        for child in self.children:
            child.container = self.rect
        self.draw()

    def update(self, dt):
        for anim in self.animations:
            anim.update(dt)
        for child in self.children:
            child.update(dt)

class UIButton(UIElement):
    def __init__(self, manager: "UIManager", style: dict[str, any]):
        super().__init__(manager, style)

    def _check_click(self):
        if pygame.mouse.get_pressed()[0]:
            if self.rect.collidepoint(self.manager.scene.mouse_screen_pos):
                if self.manager.clicked_element.z <= self.z:
                    self.manager.clicked_element = self
    
    def _process_click(self):
        pass

class UIImage(UIElement):
    def __init__(self, manager: "UIManager", texture: moderngl.Texture, style: dict[str, any]):
        super().__init__(manager, style)
        self.key = "UIImage"
        self.texture = texture

    def _generate_shader_program(self) -> moderngl.Program:
        return self.manager.graphics.ctx.program(self.manager.scene.files.load_text('engine/shader/ui/element.vert'), self.manager.scene.files.load_text('engine/shader/ui/image.frag'))

    def _apply_style(self):
        super()._apply_style()
        for uniform in self.program:
            if uniform == 'tex':
    
                key = self.manager.scene.texture_locker.add(self.key)
                self.texture.use(key)
                self.program['tex'] = key
                self.manager.scene.texture_locker.remove(self.key)

class UIRootElement:
    def __init__(self, manager: "UIManager"):
        self.children: list[UIElement] = []
        self.manager = manager
        self.rect = pygame.FRect(0, 0, *self.manager.scene.main.window_size)

    def add(self, element: UIElement):
        self.children.append(element)
        element.container = self.rect
        element.draw()
    
    def draw(self):
        self.rect = pygame.FRect(0, 0, *self.manager.scene.main.window_size)
        
        for element in self.children:
            element.container = self.rect
            element.draw()

    def update(self, dt):
        for element in self.children:
            element.update(dt)

class UIManager:
    def __init__(self, scene: engine.core.Scene):
        self.key = "_ENGINE_ui"
        self.scene = scene
        self.graphics = self.scene.graphics
        self.root = UIRootElement(self)
        self.clicked_element: UIElement = None
        

        # graphics
        self.on_resize()
        self.program = self.graphics.ctx.program(self.scene.files.load_text("engine/shader/graphics/uv.vert"), self.scene.files.load_text("engine/shader/graphics/texture.frag"))
        self.vao = engine.graphics.create_fullscreen_quad(self.graphics.ctx, self.program)

    def on_resize(self):
        size = self.scene.main.window_size
        self.fbo = self.graphics.ctx.framebuffer((self.graphics.ctx.texture((size[0], size[1]), 4)))
        self.root.draw()
        
    def start_draw(self):
        self.fbo.use()

    def end_draw(self):
        self.graphics.ctx.screen.use()

    def click(self):
        if self.clicked_element:
            self.clicked_element.process_click()
            

    def draw(self):
        self.graphics.ctx.screen.use()
        key = self.scene.texture_locker.add(self.key)
        
        self.fbo.color_attachments[0].use(key)
        self.program['tex'] = key
        self.scene.texture_locker.remove(self.key)
        self.vao.render(moderngl.TRIANGLE_STRIP)

    def add(self, element: UIElement):
        self.root.add(element)
        

    def update(self, dt):
        self.root.update(dt)
        self.click()
