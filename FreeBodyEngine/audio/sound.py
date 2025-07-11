import numpy as np
import sounddevice as sd
import soundfile as sf
import threading
import scipy.signal
from FreeBodyEngine.core.node import Node2D

class AudioManager:
    def __init__(self):
        self.volume = 1.0 
        self.sounds = []  
        self.lock = threading.Lock()

        self.sample_rate = 44100
        self.channels = 2

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype='float32',
            callback=self.callback,
            finished_callback=self.on_stream_finished,
            blocksize=1024,
            latency='low'
        )
        self.stream.start()
        self.running = True

    def callback(self, outdata, frames, time_info, status):
        with self.lock:
            if not self.sounds:
                outdata.fill(0)
                return

            mix = np.zeros((frames, self.channels), dtype='float32')

            to_remove = []
            for sound in self.sounds:
                data = sound.get_frames(frames)
                if data is None:
                    to_remove.append(sound)
                    continue

                data = data * (self.volume * sound.volume)

                mix[:len(data)] += data

            for s in to_remove:
                self.sounds.remove(s)

            np.clip(mix, -1, 1, out=mix)

            outdata[:] = mix

    def on_stream_finished(self):
        pass

    def add_sound(self, sound):
        with self.lock:
            self.sounds.append(sound)

    def create_sound(self, data):
        return Sound(data, self)

    def stop_all(self):
        with self.lock:
            self.sounds.clear()

    def shutdown(self):
        self.running = False
        self.stream.stop()
        self.stream.close()


def resample_audio(data, orig_sr, target_sr):
    duration = data.shape[0] / orig_sr
    target_length = int(duration * target_sr)
    resampled = scipy.signal.resample(data, target_length, axis=0)
    return resampled

class Sound:
    def __init__(self, data, manager: AudioManager):
        data, sr = sf.read(data, dtype='float32', always_2d=True)
        self.manager = manager
        self.sample_rate = sr
        self.volume = 1.0

        if sr != manager.sample_rate:
            data = resample_audio(data, sr, manager.sample_rate)
            self.sample_rate = manager.sample_rate

        if data.shape[1] == 1 and manager.channels == 2:
            data = np.repeat(data, 2, axis=1)

        self.data = data
        self.position = 0  
        self.paused = False
        self.stopped = True

    def get_frames(self, num_frames):
        if self.paused or self.stopped:
            return np.zeros((num_frames, self.manager.channels), dtype='float32')

        end = self.position + num_frames
        chunk = self.data[self.position:end]
        self.position = end

        if len(chunk) < num_frames:
            self.stopped = True
            
            # pad with zeros
            pad = np.zeros((num_frames - len(chunk), self.manager.channels), dtype='float32')
            return np.vstack((chunk, pad))

        return chunk

    def play(self):
        if self in self.manager.sounds:
            self.position = 0
            self.stopped = False
            self.paused = False
        else:
            self.position = 0
            self.stopped = False
            self.paused = False
            self.manager.add_sound(self)

    def pause(self):
        self.paused = True

    def stop(self):
        self.stopped = True
        self.position = 0

