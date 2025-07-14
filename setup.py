from setuptools import setup, find_packages
import os
import importlib
import sys

req_path = os.path.join(os.path.dirname(__file__), "FreeBodyEngine", "requirements.py")
spec = importlib.util.spec_from_file_location("requirements", req_path)
requirements_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(requirements_module)

requirements = [] 
requirements += requirements_module.GLOBAL

if sys.platform == "win32":
    for req in requirements_module.WINDOWS:
        requirements.append(req + "; sys_platform == 'win32'")

elif sys.platform == "darwin":
    for req in requirements_module.DARWIN:
        requirements.append(req + "; sys_platform == 'darwin'")

elif sys.platform == "linux":
    for req in requirements_module.LINUX:
        requirements.append(req + "; sys_platform == 'linux'")


setup(
    name="FreeBodyEngine",
    version='0.08',
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
    install_requires=requirements
)