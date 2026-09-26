"""The external profiler's own UI - a real FreeBodyEngine scene, built
with the engine's own native UIElement (see the ui-rewrite work this
profiler was born out of), showing live CPU/GPU/memory/draw-call graphs
and a sortable per-callback breakdown for whatever app its ProfilerClient
is connected to, and writing every received snapshot to a ProfilerLog on
disk the whole time."""
from collections import deque

from FreeBodyEngine.core.scene import Scene
from FreeBodyEngine import register_service_update, get_service
from FreeBodyEngine.core.update import UpdatePhase

from FreeBodyEngine.cli.profiler.logs import ProfilerLog

_FONT = "engine://font/JetBrainsMono.ttf"
_HISTORY_LEN = 240

_BG = (0.03, 0.05, 0.04, 1.0)
_PANEL_BG = (0.07, 0.09, 0.08, 1.0)
_FG = (0.85, 0.95, 0.88, 1.0)
_MUTED = (0.5, 0.6, 0.55, 1.0)
_GOOD = (0.2, 0.9, 0.4, 1.0)
_WARN = (0.95, 0.75, 0.15, 1.0)
_BAD = (0.95, 0.3, 0.3, 1.0)
_ACCENT = (0.3, 0.85, 0.6, 1.0)

_BUDGET_MS = 1000.0 / 60.0


def _level_color(value, warn_at, bad_at):
    if value <= warn_at:
        return _GOOD
    if value <= bad_at:
        return _WARN
    return _BAD


class Graph:
    """One labelled history-bar graph: a title/value row plus a row of
    thin bars, each one historical sample, height-scaled against
    `max_value` and colored per-sample via `color_fn(value) -> rgba`.
    Shared by the CPU/memory/draw-call graphs below - only the data feeding
    it differs."""

    def __init__(self, parent, title: str, height: int, bar_count: int = _HISTORY_LEN, bar_width: int = 3):
        from FreeBodyEngine.ui import UIElement
        self.height = height
        self.history = deque(maxlen=bar_count)

        panel = UIElement(None, styles={
            "width": "100w", "height": "auto", "layout": "vertical", "gap": 4,
            "padding": 10, "base_color": _PANEL_BG, "border_radius": 6,
        })
        parent.add(panel)

        header = UIElement(None, styles={"width": "100w", "height": 20, "layout": "horizontal"})
        panel.add(header)
        self.title_label = UIElement(None, styles={
            "font": _FONT, "font_size": 13, "text_color": _MUTED, "width": "70w", "height": 18, "text": title,
        })
        header.add(self.title_label)
        self.value_label = UIElement(None, styles={
            "font": _FONT, "font_size": 13, "text_color": _FG, "width": "30w", "height": 18, "text": "--",
        })
        header.add(self.value_label)

        graph_row = UIElement(None, styles={
            "width": "100w", "height": height, "layout": "horizontal", "gap": 1,
            "base_color": (0.0, 0.0, 0.0, 0.25), "border_radius": 3,
        })
        panel.add(graph_row)

        self.bars = []
        for _ in range(bar_count):
            bar = UIElement(None, styles={
                "width": bar_width, "height": 1,
                "parent_anchor": "bottom_left", "anchor": "bottom_left",
                "base_color": _ACCENT,
            })
            graph_row.add(bar)
            self.bars.append(bar)

    def push(self, value: float, max_value: float, value_text: str, color):
        self.history.append(value)
        self.value_label.set_style("text", value_text)
        self.value_label.set_style("text_color", color)

        hist = list(self.history)
        pad = len(self.bars) - len(hist)
        for i, bar in enumerate(self.bars):
            if i < pad:
                bar.set_style("height", 1)
                continue
            v = hist[i - pad]
            frac = 0.0 if max_value <= 0 else min(1.0, v / max_value)
            bar.set_style("height", max(1, int(frac * self.height)))


class ProfilerApp(Scene):
    """The external profiler's one and only scene - see this module's own
    docstring."""

    def __init__(self):
        super().__init__("profiler")
        self.log = ProfilerLog()
        self._latest_phases = {}

    def on_initialize(self):
        from FreeBodyEngine.ui import UIElement

        client = get_service("profiler_client")

        root = UIElement("profiler_root", styles={
            "width": "100w", "height": "100h", "layout": "vertical", "gap": 10,
            "padding": 14, "base_color": _BG,
        })
        get_service("ui").add(root)
        self.client = client

        # -- header ------------------------------------------------------
        header = UIElement(None, styles={"width": "100w", "height": 40, "layout": "vertical", "gap": 2})
        root.add(header)
        self.title_row = UIElement(None, styles={
            "font": _FONT, "font_size": 18, "text_color": _ACCENT, "width": "100w", "height": 22,
            "text": "FreeBodyEngine Profiler",
        })
        header.add(self.title_row)
        self.status_row = UIElement(None, styles={
            "font": _FONT, "font_size": 13, "text_color": _MUTED, "width": "100w", "height": 16,
            "text": f"Connecting to {client.host}:{client.port} ...",
        })
        header.add(self.status_row)

        # -- graphs --------------------------------------------------------
        graphs_row = UIElement(None, styles={"width": "100w", "height": 170, "layout": "horizontal", "gap": 10})
        root.add(graphs_row)

        cpu_col = UIElement(None, styles={"width": "34w", "height": "100h", "layout": "vertical"})
        graphs_row.add(cpu_col)
        self.cpu_graph = Graph(cpu_col, "CPU frame time (ms)", height=110)

        mem_col = UIElement(None, styles={"width": "33w", "height": "100h", "layout": "vertical"})
        graphs_row.add(mem_col)
        self.mem_graph = Graph(mem_col, "Process memory (MB)", height=110)

        draw_col = UIElement(None, styles={"width": "33w", "height": "100h", "layout": "vertical"})
        graphs_row.add(draw_col)
        self.draw_graph = Graph(draw_col, "Draw calls / frame", height=110)

        # -- secondary stats row (fps/gpu/tps) --------------------------
        stats_row = UIElement(None, styles={
            "width": "100w", "height": 24, "layout": "horizontal", "gap": 16,
            "padding": 4,
        })
        root.add(stats_row)
        self.fps_label = self._stat_label(stats_row, "fps: --")
        self.tps_label = self._stat_label(stats_row, "tps: --")
        self.gpu_label = self._stat_label(stats_row, "gpu: --")
        self.frame_label = self._stat_label(stats_row, "frame: --")
        self.log_label = UIElement(None, styles={
            "font": _FONT, "font_size": 11, "text_color": _MUTED, "width": "100w", "height": 16,
            "text": f"logging to {self.log.path}",
        })

        # -- breakdown (scrollable - the exact same native overflow
        # mechanism the rest of this session's work landed) --------------
        breakdown_header = UIElement(None, styles={
            "font": _FONT, "font_size": 14, "text_color": _FG, "width": "100w", "height": 20,
            "text": "Per-callback breakdown (this frame, slowest first)",
        })
        root.add(breakdown_header)

        self.breakdown = UIElement(None, styles={
            "width": "100w", "height": "auto", "layout": "vertical", "gap": 2,
            "overflow": "auto", "padding": 6, "base_color": _PANEL_BG, "border_radius": 6,
            "scrollbar_thumb": {"base_color": (0.4, 0.5, 0.45, 0.6)},
        })
        root.add(self.breakdown)
        root.add(self.log_label)

        register_service_update(UpdatePhase.LATE, self.update, priority=-1000)

    def _stat_label(self, parent, text):
        from FreeBodyEngine.ui import UIElement
        label = UIElement(None, styles={
            "font": _FONT, "font_size": 13, "text_color": _FG, "width": 160, "height": 18, "text": text,
        })
        parent.add(label)
        return label

    def update(self):
        snapshots = self.client.poll()
        for snap in snapshots:
            self.log.write(snap)

        if not snapshots:
            self.status_row.set_style(
                "text",
                f"Connected to {self.client.host}:{self.client.port} - waiting for data..."
                if self.client.connected else
                f"Not connected - retrying {self.client.host}:{self.client.port} ...",
            )
            self.status_row.set_style("text_color", _MUTED if self.client.connected else _WARN)
            return

        snap = snapshots[-1]
        self.status_row.set_style("text", f"Connected to {self.client.host}:{self.client.port}")
        self.status_row.set_style("text_color", _GOOD)
        self._latest_phases = snap.get("phases") or {}

        total_ms = sum(seconds for entries in self._latest_phases.values() for _, seconds in entries) * 1000.0
        self.cpu_graph.push(
            total_ms, _BUDGET_MS * 4, f"{total_ms:.2f}ms",
            _level_color(total_ms, _BUDGET_MS, _BUDGET_MS * 2),
        )

        mem = snap.get("memory_mb")
        if mem is not None:
            recent_max = max([*self.mem_graph.history, mem]) if self.mem_graph.history else mem
            self.mem_graph.push(mem, max(recent_max, 1.0), f"{mem:.0f}MB", _FG)

        draw_calls = snap.get("draw_calls")
        if draw_calls is not None:
            self.draw_graph.push(draw_calls, max(draw_calls, 200), str(draw_calls), _FG)

        fps = snap.get("fps")
        self.fps_label.set_style("text", f"fps: {fps}")
        self.fps_label.set_style("text_color", _level_color(1000.0 / fps if fps else 999, 1000.0 / 55, 1000.0 / 30))

        self.tps_label.set_style("text", f"tps: {snap.get('tps')}")

        gpu_ms = snap.get("gpu_ms")
        self.gpu_label.set_style("text", f"gpu: {gpu_ms:.2f}ms" if gpu_ms is not None else "gpu: unavailable")

        self.frame_label.set_style("text", f"frame: {snap.get('frame')}")

        # -- breakdown list -------------------------------------------------
        flat = [(f"{phase}: {label}", seconds) for phase, entries in self._latest_phases.items() for label, seconds in entries]
        self.breakdown.children.clear()
        for label, seconds in sorted(flat, key=lambda x: x[1], reverse=True)[:40]:
            ms = seconds * 1000.0
            color = _FG if ms < 1.0 else (_WARN if ms < 4.0 else _BAD)
            from FreeBodyEngine.ui import UIElement
            self.breakdown.add(UIElement(None, styles={
                "font": _FONT, "font_size": 12, "text_color": color, "width": "100w", "height": 15,
                "text": f"{label}: {ms:.3f}ms",
            }))
