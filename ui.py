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

        # graphics
        self.program = self._generate_shader_program()
        
    
        #rects
        self.container: pygame.FRect
        
        self.rect: pygame.FRect
        self.interior_rect: pygame.FRect
        
    def _generate_shader_program(self) -> moderngl.Program:
        return self.manager.graphics.ctx.program(self.manager.scene.files.load_text('engine/shader/ui/element.vert'), self.manager.scene.files.load_text('engine/shader/ui/image.frag'))
    
    def _calculate_rect(self):
        size = self.style.get("size", (50, 50))
    
        width, height = (((size[0] / 100)*self.container.size[0]) * 2, ((size[1] / 100)*self.container.size[1]) * 2)

        pos = self.style.get("pos", (0, 0))
        center = ((pos[0] / self.container.size[0]) * 200, (pos[1] / self.container.size[1]) * 200)

        left, top = ((center[0] - width/2) + self.container.centerx, (center[1] - height/2) + self.container.centery)
        
        self.rect = pygame.FRect(left, top, width, height)

        
    def _calculate_interior(self):
        style = self._get_padding()
        padding = (style[0] * self.rect.size[0], style[1] * self.rect.size[0], style[2] * self.rect.size[1], style[3]* self.rect.size[1])
        
        left, top = (self.rect.left + padding[0], self.rect.top + padding[2]) 
        width, height = (self.rect.size[0] - padding[0] - padding[1], self.rect.size[1] - padding[2] - padding[3])

        self.interior_rect = pygame.FRect(left, top, width, height)

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
        
    def _generate_graphics_objects(self):
        left = self.rect.left / 100
        right = self.rect.right / 100
        top = self.rect.top / 100
        bottom = self.rect.bottom / 100 

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
        self._generate_graphics_objects()
        self._apply_style()
        self.vao.render(moderngl.TRIANGLE_STRIP)
        self.manager.end_draw()

    def draw(self):
        self._draw_to_screen()
        for child in self.children:
            child.draw()

    def update(self, dt):
        for anim in self.animations:
            anim.update(dt)
        for child in self.children:
            child.update(dt)


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
    def __init__(self):
        self.children: list[UIElement] = []
        self.rect = pygame.FRect(-50, -50, 100, 100)

    def add(self, element: UIElement):
        self.children.append(element)
        element.container = self.rect
        element.draw()
    
    def draw(self):
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
        self.root = UIRootElement()

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
    
