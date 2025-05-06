
class SoundEmmiter(Entity):
    def __init__(self, position, sound, scene, radius, max_volume=1, loop=False, tag=""):
        super().__init__(position, scene)
        self.sound = sound
        self.sound.set_volume(max_volume)
        self.max_volume = max_volume
        self.radius = radius
        self.prev_volume = 0
        self.loop = loop

    def play(self):
        loops = 0
        if self.loop:
            loops = -1

        self.sound.play(loops)

    def stop(self):
        self.sound.stop()

    def update_volume(self):
        distance = self.scene.camera.center.distance_to(self.position)
        volume = min((distance * 100)/self.radius, self.max_volume)
        self.sound.set_volume(volume)

    def on_update(self, dt):
        self.update_volume()

class RandomSoundEmmiter(SoundEmmiter):
    def __init__(self, pos, sounds: list[pygame.Sound], scene, radius, max_volume):
        self.sounds = sounds
        
        super().__init__(pos, sounds[0], scene, radius, max_volume)
        
    def change_sound(self):
        self.sound = self.sounds[random.randint(0, len(self.sounds) - 1)]
        self.update_volume()

    def play(self):
        self.change_sound()
        super().play()
