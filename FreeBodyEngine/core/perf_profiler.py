"""A live, in-engine performance profiler with a GUI built out of the
engine's own UI system (FreeBodyEngine.ui) - not a separate window or an
external tool, a real HUD overlay any project can drop in.

Usage - register like any other service, after 'ui' already exists:

    fb.register_service(fb.core.perf_profiler.PerformanceProfiler())

Hidden by default; press F3 (configurable via the `toggle_key` argument)
to show/hide it. While hidden, per-callback timing is still collected
(cheap - see UpdateCoordinator.profiling_enabled's own docstring) so the
history graph already has real data the moment it's shown, rather than
needing to warm up first.

Distinct from the existing, much cruder FreeBodyEngine.core.profiler.
Profiler (a whole-process sys.setprofile hook, toggled by the PROFILER
flag, dumping raw per-Python-function-name totals to stdout every single
frame) - that one measures every Python call/return process-wide, which
is both far too fine-grained to read at a glance and heavy enough to
distort the very timings it's measuring. This one instruments exactly
one, deliberately coarser point instead - UpdateCoordinator's own
per-phase callback dispatch (see _run() in core/update.py) - the same
granularity a project's own code actually registers work at
(`register_service_update(UpdatePhase.DRAW, self.draw)`), so what shows
up here ("UIRenderer.draw: 2.1ms") is directly actionable rather than a
few thousand lines of individual method calls to page through.
"""
import os
from collections import deque

from FreeBodyEngine import register_event_callback, register_service_update, unregister_event_callback, unregister_service_update, get_main, get_service
from FreeBodyEngine.core.service import Service
from FreeBodyEngine.core.update import UpdatePhase
from FreeBodyEngine.core.input import Key, KEY_PRESS

# Bundled with the engine itself (engine_assets/font/) rather than
# depending on whatever font a hosting project happens to bundle - this
# HUD has to render something legible even in a brand new project that
# hasn't added a single font of its own yet.
_FONT = "engine://font/JetBrainsMono.ttf"

# How many recent frames the history graph shows - each one gets a fixed-
# width bar, so this also fixes the graph's total width.
_HISTORY_LEN = 90
_BAR_WIDTH = 3
_BAR_GAP = 1
_GRAPH_HEIGHT = 60

# Frame *budget* in milliseconds a bar is considered "on time" under -
# 1000/60, not whatever MAX_FPS is actually configured to, since that's
# the number every player-facing "is this smooth" judgement is actually
# made against regardless of this project's own cap.
_BUDGET_MS = 1000.0 / 60.0

# How many of the slowest callbacks to actually list - unbounded would
# make the breakdown panel grow without limit on a scene with a great
# many registered callbacks, most of which cost a negligible fraction of
# a millisecond and aren't worth a whole row of screen space.
_BREAKDOWN_ROWS = 12


class PerformanceProfiler(Service):
    """See this module's own docstring. Depends on 'ui' (must be
    registered first) since its HUD is built from real UIElements."""

    def __init__(self, toggle_key: Key = Key.F3):
        super().__init__('perf_profiler')
        self.dependencies = ['ui']
        self.toggle_key = toggle_key
        self.visible = False

        # (label, total_seconds_this_frame) - kept as a flat list across
        # every phase, not split by phase, since the breakdown panel
        # ranks by cost regardless of which phase something ran in.
        self.history: deque[float] = deque(maxlen=_HISTORY_LEN)

        self._panel = None
        self._fps_label = None
        self._graph_bars: list = []
        self._breakdown = None

    def on_initialize(self):
        register_event_callback(KEY_PRESS, self._on_key)
        # Low priority (runs last among LATE callbacks) so every other
        # LATE callback's own timing is already in last_frame_timings by
        # the time this reads it - see UpdateCoordinator.update()'s own
        # comment on exactly what's visible and when.
        register_service_update(UpdatePhase.LATE, self.update, priority=-1000)
        get_main().updater.profiling_enabled = True
        self._build_ui()

    def on_destroy(self):
        unregister_event_callback(KEY_PRESS, self._on_key)
        unregister_service_update(UpdatePhase.LATE, self.update)
        get_main().updater.profiling_enabled = False
        if self.visible and self._panel is not None:
            get_service('ui').remove(self._panel)

    def _on_key(self, key: Key):
        if key != self.toggle_key:
            return
        self.visible = not self.visible
        ui = get_service('ui')
        if self.visible:
            ui.add(self._panel)
        else:
            ui.remove(self._panel)

    # -- UI construction (built once; refreshed in place every frame) ------

    def _build_ui(self):
        from FreeBodyEngine.ui import UIElement

        label_style = {
            "font": _FONT, "font_size": 13, "text_color": (0.1, 1.0, 0.4, 1.0),
            "width": "100w", "height": 16,
        }

        self._panel = UIElement("perf_profiler", styles={
            "parent_anchor": "top_left", "anchor": "top_left", "x": 8, "y": 8,
            "width": (_HISTORY_LEN * (_BAR_WIDTH + _BAR_GAP)) + 16, "height": "auto",
            "layout": "vertical", "gap": 4, "padding": 8,
            "base_color": (0.0, 0.0, 0.0, 0.72),
        })

        self._fps_label = UIElement(None, styles={**label_style, "text": "..."})
        self._panel.add(self._fps_label)

        graph = UIElement(None, styles={
            "width": "100w", "height": _GRAPH_HEIGHT, "layout": "horizontal", "gap": _BAR_GAP,
        })
        self._panel.add(graph)

        self._graph_bars = []
        for _ in range(_HISTORY_LEN):
            bar = UIElement(None, styles={
                "width": _BAR_WIDTH, "height": 1,
                "parent_anchor": "bottom_left", "anchor": "bottom_left",
                "base_color": (0.1, 1.0, 0.4, 1.0),
            })
            graph.add(bar)
            self._graph_bars.append(bar)

        self._breakdown = UIElement(None, styles={
            "width": "100w", "height": "auto", "layout": "vertical", "gap": 2,
        })
        self._panel.add(self._breakdown)

    def _make_row(self, text: str, color=(0.85, 0.85, 0.85, 1.0)):
        from FreeBodyEngine.ui import UIElement
        return UIElement(None, styles={
            "font": _FONT, "font_size": 12, "text_color": color,
            "width": "100w", "height": 14, "text": text,
        })

    # -- per-frame update ----------------------------------------------------

    def update(self):
        timings = get_main().updater.last_frame_timings
        flat = [(label, seconds) for entries in timings.values() for (label, seconds) in entries]
        total_seconds = sum(seconds for _, seconds in flat)
        self.history.append(total_seconds)

        if not self.visible:
            return

        fps = get_main().time.get_fps()
        total_ms = total_seconds * 1000.0
        color = (0.1, 1.0, 0.4, 1.0) if total_ms <= _BUDGET_MS else (1.0, 0.75, 0.1, 1.0) if total_ms <= _BUDGET_MS * 2 else (1.0, 0.25, 0.25, 1.0)
        self._fps_label.set_style("text", f"{fps} fps - {total_ms:.2f}ms/frame (budget {_BUDGET_MS:.1f}ms)")
        self._fps_label.set_style("text_color", color)

        # History graph - self.history is a deque(maxlen=_HISTORY_LEN), so
        # this always has at most _HISTORY_LEN entries; older samples
        # (indices before the oldest) just leave that bar at its default
        # height until the graph has actually seen enough frames to fill.
        hist = list(self.history)
        pad = len(self._graph_bars) - len(hist)
        for i, bar in enumerate(self._graph_bars):
            if i < pad:
                bar.set_style("height", 1)
                continue
            seconds = hist[i - pad]
            ms = seconds * 1000.0
            # Capped at 4x budget so one exceptionally bad frame doesn't
            # squash every other bar down to invisible slivers by
            # comparison - still clearly reads as "way over budget" via
            # both the height cap and the color.
            height = max(1, min(_GRAPH_HEIGHT, int((ms / (_BUDGET_MS * 4)) * _GRAPH_HEIGHT)))
            bar.set_style("height", height)
            bar_color = (0.1, 1.0, 0.4, 1.0) if ms <= _BUDGET_MS else (1.0, 0.75, 0.1, 1.0) if ms <= _BUDGET_MS * 2 else (1.0, 0.25, 0.25, 1.0)
            bar.set_style("base_color", bar_color)

        # Breakdown - top N slowest callbacks this frame, descending.
        self._breakdown.children.clear()
        for label, seconds in sorted(flat, key=lambda x: x[1], reverse=True)[:_BREAKDOWN_ROWS]:
            ms = seconds * 1000.0
            row_color = (0.85, 0.85, 0.85, 1.0) if ms < 1.0 else (1.0, 0.75, 0.1, 1.0) if ms < 4.0 else (1.0, 0.25, 0.25, 1.0)
            self._breakdown.add(self._make_row(f"{label}: {ms:.2f}ms", row_color))
