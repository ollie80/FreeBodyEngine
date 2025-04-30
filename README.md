<a href="https://github.com/ollie80/FreeBodyEngine">
  <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ollie80/FreeBodyEngine/main/engine_assets/logo/FreeBodyTextWhite.png">
  <img alt="logo" src="https://raw.githubusercontent.com/ollie80/FreeBodyEngine/main/engine_assets/logo/FreeBodyBlackWhite.png">
  </picture>
</a>

## WARNING
This engine is **very** early in development, you **will** run into many bugs.

## Requirements
- python
- pygame-ce (if you have the normal version uninstall and install ce)
- moderngl

## Quick Start Guide
First, clone the template repo.

`git clone https://github.com/ollie80/FreeBodyEngineTemplate.git`

Then move to the created directory and clone the engine files.


`cd FreeBodyEngineTemplate`

`git clone https://github.com/ollie80/FreeBodyEngine.git`

## Running and Building
To run your game in dev mode, simply run the `FreeBodyEngine/dev/run.py` file (this will also pass on any flags to you main file).

To build your game, run the `FreeBodyEngine/build/build.py` file, you will then find your executable and assets in the dist folder. 

**WARNING** Always keep the built game files in the same structure or else many of the engine's systems will break.
