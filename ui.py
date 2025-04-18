import numpy as np
import FreeBodyEngine as engine
import pygame
import random
import moderngl

UIELEMENT_FRAG_SHADER = """
#version 330 core

in vec2 uv;
out vec4 f_color;


void main() {
    

    f_color = vec4(uv, 1.0, 1.0);
}
"""

UIELEMENT_VERT_SHADER = """
#version 330 core

in vec2 texCoord;
in vec2 vert;
out vec2 uv;

uniform vec3 rot;

void main() {
    uv = texCoord;

    // Rotation matrices
    float cx = cos(rot.x);
    float sx = sin(rot.x);
    float cy = cos(rot.y);
    float sy = sin(rot.y);
    float cz = cos(rot.z);
    float sz = sin(rot.z);

    // Rotation around X-axis
    mat3 rotX = mat3(
        1.0, 0.0,  0.0,
        0.0,  cx, -sx,
        0.0,  sx,  cx
    );

    // Rotation around Y-axis
    mat3 rotY = mat3(
         cy, 0.0, sy,
         0.0, 1.0, 0.0,
        -sy, 0.0, cy
    );

    // Rotation around Z-axis
    mat3 rotZ = mat3(
        cz, -sz, 0.0,
        sz,  cz, 0.0,
        0.0, 0.0, 1.0
    );

    // Combine rotations: Z * Y * X (standard order)
    mat3 rotation = rotZ * rotY * rotX;

    vec3 rotatedVert = rotation * vec3(vert, 0.0);

    gl_Position = vec4(rotatedVert, 1.0);
}
"""

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
        self.program = self.manager.graphics.ctx.program(UIELEMENT_VERT_SHADER, UIELEMENT_FRAG_SHADER)
        
    
        #rects
        self.container: pygame.FRect
        
        self.rect: pygame.FRect
        self.interior_rect: pygame.FRect
        

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
        print(self.rect)
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
        self.program = self.graphics.ctx.program(engine.graphics.uv_vert_shader, engine.graphics.texture_frag_shader)
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
    

class _Element:
    def __init__(self, tag="none", style_overide: dict[str, str] = {}, type="none", text = ""):
        self.tag = tag
        self.type = type
        self.id = pygame.time.get_ticks() # this is to differentiate each instance so the index isnt always one if all items in a grid are the same
        self.elements: list[Element] = []
        self.neighbors: list[Element] = []

        self.size = (0,0)
        
        self.surf: pygame.surface.Surface
        self.exterior_rect: pygame.rect.Rect
        self.rect: pygame.rect.Rect
        self.interior_rect: pygame.rect.Rect
        self.text_rect: pygame.rect.Rect
        self.cursor_set = True

        self.style_overide = style_overide
        self.style = {"bg-color": "$BG", "border": True, "visible": True, "border-width": 2, "border-radius": 0, "border-color": "#FFFFFF", "margin": 3, "padding": 3, "width": '%w80', 'height': "%v80", 'center-hor': False, 'center-vert': False, "grid": False, "grid-row-gap": 0, "grid-col-gap": 0, "max-row-items": 6, "font-align-x": "center","font-align-y": "center", 'font': "@test", 'font-size': "%vi14", "font-color": "#FFFFFF", "wrap-width": "%wi100", "font-AA": True, "hover-cursor": pygame.cursors.arrow}

        self.clicked = False
        self.focused = False
        self.hover = False
        self.mouse_down = False


        self.text = text
        
        self.manager: UIManager

    def initialize(self, manager: "UIManager", parent: "Element" = None):
        self.manager = manager
        self.parent = parent
        self.style = self.get_style()

        self.draw()
        self.on_initialize()
     
    def on_draw(self):
        pass

    def on_initialize(self):
        pass

    def resize(self):
        self.draw()
        self.on_resize()
        
        for element in self.elements:
            element.resize()

    def on_resize(self):
        pass

    def get_element(self, tag) -> "Element":
        for element in self.elements:
            if element.tag == tag:
                return element
            else:
                return element.get_element(tag)
        return None

    def get_style(self) -> dict[str, str]: 
        new_style = self.style.copy()
        for style in self.manager.style:
            new_style[style] = self.manager.style[style]
        for style in self.style_overide:
            new_style[style] = self.style_overide[style]
        return new_style
    
    def set_styles(self, styles: dict[str, any]):
        new_style = self.style.copy()
        
        for style in styles:
            new_style[style] = styles[style]
        
        self.style = new_style

    def add(self, element: "Element"):
        self.elements.append(element)
        element.initialize(self.manager, self)

    def remove(self, element):
        self.elements.remove(element)

    def get_value(self, value):
        if not isinstance(value, str):
            return value
        elif value.startswith("%ww"): # percentage of window's width
            return (int(value.removeprefix("%ww")) * 0.01) * self.manager.window_size[0]
        elif value.startswith("%wv"): # percentage of window's height
            return (int(value.removeprefix("%wv")) * 0.01) * self.manager.window_size[1]
        elif value.startswith("%wi"):
            return int((int(value.removeprefix("%wi")) * 0.01) * self.interior_rect.width) 
        elif value.startswith("%vi"):
            return int((int(value.removeprefix("%vi")) * 0.01) * self.interior_rect.height)
        elif value.startswith("%w"): # percentage of container's (window or parent's) width
            return (int(value.removeprefix('%w')) * 0.01) * self.container_rect.size[0]
        elif value.startswith("%v"): # percentage of container's height
            return (int(value.removeprefix("%v")) * 0.01) * self.container_rect.size[1]
        
        elif value.startswith("$"):
            return self.manager.colors[value]
        elif value.startswith("#"):
            return value    

    def update_neighbors(self):
        if self.parent:
            self.neighbors = self.parent.elements
        else:
            self.neighbors = self.manager.elements

    def update_container_rect(self):
        if self.parent:
            self.container_rect = self.parent.interior_rect
        else:
            self.container_rect = pygame.rect.Rect(0, 0, self.manager.window_size[0], self.manager.window_size[1]) 

    def get_border_radius(self):
        if isinstance(self.style['border-radius'], list):
            return [self.get_value(self.style['border-radius'][0]), self.get_value(self.style['border-radius'][1]), self.get_value(self.style['border-radius'][2]), self.get_value(self.style['border-radius'][3])]
        else:
            return [self.get_value(self.style['border-radius']), self.get_value(self.style['border-radius']), self.get_value(self.style['border-radius']), self.get_value(self.style['border-radius'])]

    def in_grid(self) -> bool:
        if self.parent:
            return self.parent.style['grid']
        else:
            return False
    
    def update_size(self):
        self.size = (self.get_value(self.style["width"]), self.get_value(self.style["height"]))

    def update_index(self):
        self.index = self.neighbors.index(self)

    def update_padding(self):
        padding = self.style['padding']
        if isinstance(self.style['padding'], list):
            self.padding = [self.get_value(padding[0]), self.get_value(padding[1]), self.get_value(padding[2]), self.get_value(padding[3])]
        else:
            U_padding = self.get_value(padding)
            self.padding = [U_padding, U_padding, U_padding, U_padding] 
    
    def update_margins(self):  
        style_margins = self.style['margin']  
        if isinstance(self.style['margin'], list):
            margins = [self.get_value(style_margins[0]), self.get_value(style_margins[1]), self.get_value(style_margins[2]), self.get_value(style_margins[3])]
        else:
            u_margins = self.get_value(style_margins)
            margins = [u_margins, u_margins, u_margins, u_margins]

        if self.style['center-hor'] == True and len(self.neighbors) == 1:
           left = (self.container_rect.size[0] - self.size[0]) / 2
           right = (self.container_rect.size[0] - self.size[0]) / 2
        
        else:
            left = self.get_value(margins[0])
            right = self.get_value(margins[1])
        
        if self.style['center-vert'] == True and len(self.neighbors) == 1:
            top = (self.container_rect.size[1] - self.size[1]) / 2
            bottom = (self.container_rect.size[1] - self.size[1]) / 2

        else:
            top = self.get_value(margins[2])
            bottom = self.get_value(margins[3])
        
        self.margins = [left, right, top, bottom]

    def get_grid_item(self, row, col):
        index = (row * self.style['max-row-items']) + col
        return self.elements[index]

    def update_exterior_rect(self):
        width = self.size[0] + self.margins[0] + self.margins[1]
        height = self.size[1] + self.margins[2] + self.margins[3]
        
        if self.in_grid():
            max_row_items = self.parent.style['max-row-items']
            row = self.index // max_row_items
            col = self.index % max_row_items
            
            if row == 0:

                top = self.container_rect.top
            else:

                top = self.parent.get_grid_item(row - 1, col).exterior_rect.bottom + self.parent.style['grid-row-gap']

            if col == 0:
                left = self.container_rect.left
            else:

                left = self.parent.get_grid_item(row, col - 1).exterior_rect.right + self.parent.style['grid-col-gap']
        else:
            left = self.container_rect.left

            top = self.container_rect.top
        
        self.exterior_rect = pygame.rect.Rect(left, top, width, height)
    
    def update_interior_rect(self):
        left = self.rect.left + self.padding[0] 
        top = self.rect.top + self.padding[2]
        width = self.size[0] - (self.padding[1] + self.padding[0])
        height = self.size[1] - (self.padding[3] + self.padding[2])
    
        self.interior_rect = pygame.rect.Rect(left, top, width, height)

    def update_rect(self):
        self.update_container_rect()
        self.update_size()
        self.update_neighbors()
        self.update_index()
        self.update_margins()
        self.update_padding()
        self.update_exterior_rect()
        
        left = self.exterior_rect.left + self.margins[0]
        top = self.exterior_rect.top + self.margins[2]

        self.rect = pygame.rect.Rect(left, top, self.size[0], self.size[1])

        self.update_interior_rect()
    
    def draw(self):
        self.update_rect()
        border_radius = self.get_border_radius()
        if  self.style["border"] == True:
            pygame.draw.rect(self.manager.surface, self.get_value(self.style["border-color"]), self.rect.inflate(self.get_value(self.style['border-width']), self.get_value(self.style['border-width'])), border_top_left_radius=border_radius[0], border_bottom_left_radius=border_radius[1], border_top_right_radius=border_radius[2], border_bottom_right_radius=border_radius[3])        

        pygame.draw.rect(self.manager.surface, self.get_value(self.style["bg-color"]), self.rect, border_top_left_radius=border_radius[0], border_bottom_left_radius=border_radius[1], border_top_right_radius=border_radius[2], border_bottom_right_radius=border_radius[3])

        if self.text != "":
            self.draw_text()

        self.on_draw()

    def mouse_input(self, mouse_down, mouse_up):
        self.check_hover()
        
        if self.hover and self.mouse_down and mouse_up:
            self.manager.reset_clicked()
            self.manager.reset_focus()
            self.clicked = True
            self.focused = True
            self.mouse_down = False
            
        else:
            self.clicked = False

        if self.hover and mouse_down and not self.clicked:
            self.manager.reset_mousedown()
            self.mouse_down = True

        for element in self.elements:
            element.mouse_input(mouse_down, mouse_up)

    def check_hover(self):
        mouse_pos = pygame.mouse.get_pos()
        if self.rect.collidepoint(mouse_pos):
            self.manager.reset_hover()
            self.hover = True
        else:
            self.hover = False
        
        self.update_cursor()

    def update_cursor(self):
        if self.hover == True:
            pygame.mouse.set_cursor(self.style["hover-cursor"])
            self.manager.cursor_set = True
            self.cursor_set = True
        if not self.hover and self.cursor_set:
            self.cursor_set = False
            self.manager.cursor_set = False


    def draw_text(self):
        text_surf = self.manager.render_text(self.text, self.get_value(self.style["font"]), self.get_value(self.style["font-size"]), self.get_value(self.style["font-color"]), wrap_length=self.get_value(self.style["wrap-width"]))
        
        self.update_text_rect(text_surf)
        self.manager.surface.blit(text_surf, self.text_rect)
    
    def update_text_rect(self, surf: pygame.surface.Surface):
        align_x = self.style["font-align-x"]
        align_y = self.style["font-align-y"]
        if align_x == "center":
            left = (self.interior_rect.left + self.interior_rect.width/2) - (surf.width/2)
    
        if align_y == "center":
            top = (self.interior_rect.top + self.interior_rect.height/2) - (surf.height/2)
        
        if align_x == "left":
            left = self.interior_rect.left
            
        if align_y == "top":
            top = self.interior_rect.top
        
        if align_x == "right":
            left = self.interior_rect.right - surf.width

        if align_y == "bottom":
            top = self.interior_rect.bottom - surf.height
    
        if top < self.interior_rect.top:
            top = self.interior_rect.top

        if left < self.interior_rect.left:
                left = self.interior_rect.left
        

        self.text_rect = pygame.rect.Rect(left, top, surf.width, surf.height)
        
    def on_update(self):
        pass
            
    def update(self):
        if self.clicked:
            print("clicked")
        self.on_update()

class _TextInput(_Element):
    def __init__(self, tag="", style_overide={}, type="", text="Hello"):
        super().__init__(tag, style_overide, type, text) 
        self.set_styles({"height": 50, "width": 400, "border-width": 2, "border-color": "#000000", "padding": [20, 0, 4, 0], "bg-color": "#FFFFFF", "border-radius":24, "placeholder": "Placeholder", "placeholder-font": "@deafult", "placeholder-bold": False, "placeholder-italic": False, "placeholder-color": "#000000", "placeholder-size": "%vi100", "font-size": "%vi100", "font-color": "#000000", "hover-cursor": 1, "font-align-x": "left", "font-align-y": "center"})
        self.placeholder_active = False
        self.cursor_index = 5
        self.clicked_element: Element | None = None

    def update_text(self):
        if len(self.text) != 0 and isinstance(self.text, str):
           pass
        
        else:
            self.placeholder_active = True
        
        self.draw_text()

    def draw_text(self):
        if not self.placeholder_active:
            text_surf = self.manager.render_text(self.text, self.get_value(self.style["font"]), self.get_value(self.style["font-size"]), self.get_value(self.style["font-color"]), wrap_length=self.get_value(self.style["wrap-width"]))
        
        else:    
            text_surf = self.manager.render_text(self.style["placeholder"], self.get_value(self.style["placeholder-font"]), self.get_value(self.style["placeholder-size"]), self.get_value(self.style["placeholder-color"]), wrap_length=self.get_value(self.style["wrap-width"]))
            
        self.update_text_rect(text_surf)
        self.manager.surface.blit(text_surf, self.text_rect)
    
    def draw_text_cursor(self):
        font: pygame.font.Font = self.manager.get_font(self.get_value(self.style["font"]), self.get_value(self.style['font-size']))
        preceding_text = self.text[0:self.cursor_index]

        height = self.style["font-size"]  
        width = 3
        top = self.text_rect.top

        if self.cursor_index == 0:
            left = self.text_rect.left
        else:
            left = font.size(preceding_text)[0]

        rect = pygame.rect.Rect(self.get_value(left), self.get_value(top), self.get_value(width), self.get_value(height))

        pygame.draw.rect(self.manager.screen, "#000000", rect)


    def on_update(self):
        
        self.update_text()
        self.draw_text_cursor()

class _UIManager:
    def __init__(self):
        self.elements: list[Element] = []
        self.index = 0
        self.mouse_down = False
        self.cursor_set = False
    
        self.window_size = (0,0)
        self.surface = pygame.surface.Surface(self.window_size)

        self.colors: dict[str, str] = {"$BG": '#00000000'}
        self.fonts: dict[str, str]  = {"@default": None}        
        self.style: dict[str, str] = {}
        self.font_cache: dict[str, dict[str, pygame.font.Font]] = {}
        
    def initialize(self, scene: engine.core.Scene):
        self.scene: engine.core.Scene = scene
        self.screen = self.scene.main.screen

        self.window_size = self.scene.main.window_size
        self.surface = pygame.surface.Surface(self.window_size)
        self.surface.fill("green")
        self.surface.set_colorkey("green")

    def render_text(self, text, font_path, size, color="white", bold=False, italic=False, wrap_length=99999) -> pygame.surface.Surface:
        font: pygame.font.Font = self.get_font(font_path, size)
        font.set_bold(bold)
        font.set_italic(italic)
        return font.render(text, True, color, wraplength=wrap_length)
        
    def get_font(self, font_path, size):
        key = (font_path, size)

        if key not in self.font_cache:
            self.font_cache[key] = pygame.font.Font(font_path, size)
        
        return self.font_cache[key]

    def get_element(self, tag):
        for element in self.elements:
            if element.tag == tag:
                return element
            else:
                return element.get_element(tag)
        return None

    def add(self, element: _Element):
        self.elements.append(element)
        element.initialize(self, None)

    def remove(self, element: _Element):
        self.elements.remove(element)
    
    # Really shitty solution for figuring out which element is focused but im too lazy rn so i will fix it later
    def reset_hover(self):
        for element in self.elements:
            element.hover = False

    def reset_mousedown(self):
        for element in self.elements:
            element.mouse_down = False
    
    def reset_clicked(self):
        for element in self.elements:
            element.clicked = False

    def reset_focus(self):
        for element in self.elements:
            element.focused = False

    def event_loop(self, event):
        mouse_down = False
        mouse_up = False
        if event.type == pygame.VIDEORESIZE:
            self.resize()
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_down = True
        if event.type == pygame.MOUSEBUTTONUP:
            mouse_up = True
        
        for element in self.elements:
            element.mouse_input(mouse_down, mouse_up)

    def resize(self):
        self.window_size = self.scene.main.window_size

        self.surface = pygame.surface.Surface(self.window_size)
        self.surface.fill("green")
        self.surface.set_colorkey("green")

        
        for element in self.elements:
            element.resize()
            
    def update(self):
        self.index = 0
        self.window_size = self.scene.main.window_size
        if not self.cursor_set:
            pygame.mouse.set_cursor(0)
        
        
        for element in self.elements:
            element.update()

        self.screen.blit(self.surface, (0,0))
    
        self.reset_clicked()
