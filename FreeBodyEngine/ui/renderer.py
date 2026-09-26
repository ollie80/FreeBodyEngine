from FreeBodyEngine.core.service import Service
from FreeBodyEngine import register_service_update, unregister_service_update, get_service, warning, get_time
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.graphics.mesh import generate_quad
from FreeBodyEngine.math import Transform, Vector
from FreeBodyEngine.core.camera import Camera, CAMERA_PROJECTION
from FreeBodyEngine.graphics.color import Color
from FreeBodyEngine.core.files import load_file
from FreeBodyEngine.ui.element import ElementStates
from FreeBodyEngine.graphics.material import BlendMode
from FreeBodyEngine.graphics.framebuffer import AttachmentType, AttachmentFormat
import numpy as np
import math

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeBodyEngine.ui import UIManager
    from FreeBodyEngine.ui.element import UIElement
    from FreeBodyEngine.graphics.material import Material

class UIRenderer(Service):
    """Engine service that draws the UI tree owned by the `ui` service (`UIManager`)."""

    def __init__(self):
        """Loads the shared background quad mesh/material used to draw every element."""
        super().__init__('ui_renderer')
        self.dependencies.append('ui')

        self.quad = generate_quad()

        self.material: 'Material' = load_file('engine://ui/element.fbmat')

        # Batched counterpart to self.material, for backgrounds with no
        # image - see _draw_background/_flush_instances. Untextured
        # backgrounds are the overwhelming majority of what UIRenderer
        # draws (layout wrappers, panels, buttons, cards, ...), and real
        # cProfile data showed set_uniform() (paid 8x per element, once
        # per draw_mesh()) as the single largest remaining cost in
        # UIRenderer.draw() - this trades per-element uniform-setting for
        # one instance-buffer upload per batch instead.
        self.instanced_material: 'Material' = load_file('engine://ui/element_instanced.fbmat')

        # Queued (rect, border_radius, border_width, border_color,
        # base_color) tuples for the batch currently being built - flushed
        # (see _flush_instances) whenever something that must draw
        # in-between needs to happen first: this element's own text, a
        # scissor change, or a textured background - never reordered,
        # just deferred, so paint order comes out identical to drawing
        # everything immediately would have.
        self._pending_instances: list = []

        # Keyed by the raw `image` style path - a background image (e.g. an
        # avatar) is loaded once and reused every frame/every element that
        # references the same path, the same way resolve_font() caches
        # fonts. Goes through load_file() so plain sprite .png assets that
        # already live in the shared sprite atlas are looked up there
        # instead of duplicated as a second standalone texture.
        self._image_cache: dict[str, any] = {}

        # The scissor rect (x, y, width, height) currently bound on the GPU,
        # or None for unclipped - tracked so _apply_scissor only issues a
        # real set_scissor/clear_scissor call when it's actually changing,
        # rather than once per element regardless of whether it moved.
        self._active_scissor = None

        # Both re-cached at the top of every draw() call (see its own
        # comment) - never read before the first draw() sets them for real.
        self._renderer = None
        self._scale = 1.0
        self._text_renderer = None

        # Damage-tracking (see draw()'s own docs): everything now draws
        # into this persistent offscreen layer instead of straight onto
        # the screen, so a frame where nothing changed can just
        # re-composite it instead of redrawing anything. Created lazily
        # by _ensure_ui_framebuffer() the first time draw() runs, once the
        # window's real size is known - None until then.
        self._ui_framebuffer = None

        # Set whenever _ui_framebuffer is (re)created (first use, or a
        # resize) and consumed by the next draw(), which treats it as "the
        # whole window is dirty" rather than trusting the per-element diff
        # (_compute_dirty_rect) - a fresh/resized framebuffer's contents
        # are undefined everywhere, not just wherever signatures differ
        # from last frame.
        self._force_full_repaint = True

        # The bounding rect of everything _compute_dirty_rect found
        # changed this frame, or None if nothing did - recomputed at the
        # top of every draw() and consumed by it; never read across
        # frames. A single bounding rect, not a precise dirty region list
        # - see _mark_dirty's own docstring for why.
        self._dirty_rect = None

        # What self.ui.root.children looked like (by child identity/order)
        # last frame - compared
        # directly in draw() (not by recursing into _compute_dirty_rect,
        # which only ever visits *children* of root) since nothing else
        # notices a top-level view/screen being swapped out wholesale.
        self._prev_root_children: tuple = None

        # The offscreen layer's own compositor - a fixed NDC-spanning quad
        # (mirrors PBRPipeline._composite_quad exactly) and a minimal
        # shader that just samples it, drawn once per frame in
        # _composite_ui_layer regardless of how much of the layer this
        # frame actually redrew.
        self._composite_material: 'Material' = load_file('engine://ui/ui_composite.fbmat')
        self._composite_quad = generate_quad(2.0, 2.0)

        # Cached wrapper for _ui_framebuffer's color attachment (see
        # _composite_ui_layer) - None until the framebuffer exists, and
        # invalidated back to None by _ensure_ui_framebuffer whenever that
        # attachment's real GL texture is recreated (initial creation,
        # every resize).
        self._ui_layer_texture = None

    def on_initialize(self):
        """Registers the draw callback and grabs a reference to the `ui` service's tree."""
        register_service_update(UpdatePhase.DRAW, self.draw)
        self.ui: 'UIManager' = get_service('ui')

    def on_destroy(self):
        """Unregisters the draw callback registered in `on_initialize`."""
        unregister_service_update(UpdatePhase.DRAW, self.draw)

    def draw(self):
        """Draws every top-level element of the UI tree (and, recursively, their children).

        Depth testing is explicitly turned off first, then back on after -
        nothing here ever did this before, so the UI silently inherited
        whatever depth-test state the 3D pipeline (PBRPipeline) happened to
        leave behind (on for its opaque/lighting passes - see
        graphics/pbr/pipeline.py - off only during its own composite step).
        Every UI element's background and text share the same mesh, drawn
        at the same implicit depth, in the same frame's depth buffer as
        whatever 3D content came before - with depth testing left on and
        GL's default depth func (GL_LESS), a background quad writes a
        depth value that its own text quad, drawn microseconds later at
        that identical depth, then fails to beat ("less than", not
        "less-or-equal") - so the text silently doesn't draw. Which
        specific elements this hits depends on incidental depth-buffer
        contents from whatever 3D drawing happened to precede them that
        frame, which is exactly the "some buttons show their label, some
        don't, no obvious pattern" bug this fixes. A 2D overlay drawn last
        in painter's-algorithm order (later siblings on top - see
        _draw_element's docs) was never supposed to depend on the depth
        buffer at all.

        Blend mode gets the same explicit treatment, for the same reason:
        neither this nor a background/text element's own material (see
        element.fbfrag/text.fbfrag - both compute a real per-pixel alpha
        meant to be blended, not discarded) ever enabled blending itself,
        so every element has always relied on inheriting GL_BLEND enabled
        from whatever the 3D pipeline left behind - which used to be true
        by accident (a Framebuffer created with transparent=True enables
        it once at creation - see GLFramebuffer.__init__ - and nothing
        disabled it for real until Renderer._current_blend_mode's cache
        actually diverged from OPAQUE, which never happened in a project
        with zero BlendMode.TRANSPARENT draws), not by anything here
        actually asking for it - a project that adds its first transparent
        draw call breaks that accident and every element goes solid
        (its real per-pixel alpha applied with no blending to cut it down
        to shape) with no other visible cause.

        Damage-tracking: nothing here draws straight onto the screen
        anymore - it all draws into a persistent offscreen layer
        (self._ui_framebuffer), and only the part of that layer covered by
        this frame's dirty rect (see _compute_dirty_rect/_mark_dirty) gets
        cleared and redrawn; whatever's already there for the rest of it
        is last frame's still-correct pixels. The layer then gets
        composited onto the real target once, every frame, regardless of
        how much of it actually changed - see _composite_ui_layer. On a
        screen where nothing changed at all (dirty rect is None) this
        skips the entire tree walk and just re-composites.

        Whatever's bound as the draw target when this starts is not
        assumed to be the window's own default framebuffer - a project's
        active graphics pipeline may have left something else bound on
        purpose for UI to draw into (PBRPipeline's main_framebuffer; more
        drastically, phonon's own VisualizerPipeline/FramePresenter, which
        renders the *entire app* - itself and every UI element on top of
        it - into a ping-pong framebuffer it swaps every frame, then blits
        that to the window itself in a later, separate pass). Captured
        once here (get_active_framebuffer) and explicitly restored
        (bind_active_framebuffer) after this draw's own offscreen layer
        is done being bound to - never a bare "go back to the default
        framebuffer" assumption, which would silently draw every frame's
        UI onto a surface nothing else ever presents."""
        renderer = get_service('renderer')
        self._renderer = renderer  # see _draw_background/_draw_text's own comments on why this is cached for the draw
        target_framebuffer = renderer.get_active_framebuffer()
        renderer.disable_depth_testing()
        renderer.set_blend_mode(BlendMode.TRANSPARENT)

        # window_size and content_scale are both per-frame constants (the
        # window doesn't resize mid-draw), not per-element ones - real
        # cProfile data (chasing the ~13-14ms/frame UIRenderer.draw() cost)
        # showed _draw_background/_draw_text recomputing both, every single
        # element, adding up to real, wasted per-frame cost: content_scale
        # alone (a service lookup + property getter) cost ~0.78ms/frame
        # across ~10,600 elements on a realistic page, and re-setting the
        # already-unchanged window_size uniform ~10,600 times paid its
        # Python-level call/cache-compare overhead for a value the cache
        # was always going to reject as unchanged anyway. Computed once
        # here and threaded through _draw_element instead.
        scale = self._content_scale()
        self._scale = scale
        self._text_renderer = get_service('text_renderer')
        width, height = self.ui.root.width, self.ui.root.height
        self.material.shader.set_uniform('window_size', (width, height))
        self.instanced_material.shader.set_uniform('window_size', (width, height))

        self._ensure_ui_framebuffer(int(width), int(height))

        # Seeded with the root's own rect, not None - _draw_element already
        # culls a whole subtree against the nearest scrollable ancestor's
        # scissor, but with no ancestor at all (the overwhelmingly common
        # case - most elements aren't inside an "overflow: auto" container)
        # that scissor was None ("unclipped") all the way to the root, so
        # anything positioned outside the actual visible window - an
        # off-screen-until-animated-in modal/drawer, a row inside a plain
        # (non-scrolling) list taller than the window, anything an anchor/
        # transform pushed past the edge - still drew every frame with
        # nothing to stop it. Starting from the window's own bounds instead
        # gives every element real viewport culling, not just the ones
        # lucky enough to sit inside a scrollable container.
        root_rect = (0.0, 0.0, float(width), float(height))

        # A top-level view/screen being swapped out wholesale (_show_view
        # in a project like phonon, say) is the one structural change
        # _compute_dirty_rect's own child-set check can't see - it only
        # ever recurses into root's *children*, never root itself. Caught
        # here instead: if the top-level child set differs at all, the
        # safe/simple move is to dirty the entire window, not try to work
        # out which particular screen used to occupy which particular
        # rect.
        # id(), not the child objects themselves - .children is a fresh
        # view each read (a real dict in the pure-Python backend, a
        # _ChildrenView wrapping a live C++ node in the native one - see
        # ui/native_element.py's own docstring), but the child objects it
        # yields have stable identity either way, which is all a "did the
        # set/order of children change" check actually needs. Also why
        # this can't just be `.keys()` - the native view has no keys at
        # all, only positional children.
        root_children = tuple(id(c) for c in self.ui.root.children.values())
        if root_children != self._prev_root_children:
            self._mark_dirty(root_rect)
        self._prev_root_children = root_children

        self._dirty_rect = None
        for element in self.ui.root.children.values():
            self._compute_dirty_rect(element, root_rect)

        if self._force_full_repaint:
            self._dirty_rect = root_rect
            self._force_full_repaint = False

        if self._dirty_rect is not None:
            # Snapped outward to whole pixels - glScissor truncates to ints,
            # so a fractional dirty rect would otherwise clear (and clip the
            # redraw to) a region up to a pixel short of what changed,
            # leaving a stale sliver at its right/bottom edge.
            x, y, w, h = self._dirty_rect
            x0, y0 = max(0, math.floor(x)), max(0, math.floor(y))
            x1, y1 = min(int(width), math.ceil(x + w)), min(int(height), math.ceil(y + h))
            self._dirty_rect = (float(x0), float(y0), float(max(0, x1 - x0)), float(max(0, y1 - y0)))

            self._ui_framebuffer.bind()
            try:
                # Scissor-clear just the dirty region before redrawing it -
                # everything outside it must survive untouched, which is the
                # entire point of only repainting what changed. Goes through
                # _apply_scissor (not a raw renderer.set_scissor call) so its
                # _active_scissor cache - and therefore every scissor check
                # _draw_element makes during the walk right after - stays
                # accurate.
                self._apply_scissor(self._dirty_rect)
                renderer.clear(Color((0.0, 0.0, 0.0, 0.0)))

                # Seeded with the dirty rect, not root_rect, so every draw in
                # this pass is scissored to it. An element that only partly
                # overlaps the dirty rect still gets redrawn in full, and
                # without this its background would paint over the
                # uncleared pixels outside the dirty rect - wiping out
                # children/siblings there that the cull in _draw_element
                # (correctly) skips redrawing. That's what erased phonon's
                # top bar: the full-window main panel behind it redrew
                # whenever anything in the content area changed.
                for element in self.ui.root.children.values():
                    self._draw_element(element, self._dirty_rect)
                self._flush_instances()  # catches whatever the last element(s) queued and never got flushed by a later text draw/scissor change
                self._flush_text()  # same, for whatever text queue_text() queued and never got flushed by a later background/scissor change
            except Exception:
                # _compute_dirty_rect already recorded this frame's
                # signatures, so a redraw that dies partway through would
                # otherwise leave the layer permanently wrong for whatever
                # it didn't get to - nothing would ever look "changed" again.
                self._force_full_repaint = True
                raise
            finally:
                self._apply_scissor(None)

                # NOT self._ui_framebuffer.unbind() - that hardcodes "go back
                # to the window's own default framebuffer", which is wrong
                # whenever a pipeline left something else bound for UI to draw
                # into (see draw()'s own docstring on target_framebuffer).
                # This puts back the *actual* target this draw() started with.
                renderer.bind_active_framebuffer(target_framebuffer)

        self._composite_ui_layer(width, height)

        renderer.set_blend_mode(BlendMode.OPAQUE)
        renderer.enable_depth_testing()

    def _ensure_ui_framebuffer(self, width: int, height: int):
        """(Re)creates the offscreen layer everything draws into (see
        draw()'s own docs) at (width, height) - the first time this runs,
        and again whenever the window's size changes. Either way,
        whatever was in it before is gone: a fresh/resized framebuffer's
        contents are undefined, not "still correct for whatever part
        didn't change" - so this always forces the next redraw to repaint
        the whole window (_force_full_repaint), regardless of what the
        per-element diff in _compute_dirty_rect finds."""
        fb = self._ui_framebuffer
        if fb is not None and fb.width == width and fb.height == height:
            return

        if fb is None:
            self._ui_framebuffer = self._renderer.create_framebuffer(
                width, height, {'color': (AttachmentType.COLOR, AttachmentFormat.RGBA8)},
            )
        else:
            fb.resize((width, height))

        # A resize (GL44Framebuffer.resize) deletes and recreates the
        # color attachment's real GL texture under the same Python
        # Framebuffer object - the *id* wrap_external_texture wrapped
        # last time now points at a dead texture. Clearing the cache here
        # forces _composite_ui_layer to wrap the new one instead of
        # reusing a stale wrapper.
        self._ui_layer_texture = None

        self._force_full_repaint = True

    def _composite_ui_layer(self, width: float, height: float):
        """Draws the offscreen UI layer onto the real target as one
        alpha-blended fullscreen quad, every frame, regardless of how much
        of the layer this frame's redraw (if any) actually touched -
        mirrors PBRPipeline._draw_composite's own G-buffer round trip
        (generate_quad(2.0, 2.0) spanning NDC -1..1 directly, a vertex
        shader that passes vertex/uv straight through, no model/view/proj
        at all - see ui_composite.fbvert's own docstring for why this
        doesn't reuse element.fbvert's per-element image_uv mapping
        instead). Wraps the layer's color attachment exactly once (cached
        in self._ui_layer_texture, invalidated by _ensure_ui_framebuffer
        whenever the real GL texture underneath actually changes) instead
        of on every call - wrap_external_texture hands back a fresh
        Texture wrapper (and a fresh entry in the texture manager's own
        standalone-texture table) each time it's called, and this runs
        every single frame forever, so re-wrapping here was leaking one
        of each, unbounded, for the life of the app."""
        if self._ui_layer_texture is None:
            texture_manager = self._renderer.texture_manager
            gl_texture = self._ui_framebuffer.get_attachment_texture('color')
            self._ui_layer_texture = texture_manager.wrap_external_texture(gl_texture)

        self._composite_material.shader.set_uniform('ui_layer', self._ui_layer_texture)
        self._renderer.draw_mesh(self._composite_quad, self._composite_material)

    @staticmethod
    def _rect_outside(rect: tuple, bound: tuple) -> bool:
        """True if `rect` (x, y, width, height) has no overlap with
        `bound` at all - the shared disjoint-rectangles test behind every
        "this element or its whole subtree is definitely invisible right
        now" cull in this file (an inherited overflow scissor, this
        frame's dirty rect)."""
        x, y, w, h = rect
        bx, by, bw, bh = bound
        return x >= bx + bw or x + w <= bx or y >= by + bh or y + h <= by

    def _mark_dirty(self, rect: tuple):
        """Unions `rect` into self._dirty_rect - the running bounding box
        of everything _compute_dirty_rect has found changed so far this
        frame (see draw()). A single bounding rect, not a precise dirty
        region list: scattered unrelated changes end up over-redrawing
        whatever sits between them, but that trade buys a single
        scissor/clear/cull instead of tracking and re-testing against an
        unbounded list of disjoint rects for every element, every frame."""
        if rect[2] <= 0 or rect[3] <= 0:
            return
        if self._dirty_rect is None:
            self._dirty_rect = rect
            return
        x, y, w, h = self._dirty_rect
        rx, ry, rw, rh = rect
        x2 = max(x + w, rx + rw)
        y2 = max(y + h, ry + rh)
        nx = min(x, rx)
        ny = min(y, ry)
        self._dirty_rect = (nx, ny, x2 - nx, y2 - ny)

    def _invalidate_subtree(self, element: 'UIElement'):
        """Clears element._ui_prev_signature (and recursively, every
        descendant's) so the next time anything in this subtree is
        actually visited by _compute_dirty_rect, it's unconditionally
        treated as new/changed - see the cull branch in
        _compute_dirty_rect for why a culled subtree can't just leave its
        old signature in place. Deliberately does none of the real diff's
        work (no get_current_styles(), no rect/scissor math) - it only
        ever needs to blank one attribute per node.

        Also blanks _ui_prev_rect, not just _ui_prev_signature: the cull
        branch that calls this already dirtied that old rect once (see
        its own comment on why) - leaving prev_rect in place would make
        it look, to next frame's cull branch, like this element *just*
        went from visible to hidden all over again, re-dirtying the same
        already-handled rect every single frame for as long as it stays
        off-screen."""
        element._ui_prev_signature = None
        element._ui_prev_rect = None
        for child in element.children.values():
            self._invalidate_subtree(child)

    def _compute_dirty_rect(self, element: 'UIElement', scissor: tuple):
        """The diff half of draw()'s damage-tracking scheme: walks the
        tree the same way _draw_element does (same cull, same
        overflow-scissor propagation into children) but draws nothing -
        it compares each element's current (layout rect, inherited
        scissor, resolved styles, cursor/text-scroll state, cursor-blink
        phase, child-key set) against whatever was stored the last time
        this ran, and folds the union of its old+new rect into
        self._dirty_rect (via _mark_dirty) wherever they differ, or the
        element is new, or its child set changed (see _draw_element's own
        docs on why a changed child set dirties *this* element's rect
        rather than trying to track a removed child's own rect directly -
        every child lives within its parent's bounds, so this covers
        wherever a removed child used to draw without needing to notice
        the removal itself).

        Runs unconditionally, every frame, over the whole (culled) tree -
        the cost is real (one get_current_styles() per visited element,
        same as _draw_element already pays for every element it draws),
        but it's what makes skipping the *expensive* half - background/
        text draw calls, GPU buffer uploads - possible for everything that
        didn't actually change."""
        layout = element._layout
        rect = (layout.x, layout.y, layout.width, layout.height)

        if scissor is not None and layout.width > 0 and layout.height > 0 and self._rect_outside(rect, scissor):
            # Culled - the redraw pass (_draw_element) will skip this
            # exact same subtree for the exact same reason, so nothing in
            # it is getting drawn (or kept correctly painted) this frame.
            #
            # If it was visible last time this ran (a real prev_rect on
            # file, not just missing), its *old* on-screen position still
            # has real pixels baked into the offscreen layer from back
            # then - a scrolled list is the obvious case, a row sliding
            # from "in view" to "off the top" this very frame - and
            # nothing else is going to clear them: unlike normal sibling
            # reflow (where whatever now occupies that space repaints it
            # as part of its own change), an ancestor's scissor simply
            # hiding this element doesn't touch the pixels it already
            # left behind. Dirtying prev_rect here is what makes the
            # clear+redraw pass wipe them instead of leaving a stale
            # ghost of wherever this used to be, forever.
            prev_rect = getattr(element, '_ui_prev_rect', None)
            if prev_rect is not None:
                self._mark_dirty(prev_rect)

            # Its stored signature has to be invalidated too, recursively,
            # not just left as whatever it was: leaving it intact would
            # mean that if this subtree becomes visible again later
            # (scrolled back into view, say) with *unchanged* content, the
            # next diff would see a matching signature and conclude "no
            # repaint needed" - even though its pixels were never actually
            # drawn into the offscreen layer for however long it's been
            # culled, and are either stale or were never there at all.
            # Cheap (no get_current_styles(), no rect math) since it's
            # just clearing one attribute per node, not the full diff.
            self._invalidate_subtree(element)
            return

        styles = element.get_current_styles()
        show_cursor = styles.get('editable', False) and element.state == ElementStates.FOCUSED
        blink_phase = (int(get_time() * 2) % 2) if show_cursor else None

        signature = (
            rect, scissor, styles,
            element._cursor_index, element._text_view_offset, blink_phase,
            # By identity, not `.keys()` - see draw()'s own comment on
            # root_children for why (the native backend's _ChildrenView
            # has no keys at all).
            tuple(id(c) for c in element.children.values()),
        )

        prev_signature = getattr(element, '_ui_prev_signature', None)
        prev_rect = getattr(element, '_ui_prev_rect', None)
        element._ui_prev_signature = signature
        element._ui_prev_rect = rect

        if signature != prev_signature:
            self._mark_dirty(rect)
            if prev_rect is not None:
                self._mark_dirty(prev_rect)

        child_scissor = scissor
        if element.get_overflow(styles) != "visible":
            child_scissor = self._intersect_rect(scissor, rect) if scissor is not None else rect

        for child in element.children.values():
            self._compute_dirty_rect(child, child_scissor)

    @staticmethod
    def _intersect_rect(a: tuple, b: tuple) -> tuple:
        """Intersection of two (x, y, width, height) rects, clamped to a
        non-negative width/height (an empty intersection, not a negative one)."""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x = max(ax, bx)
        y = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        return (x, y, max(0.0, x2 - x), max(0.0, y2 - y))

    def _apply_scissor(self, rect: tuple):
        """Binds `rect` as the active GPU scissor (or clears it for `None`),
        skipping the actual renderer call if it's already what's bound."""
        if rect == self._active_scissor:
            return

        # A pending batch was queued expecting the scissor bound *right
        # now* to still be in effect when it actually draws - it has to
        # go out under that scissor, before this call changes it to
        # something else. Both queues, not just backgrounds - queued text
        # (see queue_text()) is exactly as scissor-sensitive.
        self._flush_instances()
        self._flush_text()

        self._active_scissor = rect
        renderer = self._renderer

        if rect is None:
            renderer.clear_scissor()
        else:
            renderer.set_scissor(*rect)

    def _draw_element(self, element: 'UIElement', scissor: tuple):
        """Draws one element's background/text, then recurses into its own
        children - UIElement.calculate_layout() already computes correct
        layouts for arbitrarily nested trees (see ui/element.py), but until
        now this only ever drew direct children of the root, so nothing
        composed of nested elements (an avatar + bubble inside a message
        row, say) ever actually rendered past its top-level container.

        `scissor` is the (x, y, width, height) clip rect inherited from the
        nearest ancestor whose overflow isn't "visible" (see ui/element.py's
        OVERFLOW docs), or None if there isn't one. An element entirely outside it is skipped
        along with its whole subtree - nothing under a scrolled-out-of-view
        row can be visible either, so this also caps how much of an
        offscreen subtree gets a draw call, not just its own background/
        text. (Full virtualization - skipping *layout*, not just drawing,
        for offscreen rows - is a further improvement, not this one.)

        The "outside the scissor rect" test only applies when this element
        itself has a real (positive) width and height. A zero-size element
        is not the same thing as an off-screen one: a plain layout wrapper
        with no explicit height (see ui/element.py's "auto" size docs -
        before that existed, *every* such wrapper defaulted to height 0
        from DEFAULT_STYLES) reports zero size for itself while still
        having children with their own real, independent geometry
        (fixed-pixel row heights inside it, say). Treating "zero size" as
        "fully clipped, skip the whole subtree" - what this used to do -
        discarded every one of those children's draw calls along with it,
        silently: a search-results list, or any dynamically-populated
        container built the obvious way (an unsized wrapper around rows
        added later), rendered nothing at all despite every row existing
        in the tree with the right text and a valid size of its own."""
        layout = element._layout
        rect = (layout.x, layout.y, layout.width, layout.height)

        if layout.width > 0 and layout.height > 0:
            if scissor is not None and self._rect_outside(rect, scissor):
                return
            # This frame's redraw only ever touches self._dirty_rect (see
            # draw()) - an element entirely outside it wasn't part of
            # whatever changed, so its pixels in the offscreen layer are
            # already correct from a previous frame and don't need
            # (indeed, by construction, since only the dirty rect got
            # scissor-cleared, don't get another chance to) redraw here.
            if self._rect_outside(rect, self._dirty_rect):
                return

        self._apply_scissor(scissor)

        styles = element.get_current_styles()

        self._draw_background(element, styles)

        # A pending batch of queued backgrounds must draw *before* this
        # element's own text - both backgrounds and text are batched now
        # (see queue_text()/_flush_text and _pending_instances/
        # _flush_instances), so if there's anything queued in the
        # background channel (this element's own background just got
        # added to it, or an earlier sibling's did) it has to flush now or
        # the text would end up painted first, with the background drawn
        # over it a moment later. Mirrors _draw_text's own early-bail
        # condition so a text-less element (the common case - most nodes
        # are plain layout wrappers) doesn't force a flush for nothing.
        #
        # The two batches never both hold pending work at once - see
        # _draw_background's own flush-the-other-channel call, which
        # keeps this symmetric in the other direction (queuing a new
        # background flushes any pending text first) - so which one gets
        # flushed first here, or at the end of draw()/on a scissor change,
        # never actually matters for paint order.
        show_cursor = styles.get('editable', False) and element.state == ElementStates.FOCUSED
        if styles.get('font') is not None and (styles.get('text') or show_cursor):
            self._flush_instances()

        self._draw_text(element, styles)

        child_scissor = scissor
        if element.get_overflow(styles) != "visible":
            child_scissor = self._intersect_rect(scissor, rect) if scissor is not None else rect

        for child in element.children.values():
            self._draw_element(child, child_scissor)

    @staticmethod
    def _to_vec4(value) -> tuple:
        """border_radius/border_width are single numbers in the common
        case (one radius/thickness for every corner/edge) but the shader
        takes a vec4 (per-corner radius in top_left/top_right/bottom_right/
        bottom_left order, matching CSS) so asymmetric shapes - like an
        Instagram-style bubble with one flattened corner on its "tail"
        side - are just a 4-tuple instead of a new style."""
        if isinstance(value, (tuple, list)):
            if len(value) == 4:
                return tuple(float(v) for v in value)
            warning(f'Expected 4 values for a per-corner/per-edge style, got {value!r}.')
            return (0.0, 0.0, 0.0, 0.0)
        return (float(value),) * 4

    def _content_scale(self) -> float:
        """See Window.content_scale's docstring. Every plain-pixel style
        this renderer reads directly from `styles` (border_radius/width,
        font_size, padding*) bypasses ui/element.py's _parse_size - which
        is where content_scale normally gets applied - so each read here
        has to scale itself to stay consistent with the already-scaled
        box _draw_background/_draw_text are drawing into; skipping this
        would draw correctly-scaled boxes with unscaled (and therefore,
        on any non-1.0-scale display, wrongly offset/sized) borders and
        text inside them."""
        window = get_service('window')
        return window.content_scale if window is not None else 1.0

    def _resolve_image(self, path: str):
        cached = self._image_cache.get(path)
        if cached is not None:
            return cached

        texture = load_file(path)
        if texture is not None:
            self._image_cache[path] = texture
        return texture

    def _draw_background(self, element: 'UIElement', styles: dict):
        width, height = element._layout.width, element._layout.height
        if width <= 0 or height <= 0:
            return

        # A pure layout wrapper (a row/column that only exists to
        # position its children - the overwhelming majority of nodes in
        # a typical UI tree, e.g. every `UIElement(None, styles={"layout":
        # "horizontal", ...})` that never sets its own base_color) draws
        # nothing visible at all: DEFAULT_STYLES' own base_color is fully
        # transparent (0,0,0,0) specifically so a layout-only element
        # doesn't render as a surprise solid box. This used to still pay
        # 8 real set_uniform() calls plus a full draw_mesh() for that
        # literal no-op every single frame - real profiling (FreeBodyEngine
        # .core.perf_profiler) showed _draw_background as the single
        # largest remaining cost in UIRenderer.draw() even after batching
        # text - most of it spent on elements with nothing to actually
        # draw. Skipped here instead, before any of that work starts,
        # whenever there's truly nothing that would be visible: fully
        # transparent base_color, no border on any edge, and no
        # background image.
        base_color = styles.get('base_color', (1.0, 1.0, 1.0, 1.0))
        has_border = any(v != 0 for v in self._to_vec4(styles.get('border_width', 0)))
        has_image = bool(styles.get('image'))
        if base_color[3] == 0 and not has_border and not has_image:
            return

        if has_image:
            # Can't be batched - element_instanced.fbvert/.fbfrag have no
            # texture-sampling path at all (see their own docstrings), so
            # this small minority of backgrounds (avatars, cover art, ...)
            # still goes through the original single-element material/
            # draw_mesh() path. Flushes both channels first so it draws in
            # the right place relative to whatever's already queued in
            # either - this element comes right after those in tree order,
            # so its own draw call has to happen before anything queued
            # *after* it, not before.
            self._flush_instances()
            self._flush_text()
            self._draw_background_immediate(element, styles, width, height)
            return

        # Flushes any pending text before this new background instance
        # joins the queue - the mirror image of _draw_element's own
        # bg-before-text flush above, and for the same reason: an earlier
        # sibling's text queued but not yet drawn must land on screen
        # before this (possibly opaque) background, or paint order would
        # flip wherever the two happen to overlap. Together the two rules
        # guarantee only one of the two queues ever holds pending work at
        # a time (see _draw_element's own comment on this).
        self._flush_text()

        scale = self._scale
        self._pending_instances.append((
            (element._layout.x, element._layout.y, width, height),
            tuple(v * scale for v in self._to_vec4(styles.get('border_radius', 0))),
            tuple(v * scale for v in self._to_vec4(styles.get('border_width', 0))),
            styles.get('border_color', (0.0, 0.0, 0.0, 1.0)),
            base_color,
        ))

    def _draw_background_immediate(self, element: 'UIElement', styles: dict, width: float, height: float):
        """The original, single-element background draw - used only for a
        background with an `image` style (see _draw_background), where
        batching doesn't apply."""
        shader = self.material.shader
        shader.set_uniform('rect', (element._layout.x, element._layout.y, width, height))
        shader.set_uniform('size', (float(width), float(height)))
        scale = self._scale
        shader.set_uniform('border_radius', tuple(v * scale for v in self._to_vec4(styles.get('border_radius', 0))))
        shader.set_uniform('border_width', tuple(v * scale for v in self._to_vec4(styles.get('border_width', 0))))
        shader.set_uniform('border_color', styles.get('border_color', (0.0, 0.0, 0.0, 1.0)))
        shader.set_uniform('base_color', styles.get('base_color', (1.0, 1.0, 1.0, 1.0)))

        image_path = styles.get('image')
        texture = self._resolve_image(image_path) if image_path else None
        shader.set_uniform('use_texture', texture is not None)
        if texture is not None:
            shader.set_uniform('background_texture', texture)

        self._renderer.draw_mesh(self.quad, self.material)

    def _flush_instances(self):
        """Draws every currently-queued background as one instanced draw
        call (see draw_ui_background_instances on both GL renderer
        backends) and clears the queue. A no-op when nothing's queued -
        called defensively from several places (a scissor change, before
        any element's text, at the end of draw()) that don't know or care
        whether anything is actually pending."""
        if not self._pending_instances:
            return

        n = len(self._pending_instances)
        data = np.empty((n, 20), dtype=np.float32)
        for i, (rect, border_radius, border_width, border_color, base_color) in enumerate(self._pending_instances):
            data[i, 0:4] = rect
            data[i, 4:8] = border_radius
            data[i, 8:12] = border_width
            data[i, 12:16] = border_color
            data[i, 16:20] = base_color
        self._pending_instances.clear()

        self._renderer.draw_ui_background_instances(self.quad, self.instanced_material, data)

    def _flush_text(self):
        """Thin wrapper around TextRenderer.flush() - see its own
        docstring for what actually gets batched and why. Kept as its own
        method (rather than calling self._text_renderer.flush() directly
        at every call site) purely so every flush point in this file reads
        the same way regardless of which queue it's draining."""
        self._text_renderer.flush()

    def _draw_text(self, element: 'UIElement', styles: dict):
        text = styles.get('text') or ''
        font_path = styles.get('font')

        # A focused, editable field still needs its caret drawn even with
        # no text yet (an empty search box you've just clicked into is the
        # most common case) - so this can't bail out just because `text`
        # is empty the way it used to; only a missing font (nothing at all
        # could be drawn) or "neither text nor a cursor to draw" bails.
        show_cursor = styles.get('editable', False) and element.state == ElementStates.FOCUSED
        if font_path is None or (not text and not show_cursor):
            return

        # Masking happens here, drawing-only - get_current_styles()["text"]
        # (what the "submit" callback receives, what add_playlist_track()
        # etc. would actually send) still carries the real value; only the
        # glyphs drawn to screen are replaced.
        if styles.get('secret', False):
            text = '•' * len(text)

        from FreeBodyEngine.core.files.loaders.font import resolve_font  # lazy - avoids a ui <-> core.files import cycle (utils.py imports ui.element early during core.files' own init)
        font = resolve_font(font_path, weight=styles.get('font_weight', 'regular'))
        if font is None:
            return

        scale = self._scale
        font_size = styles.get('font_size', 24) * scale
        pad = styles.get('padding', 0)
        pad_left = styles.get('padding_left', pad) * scale
        pad_right = styles.get('padding_right', pad) * scale
        pad_top = styles.get('padding_top', pad) * scale
        pad_bottom = styles.get('padding_bottom', pad) * scale

        text_renderer = self._text_renderer
        editable = styles.get('editable', False)

        # Elements have a fixed pixel width/height (or one resolved from a
        # percentage - see UIElement._parse_size), so text longer than
        # that would otherwise just overflow past the element's edge with
        # nothing to stop it (draw_text has no concept of a bound to stop
        # at). An editable field scrolls horizontally to keep the cursor
        # in view instead - the right call for something you're actively
        # typing into (eliding the *end* with "..." would hide what you
        # just typed the moment a search query got long); every other
        # element keeps eliding with an ellipsis, same as before.
        available_width = element._layout.width - pad_left - pad_right
        draw_x = element._layout.x + pad_left
        clip_rect = None

        # Clamped here (not just wherever it's mutated in manager.py) so a
        # cursor left past the end of shorter text - the field's own text
        # was set programmatically out from under it, say - never indexes
        # past the string it's about to be measured against below.
        element._cursor_index = max(0, min(element._cursor_index, len(text)))
        cursor_index = element._cursor_index

        if editable:
            full_width = text_renderer.measure_text(font, text, font_size)
            cursor_px = text_renderer.measure_text(font, text[:cursor_index], font_size)

            view_offset = element._text_view_offset
            if available_width > 0:
                if full_width <= available_width:
                    view_offset = 0.0
                else:
                    if cursor_px - view_offset < 0:
                        view_offset = cursor_px
                    elif cursor_px - view_offset > available_width:
                        view_offset = cursor_px - available_width
                    view_offset = max(0.0, min(view_offset, full_width - available_width))
            element._text_view_offset = view_offset

            draw_x -= view_offset
            if full_width > available_width:
                clip_rect = (element._layout.x + pad_left, element._layout.y, max(0, available_width), element._layout.height)
        elif available_width > 0 and text_renderer.measure_text(font, text, font_size) > available_width:
            ellipsis = '...'
            ellipsis_width = text_renderer.measure_text(font, ellipsis, font_size)
            truncated = text
            while truncated and text_renderer.measure_text(font, truncated, font_size) + ellipsis_width > available_width:
                truncated = truncated[:-1]
            text = (truncated + ellipsis) if truncated else ellipsis

        # Vertically centered in the padded content box using the font's
        # real ascender/descender (not just font_size) - previously this
        # always baseline-aligned to the top (padding_top + font_size),
        # which reads fine for a top-aligned multi-line block but left
        # every single-line label (virtually everything - every button,
        # every row) sitting near the top of its box with visibly more
        # empty space below than above, instead of actually centered.
        content_top = element._layout.y + pad_top
        content_height = max(0, element._layout.height - pad_top - pad_bottom)
        line_height = (font.ascender - font.descender) * font_size
        baseline_y = content_top + (content_height - line_height) / 2 + font.ascender * font_size

        text_color = styles.get('text_color', (1.0, 1.0, 1.0, 1.0))

        # A scrolled/overflowing editable field needs its own clip so the
        # part scrolled "off-screen" doesn't just draw past the field's
        # edge into whatever's next to it - nothing about a plain
        # UIElement clips its own text to its own bounds otherwise (see
        # _draw_element's docs on "overflow" - that's about clipping
        # *children*, not an element's own content). Scoped to just this
        # draw call and restored after, rather than left active, so it
        # doesn't clip whatever's drawn next.
        previous_scissor = self._active_scissor
        if clip_rect is not None:
            new_scissor = self._intersect_rect(previous_scissor, clip_rect) if previous_scissor is not None else clip_rect
            self._apply_scissor(new_scissor)

        if text:
            text_renderer.queue_text(font, text, draw_x, baseline_y, font_size, text_color)

        if show_cursor:
            # Blinks at 1Hz (on for the first half-second of each second,
            # off for the second) - a solid, unblinking caret reads as
            # part of the text ("Search|" looks like a typo), same reason
            # every OS text field blinks its own. Drawn as a plain "|"
            # glyph through the same text pipeline rather than a separate
            # quad, positioned from `cursor_index` (see ui/manager.py's
            # _on_key, which moves/inserts/deletes at it) rather than
            # always trailing the text - the cursor can now sit mid-string,
            # not just at the end.
            if int(get_time() * 2) % 2 == 0:
                cursor_x = draw_x + text_renderer.measure_text(font, text[:cursor_index], font_size)
                text_renderer.queue_text(font, '|', cursor_x, baseline_y, font_size, text_color)

        if clip_rect is not None:
            self._apply_scissor(previous_scissor)
