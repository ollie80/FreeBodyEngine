from setuptools import setup, find_packages
import json

setup(
    name="FreeBodyEngine",
    version='0.1',
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
    install_requires=["PyOpenGL >= 3.1.9", "pywin32 >= 310", "numpy >= 2.3.1", "glfw >= 2.9.0"]
)