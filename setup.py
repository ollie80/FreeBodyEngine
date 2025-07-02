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
)