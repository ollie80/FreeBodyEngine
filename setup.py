from setuptools import setup, find_packages
import json

setup(
    name="FreeBodyEngine",
    version='0.06',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'freebody=FreeBodyEngine.cli.commands:main',
            'fb=FreeBodyEngine.cli.commands:main',
        ]
    },
    license="MIT",
    author="Oliver Morrison",
    long_description_content_type="text/markdown",
    install_requires=["PyOpenGL >= 3.1.9",
                "numpy >= 2.3.1",
                "glfw >= 2.9.0",
                "watchdog",
                "freetype-py",
                "PySDL2",
                "pysdl2-dll",
                "sounddevice",
                "soundfile",
                "scipy",

                #windows
                "pywin32; sys_platform == 'win32'",
                "windows-curses; sys_platform == 'win32'"
                ]
)