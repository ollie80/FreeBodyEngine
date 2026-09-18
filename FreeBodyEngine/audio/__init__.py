from FreeBodyEngine.utils import get_platform

# audio.sound imports sounddevice (PortAudio) - a ctypes binding to a real
# native audio device library that simply doesn't exist inside a Pyodide/
# WASM browser session (sys.platform == "emscripten" - see utils.
# get_platform()'s docstring); soundfile/scipy pull in their own native
# libraries too. None of that is importable there at all, so importing it
# unconditionally would make `import FreeBodyEngine` itself crash on the
# web platform before anything else - including graphics/window setup -
# ever got a chance to run. Audio playback for the web backend (a Web
# Audio API-backed Sound, presumably) isn't implemented yet; skip the
# import there instead of failing the whole engine over it, the same way
# graphics/__init__.py guards its own PyOpenGL-dependent gl33 import.

def get_audio_manager():
    if get_platform() != "web":
        from FreeBodyEngine.audio import sound_file
        return sound_file.SoundFileAudioManager() 
    else:
        from FreeBodyEngine.audio import web
        return web.PyodideAudioManager()


