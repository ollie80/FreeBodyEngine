
class Scene:
    def __init__(self, main: "Main"):
        self.SDL = main.SDL

        self.main = main
        self.entities: list[Entity] = []
        
        self.camera: engine.graphics.Camera
        self.files: engine.files.FileManager = self.main.files

        self.camera = engine.graphics.Camera(vector(0, 32), self, 1)
        self.texture_locker = engine.data.KeyLocker()
        self.glCtx: moderngl.Context = self.main.glCtx
        self.glCtx.enable(moderngl.BLEND)
        self.glCtx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.scene_texture = self.glCtx.texture(self.main.window_size, 4)
     

        self.graphics = engine.graphics.Graphics(self, self.glCtx)      
            
        self.add(self.camera)
        self.input = InputManager(self)
        
        
        self.ui = engine.ui.UIManager(self)

        self.update_mouse_pos()

    
    def graphics_setup(self):
        if not self.SDL:
            
            self.screen = self.glCtx.framebuffer(color_attachments=[self.scene_texture])

            self.program = self.glCtx.program(vertex_shader=scene_vertex_shader, fragment_shader=scene_fragment_shader)

            # Define vertices for a fullscreen quad (to display the framebuffer texture)
            vertices = np.array([
                -1, -1,  0, 0,
                1, -1,  1, 0,
                -1,  1,  0, 1,
                1,  1,  1, 1,
            ], dtype='f4')

            vbo = self.glCtx.buffer(vertices)
            self.vao = self.glCtx.simple_vertex_array(self.program, vbo, 'in_vert', 'in_text')
        else:
            self.display = pygame.surface.Surface((self.main.window_size[0] / self.camera.zoom, self.main.window_size[1] / self.camera.zoom))

    def set_active_camera(self, camera_id):
        for entity in self.entities:
            if entity.__class__ == Camera:
                if entity.camera_id == camera_id:
                    self.camera = entity

    def on_resize(self):
        self.graphics.on_resize()
        #self.lighting_manager.on_resize()
        self.camera.on_resize()
        self.ui.on_resize()
        self.glCtx.viewport = (0, 0, self.main.window_size[0], self.main.window_size[1])
    
    def event_loop(self, event):
        self.input.event_loop(event)
        for entity in self.entities:
            entity.on_event_loop(event)
        
    def on_post_draw(self):
        pass

  
    def update_mouse_pos(self):
        self.mouse_screen_pos = vector(pygame.mouse.get_pos())
        self.mouse_world_pos = vector((self.camera.position.x - (self.main.window_size[0]/2) / self.camera.zoom) + (self.mouse_screen_pos[0] / self.camera.zoom), (self.camera.position.y - (self.main.window_size[1]/2) / self.camera.zoom) + (self.mouse_screen_pos[1] / self.camera.zoom))

    def add(self, actor):
        self.entities.append(actor)

    def on_update(self, dt):
        pass

    def draw(self):
        self.on_draw()

        for entity in self.entities:
            entity.on_draw()
        
        self.graphics.draw()

        self.on_post_draw()

    def on_draw(self):
        pass

    def update(self, dt):
        self.input.handle_input()
        self.update_mouse_pos()
        self.graphics.update(dt)
        for entity in self.entities:
            entity.update(dt)
        self.on_update(dt)
        self.ui.update(dt)
        self.draw()



class SceneTransition:
    def __init__(self, main: "Main", vert, frag, duration, curve = engine.math.Linear()):
        self.elapsed = 0
        self.duration = duration 
        self.time: int = 0
        
        self._reversed = False

        self.main = main
        self.curve = curve

        self.program = self.main.glCtx.program(vert, frag)
        
        self.vao = engine.graphics.create_fullscreen_quad(self.main.glCtx, self.program)        

    def update(self, dt):
        if not self._reversed:
            self.elapsed = min(self.elapsed + dt, self.duration) 
            self.time = self.curve.get_value(self.elapsed/self.duration)

            if self.time >= 1:
                self._reversed = True
                self.main._set_scene(self.main.transition_manager.new_scene)
        else:
            self.elapsed = max(self.elapsed - dt, 0)
            if self.elapsed == 0:
                self.time = 0
            else:
                self.time = self.curve.get_value(self.elapsed/self.duration)            
            
            if self.time <= 0:
                self.main.transition_manager.current_transition = None        
        

    def draw(self):
        self.program['time'] = self.time
        if "inverse" in self.program:
            self.program['inverse'] = not self._reversed 
        self.main.glCtx.screen.use()
        self.vao.render(moderngl.TRIANGLE_STRIP)

class FadeTransition(SceneTransition):
    def __init__(self, main: "Main", duration: int):
        super().__init__(main, main.files.load_text('engine/shader/graphics/empty.vert'), main.files.load_text('engine/shader/scene_transitions/fade.glsl'), duration, engine.math.EaseInOut())

class StarWarsTransition(SceneTransition):
    def __init__(self, main: "Main", duration: int):
        super().__init__(main, main.files.load_text('engine/shader/graphics/uv.vert'), main.files.load_text('engine/shader/scene_transitions/starwars.glsl'), duration, engine.math.EaseInOut())

class SceneTransitionManager:
    def __init__(self, main: Main):
        self.main = main
        self.current_transition: SceneTransition = None
        self.new_scene: str = None

    def transition(self, transition: SceneTransition, new_scene: str):
        self.current_transition = transition
        self.new_scene = new_scene

    def update(self, dt):
        if self.current_transition:
            self.current_transition.update(dt)

    def draw(self):
        if self.current_transition:
            self.current_transition.draw()

class SplashScreenScene(Scene):
    def __init__(self, main: Main, duration: int, new_scene: str, texture: moderngl.Texture, color: str, transition=None):
        self.timer = Timer(duration)
        self.duration = duration
        self.timer.activate()
        self.transition = transition
        super().__init__(main)
        self.graphics.rendering_mode = "general"
        self.camera.background_color.hex = color

        self.new_scene = new_scene
        aspect = engine.graphics.get_texture_aspect_ratio(texture)
        self.ui.add(engine.ui.UIImage(self.ui, texture, {"anchor": "center", "height": "50%h", "aspect-ratio": aspect}))
        
        self.started_transition = False

    def on_update(self, dt):
        self.timer.update(dt)
        
        if self.timer.complete and not self.started_transition:
            self.started_transition = True
            if self.transition == None:
                transition =  StarWarsTransition(self.main, self.duration)
            else:
                transition = self.transition
            self.main.change_scene(self.new_scene, transition)
