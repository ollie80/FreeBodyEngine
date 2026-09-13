# Scenes and Nodes

## Services

Almost everything engine-side is a [`Service`][FreeBodyEngine.core.service.Service] -
a singleton fetched by name with [`fb.get_service(name)`][FreeBodyEngine.get_service]
rather than imported directly. A project's entry point registers the ones it
needs (`files`, `renderer`, `graphics`, `window`, `scene_manager`, ...) once,
at startup, in dependency order - see [Getting Started](../getting-started.md#a-minimal-scene)
for a working example. A service can declare `dependencies` on other
service names; registering it before those dependencies are up warns rather
than failing outright.

## Scenes

A [`Scene`][FreeBodyEngine.core.scene.Scene] is a self-contained root of the
node tree - a level, a menu, whatever one `fb.set_scene(name)` should swap
to as a unit. Add scenes up front with `fb.add_scene(...)` and switch
between already-added scenes with `fb.set_scene(name)`; a scene's
`on_initialize()` is where it builds its own node tree (`self.add(...)`)
the first time it's added.

## Nodes

Every object in a scene - sprites, cameras, colliders, tilemaps - is a
[`Node`][FreeBodyEngine.core.node.Node] in a plain parent/child tree rooted
at the scene. `Node2D`/`Node3D` add a `Transform`/`Transform3` (position,
rotation, scale) and a `world_transform` that composes with the parent's,
so a child's transform is always relative to its parent's, all the way up
to the scene root.

Lifecycle hooks a node overrides:

| Hook | Called |
|---|---|
| `on_initialize()` | Once, when the node is added to an initialized parent/scene |
| `on_update()` | Every frame, during the update phase |
| `on_draw()` | Every frame, during the draw phase (2D nodes only - 3D rendering goes through the active [`GraphicsPipeline`][FreeBodyEngine.graphics.pipeline.GraphicsPipeline] instead) |

A node can require a specific parent type (`parental_requirement`) or
specific child types (`requirements`) - both just warn, rather than
prevent construction, if unmet.

## Cameras

[`Camera2D`][FreeBodyEngine.core.camera.Camera2D] and
[`Camera3D`][FreeBodyEngine.core.camera.Camera3D] are nodes like any
other (added to the tree, positioned via the normal transform) whose only
job is producing `view_matrix`/`proj_matrix` for whichever pipeline reads
`scene.camera` - set `scene.camera = my_camera` after adding it, or nothing
draws.

## Update order

Per-frame work runs in fixed phases (see
[`UpdatePhase`][FreeBodyEngine.core.update.UpdatePhase]): `EARLY`,
`PHYSICS`, `UPDATE`, `DRAW`, `LATE`. A node's own `on_update()` runs in the
`UPDATE` phase; a service (or anything else) that needs to hook a specific
phase directly calls
[`fb.register_service_update(phase, callback)`][FreeBodyEngine.register_service_update].
`LATE` in particular runs after the active `GraphicsPipeline`'s own `DRAW`-
phase render, which is the hook point for anything that needs to
post-process or overlay on top of a finished frame.
