
# class InputManager: # im very sorry for what you're about to read
#     def __init__(self, scene: Scene):
#         self.scene = scene
#         self.actions: dict[str, list[str]]
#         self.active = {}
#         self.controllers = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

#         self.change_controller()
#         self.input_mappings = {"K_Down": pygame.K_DOWN, "K_Up": pygame.K_UP, "K_Left": pygame.K_LEFT, "K_Right": pygame.K_RIGHT, "K_A": pygame.K_a, "K_D": pygame.K_d, "K_W": pygame.K_w, "K_S": pygame.K_s, "K_T": pygame.K_t, "K_M": pygame.K_m, "K_L": pygame.K_l, "K_X": pygame.K_x, "K_C": pygame.K_c, "K_G": pygame.K_g, "K_F": pygame.K_f, "K_PGUP": pygame.K_PAGEUP, "K_ESCAPE": pygame.K_ESCAPE, "K_PGDOWN": pygame.K_PAGEDOWN, "K_F3": pygame.K_F3, "K_F4": pygame.K_F4}
#         self.mouse_mappings = {"M_SCRL_UP": -1, "M_SCRL_DOWN": 1}
#         self.controller_input =  {"C_DDown": False, "C_DUp": False, "C_DLeft": False, "C_DRight": False, "C_BY": False, "C_BB": False, "C_BA": False, "C_BX": False, "C_T1": False, "C_T2": False, "C_B1": False, "C_B2": False, "C_LStick_Up": False, "C_LStick_Down": False, "C_LStick_Left": False, "C_LStick_Right": False, "C_RStick_Up": False, "C_RStick_Down": False, "C_RStick_Left": False, "C_RStick_Right": False}

#         self.scroll_input = {"M_SCRL_UP": False, "M_SCRL_DOWN": False}

#         self.joy_stick_generosity = 0.2
#         self.get_controller_input()
#         self.curr_input_type = "key"

#         self.actions = self.scene.files.load_json('controlls/actions.json')
#         for action in self.actions:
#             self.active[action] = False

#     def get_mouse_pressed(self, type='game') -> tuple[bool, bool, bool]:
#         return pygame.mouse.get_pressed()

#     def get_controllers(self):
#         self.controllers = [pygame.joystick.Joystick(x) for x in range(pygame.joystick.get_count())]

#     def change_controller(self):
#         self.get_controllers()
#         if len(self.controllers) > 0:
#             self.controller = self.controllers[0]
#         else:
#             self.controller = None
            
#     def get_controller_input(self): # shitty controller standards kinda make this mess necessary
#         if len(self.controllers) > 0:
#             for input in self.controller_input:
#                 self.controller_input[input] = False
            
#             controller_name = self.controller.get_name()
#             if controller_name == "Xbox One Controller":
#                 dpad = self.controller.get_hat(0)
#                 if dpad[0] == -1:
#                     self.controller_input["C_DLeft"] = True
#                 if dpad[0] == 1:
#                     self.controller_input["C_DRight"] = True
#                 if dpad[1] == -1:
#                     self.controller_input["C_DDown"] = True
#                 if dpad[1] == 1:
#                     self.controller_input["C_DUp"] = True
                
#                 # left stick
#                 lStickHor = self.controller.get_axis(0)
#                 lStickVert = self.controller.get_axis(1)
#                 if lStickVert > 1 - self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Down"] = True
#                 elif lStickVert < -1 + self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Up"] = True
#                 if lStickHor > 1 - self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Right"] = True
#                 elif lStickHor < -1 + self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Left"] = True
#                 if lStickHor > 0.65 - self.joy_stick_generosity and lStickVert > 0.65 - self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Down"] = True
#                     self.controller_input["C_LStick_Right"] = True
#                 if lStickHor > 0.65 - self.joy_stick_generosity and lStickVert < -0.65 + self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Up"] = True
#                     self.controller_input["C_LStick_Right"] = True
#                 if lStickHor < -0.65 + self.joy_stick_generosity and lStickVert > 0.65 - self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Down"] = True
#                     self.controller_input["C_LStick_Left"] = True
#                 if lStickHor < -0.65 + self.joy_stick_generosity and lStickVert < -0.65 + self.joy_stick_generosity:
#                     self.controller_input["C_LStick_Up"] = True
#                     self.controller_input["C_LStick_Left"] = True

#                 # left stick
#                 rStickHor = self.controller.get_axis(2)
#                 rStickVert = self.controller.get_axis(3)
#                 if rStickVert > 1 - self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Down"] = True
#                 elif rStickVert < -1 + self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Up"] = True
#                 if rStickHor > 1 - self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Right"] = True
#                 elif rStickHor < -1 + self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Left"] = True

#                 if rStickHor > 0.65 - self.joy_stick_generosity and rStickVert > 0.65 - self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Down"] = True
#                     self.controller_input["C_RStick_Right"] = True
#                 if rStickHor > 0.65 - self.joy_stick_generosity and rStickVert < -0.65 + self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Up"] = True
#                     self.controller_input["C_RStick_Right"] = True
#                 if rStickHor < -0.65 + self.joy_stick_generosity and rStickVert > 0.65 - self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Down"] = True
#                     self.controller_input["C_RStick_Left"] = True
#                 if rStickHor < -0.65 + self.joy_stick_generosity and rStickVert < -0.65 + self.joy_stick_generosity:
#                     self.controller_input["C_RStick_Up"] = True
#                     self.controller_input["C_RStick_Left"] = True

#     def reset_actions(self):
#         for action in self.active:
#             self.active[action] = False

#     def check_action(self, action) -> bool: 
#         return self.active[action]

#     def event_loop(self, event):
#         if event.type == pygame.JOYDEVICEADDED:
#             self.change_controller()
#         if event.type == pygame.JOYDEVICEREMOVED:
#             self.change_controller()
#         if event.type == pygame.MOUSEWHEEL:
#             if event.y == self.mouse_mappings["M_SCRL_UP"]:
#                 self.scroll_input["M_SCRL_UP"] = True
#             if event.y == self.mouse_mappings["M_SCRL_DOWN"]:
#                 self.scroll_input["M_SCRL_DOWN"] = True

#     def handle_input(self):
#         pygame.event.get()
#         keys = pygame.key.get_pressed()

#         self.reset_actions()

#         for action in self.actions:
#             for input in self.actions[action]:
#                 if input.startswith("K") and keys[self.input_mappings[input]]:
#                     self.active[action] = True
#                 if self.controller != None:
#                     if input.startswith("C") and self.controller_input[input]:
#                         self.active[action] = True
#                 if input.startswith("M"):
#                     if input.startswith("M_SCRL") and self.scroll_input[input] == True:
#                         self.active[action] = True
                        
#         self.scroll_input["M_SCRL_UP"] = False
#         self.scroll_input["M_SCRL_DOWN"] = False
        
                    
#         self.get_controller_input()

