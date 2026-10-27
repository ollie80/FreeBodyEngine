"""Tests for the visual-only transform styles (scale, rotation, tilt,
perspective) - how the renderer works out where a transformed element
draws, and that it's drawn through the one shader that can transform it.
The shader itself needs a GPU; this covers the CPU side, which has to
agree with it."""
import pytest

from FreeBodyEngine.ui.renderer import UIRenderer, transform_of, visual_bounds


def test_no_transform_by_default():
    assert transform_of({}) is None
    assert transform_of({"scale": 1, "rotation": 0, "tilt": (0, 0)}) is None


def test_angles_become_radians():
    rotation, tilt_x, tilt_y, scale = transform_of({"rotation": 180, "tilt": (90, -90), "scale": 2})
    assert (rotation, tilt_x, tilt_y, scale) == pytest.approx((3.14159265, 1.5707963, -1.5707963, 2.0))


def test_scale_grows_around_the_centre():
    bounds = visual_bounds((100, 100, 50, 20), transform_of({"scale": 2}), 1000)
    assert bounds == pytest.approx((74, 89, 102, 42))


def test_a_quarter_turn_swaps_width_and_height():
    bounds = visual_bounds((0, 0, 100, 20), transform_of({"rotation": 90}), 1000)
    assert bounds == pytest.approx((39, -41, 22, 102))


def test_tilting_right_edge_away_shrinks_it_and_grows_the_left():
    x, y, w, h = visual_bounds((0, 0, 200, 200), transform_of({"tilt": (20, 0)}), 400)
    # Narrower overall (the quad turns side-on), but the near (left) edge
    # comes toward the viewer, so it's taller than the element and pokes
    # out past where the element's left edge was.
    assert w < 200
    assert h > 200
    assert x < 0


def test_tilting_bottom_edge_away():
    x, y, w, h = visual_bounds((0, 0, 200, 200), transform_of({"tilt": (0, 20)}), 400)
    assert h < 200
    assert w > 200
    assert y < 0


class _Recorder(UIRenderer):
    """A UIRenderer that records which drawing path each background takes,
    with no GPU behind it."""

    def __init__(self):
        self._pending_instances = []
        self._scale = 1.0
        self.immediate = []

    def _flush_instances(self):
        pass

    def _flush_text(self):
        pass

    def _draw_background_immediate(self, element, styles, width, height):
        self.immediate.append(element)


def test_a_transformed_background_is_drawn_through_the_transforming_shader(ui):
    renderer = _Recorder()
    plain = ui.UIElement(styles={"width": 10, "height": 10, "base_color": (1, 0, 0, 1)})
    tilted = ui.UIElement(styles={"width": 10, "height": 10, "base_color": (1, 0, 0, 1), "tilt": (5, 0)})
    root = ui.RootElement(800, 600)
    root.add(plain)
    root.add(tilted)
    root.calculate_layout()

    renderer._draw_background(plain, plain.get_current_styles())
    renderer._draw_background(tilted, tilted.get_current_styles())

    assert renderer.immediate == [tilted]
    assert len(renderer._pending_instances) == 1


def test_damage_covers_where_a_transformed_element_draws(ui):
    renderer = _Recorder()
    renderer._dirty_rect = None
    box = ui.UIElement(styles={"width": 100, "height": 100, "base_color": (1, 0, 0, 1), "scale": 2})
    root = ui.RootElement(800, 600)
    root.add(box)
    root.calculate_layout()

    renderer._compute_dirty_rect(box, (0, 0, 800, 600))
    x, y, w, h = renderer._dirty_rect
    assert (x, y) == pytest.approx((-51, -51)) and (w, h) == pytest.approx((202, 202))


def test_the_transform_styles_animate(ui):
    box = ui.UIElement(styles={"scale": 0.5})
    box.set_style("scale", 1.0, duration=1.0)
    box.set_style("tilt", (10.0, 0.0), duration=1.0)
    box._update()
    styles = box.get_current_styles()
    assert styles["scale"] == pytest.approx(0.75)
    assert styles["tilt"] == pytest.approx((5.0, 0.0))
