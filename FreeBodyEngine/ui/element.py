from dataclasses import dataclass
import uuid
from enum import Enum
from FreeBodyEngine.math import Curve, Linear
from FreeBodyEngine import warning, delta
import re

class GenericElement:
    def __init__(self, tag: str = None):
        self.children: dict[uuid.UUID, 'UIElement'] = {}
        self.tag = tag
        self.styles: dict[str, any] = {}

    def add(self, element: 'UIElement') -> None:
        element._initialize(self)

    def _remove(self, element_id: uuid.UUID) -> None:
        del self.children[element_id]

    def remove(self, element: 'UIElement') -> None:
        self._remove(element.id)

    def _update(self):
        pass


class RootElement(GenericElement):
    def __init__(self, width: int, height: int, styles={}):
        super().__init__()
        self.styles = styles
        self.width = width
        self.height = height

        self.layout = Layout(0, 0, width, height)

    def set_styles(self, styles: dict[str, any]):
        self.styles = styles

    def calculate_layout(self):
        """
        Calculate layout for the root and recursively for all children.
        """
        styles = self.styles
        pad = int(styles.get("padding", 0))
        pad_left = int(styles.get("padding_left", pad))
        pad_right = int(styles.get("padding_right", pad))
        pad_top = int(styles.get("padding_top", pad))
        pad_bottom = int(styles.get("padding_bottom", pad))

        content_x = self._layout.x + pad_left
        content_y = self._layout.y + pad_top
        content_w = max(0, self.width - (pad_left + pad_right))
        content_h = max(0, self.height - (pad_top + pad_bottom))

        layout_dir = styles.get("layout", "vertical")
        gap = int(styles.get("gap", 0))

        child_offset_x = content_x
        child_offset_y = content_y

        root_content_layout = Layout(content_x, content_y, content_w, content_h)

        for child in self.children.values():
            child.calculate_layout(self, root_content_layout)

            if layout_dir == "vertical":
                child_offset_y += child._layout.height + gap
            else:  # horizontal
                child_offset_x += child._layout.width + gap


class ElementStates(Enum):
    NORMAL = "normal"
    CLICKED = "clicked"
    HOVER = "hover"
    SELECTED = 'selected'

@dataclass
class Layout:
    x: int
    y: int
    width: int
    height: int

class UIElement(GenericElement):
    def __init__(self, tag: str = None, styles={}):
        super().__init__(tag)
        self.state = ElementStates.NORMAL
        self.styles: dict[str, any] = styles
        self.parent: GenericElement
        self.id = uuid.uuid4()
        self.animations: list[UIAnimation] = []

        self._layout = Layout((0, 0), (0, 0))


    def _initialize(self, parent: GenericElement):
        self.parent = parent
        self.parent.children[self.id] = self

    def get_current_styles(self) -> dict[str, any]:
        """
        Merge base styles and state-dependent styles.
        """
        current_styles = dict(self.styles)
        state_name = self.state.value
        if state_name in self.styles:
            for k, v in self.styles[state_name].items():
                current_styles[k] = v
        return current_styles

    def _parse_size(self, size_str: str, parent_layout: Layout, root_layout: Layout) -> int:
        """
        Parse a size string into pixels using layout objects.
        
        Supported formats:
        "200"   -> fixed pixels
        "69w"   -> 69% of parent content width
        "69h"   -> 69% of parent content height
        "69ww"  -> 69% of window width
        "69hw"  -> 69% of window height
        """
        s = str(size_str).strip().lower()
        if not s:
            return 0

        try:
            return int(float(s))
        except ValueError:
            pass

        if s[-2:] in ("ww", "hw"):
            num = float(s[:-2])
            suffix = s[-2:]
        else:
            num = float(s[:-1])
            suffix = s[-1]

        if suffix == "w":
            return int(parent_layout.width * (num / 100.0))
        if suffix == "h":
            return int(parent_layout.height * (num / 100.0))

        if suffix == "ww":
            return int(root_layout.width * (num / 100.0))
        if suffix == "hw":
            return int(root_layout.height * (num / 100.0))

        return 0

    def get_style(self, name: str):
        if name in self.styles:
            return self.styles[name]
        else:
            warning(f'Style "{name}" does not exist.')

    def _set_style(self, name: str, val: any):
        self.styles[name] = val
        
    def set_style(self, name: str, val: any, duration=0, curve=Linear):
        if duration == 0:
            self._set_style(name, val)
        else:
            self.animations.append(UIAnimation(self, name, val, duration, curve))

    def calculate_layout(self, root: 'RootElement', parent_layout: Layout = None):
        styles = self.get_current_styles()

        if parent_layout is None:
            parent_w, parent_h = (root.width, root.height)
            offset_x, offset_y = 0, 0
        else:
            parent_w, parent_h = parent_layout.width, parent_layout.height
            offset_x, offset_y = parent_layout.x, parent_layout.y

        self._layout.width = self._parse_size(styles.get("width", "0"), parent_layout, root.layout)
        self._layout.height = self._parse_size(styles.get("height", "0"), parent_layout, root.layout)

        pad = self._parse_size(styles.get("padding", 0), parent_layout, root.layout)
        pad_left = self._parse_size(styles.get("padding_left", pad), parent_layout, root.layout)
        pad_right = self._parse_size(styles.get("padding_right", pad), parent_layout, root.layout)
        pad_top = self._parse_size(styles.get("padding_top", pad), parent_layout, root.layout)
        pad_bottom = self._parse_size(styles.get("padding_bottom", pad), parent_layout, root.layout)

        self._layout.x = offset_x
        self._layout.y = offset_y

        content_x = self._layout.x + pad_left
        content_y = self._layout.y + pad_top
        content_w = max(0, self._layout.width - (pad_left + pad_right))
        content_h = max(0, self._layout.height - (pad_top + pad_bottom))

        layout_dir = styles.get("layout", "vertical")
        gap = int(styles.get("gap", 0))
 
        child_offset_x = content_x
        child_offset_y = content_y

        for child in self.children.values():
            child_layout = Layout(child_offset_x, child_offset_y, content_w, content_h)
            child.calculate_layout(root, child_layout)

            if layout_dir == "vertical":
                child_offset_y += child._layout.height + gap
            else:  # horizontal
                child_offset_x += child._layout.width + gap

    def _update(self):
        for animation in self.animations:
            animation.update()

class UIAnimation:
    def __init__(self, element: 'UIElement', style: str, end_value: any, duration: float, curve: Curve = Linear()):
        self.style = style
        self.element = element
        self.curve = curve
        self.end_value = end_value
        self.duration = duration
        self.elapsed = 0.0
        self.finished = False

        self.start_value = self._capture_start_value()
        self._validate_animatable()

        if isinstance(self.start_value, str):
            self.start_nums, self.start_parts = self._extract_numbers(self.start_value)
            self.end_nums, self.end_parts = self._extract_numbers(self.end_value)
        elif isinstance(self.start_value, (tuple, list)):
            self.start_shape = self._get_shape(self.start_value)
            self.end_shape = self._get_shape(self.end_value)

    def _capture_start_value(self):
        val = self.element.get_style(self.style)
        if isinstance(val, (int, float, tuple, list, str)):
            return val
        else:
            raise ValueError(f"Unsupported type for animation: {type(val)}")

    def _extract_numbers(self, s: str):
        parts = re.split(r'(-?\d+\.?\d*)', s)
        nums = [float(p) for p in parts if re.fullmatch(r'-?\d+\.?\d*', p)]
        return nums, parts 

    def _get_shape(self, iterable):
        """Return nested shape for tuples/lists."""
        if isinstance(iterable, (list, tuple)):
            return tuple(self._get_shape(x) if isinstance(x, (list, tuple)) else 0 for x in iterable)
        else:
            return 0

    def _validate_animatable(self):
        """Check if the start and end values are compatible for animation."""
        end = self.end_value
        start = self.start_value

        if type(start) != type(end):
            raise ValueError(f"Start ({type(start)}) and end ({type(end)}) types do not match")

        if isinstance(start, str):
            start_nums, start_parts = self._extract_numbers(start)
            end_nums, end_parts = self._extract_numbers(end)
            non_numeric_start = [p for p in start_parts if not re.fullmatch(r'-?\d+\.?\d*', p)]
            non_numeric_end = [p for p in end_parts if not re.fullmatch(r'-?\d+\.?\d*', p)]
            if non_numeric_start != non_numeric_end:
                warning("Non-numeric parts of start/end string do not match")
                self.remove()

            if len(start_nums) != len(end_nums):
                warning("Number of numeric parts in start/end string do not match")
                self.remove()

        elif isinstance(start, (tuple, list)):
            start_shape = self._get_shape(start)
            end_shape = self._get_shape(end)
            if start_shape != end_shape:
                warning("Start and end iterables have different shapes")
                self.remove()

    def _interpolate(self, start, end, t: float):
        if isinstance(start, (int, float)):
            return start + (end - start) * t
        elif isinstance(start, (tuple, list)):
            return type(start)(self._interpolate(s, e, t) for s, e in zip(start, end))
        elif isinstance(start, str):
            interpolated_nums = [s + (e - s) * t for s, e in zip(self.start_nums, self.end_nums)]
            result = []
            num_idx = 0
            for p in self.start_parts:
                if re.fullmatch(r'-?\d+\.?\d*', p):
                    result.append(str(interpolated_nums[num_idx]))
                    num_idx += 1
                else:
                    result.append(p)
            return ''.join(result)
        else:
            warning('Could not interpolate between animation values.')
            self.remove()

    def update(self):
        delta_time = delta()
        if self.finished:
            return

        self.elapsed += delta_time
        t = min(self.elapsed / self.duration, 1.0)
        t = self.curve(t)

        new_value = self._interpolate(self.start_value, self.end_value, t)
        self.element._set_style(self.style, new_value)

        if self.elapsed >= self.duration:
            self.finished = True
            if self in self.element.animations:
                self.remove()

    def remove(self):
        self.element.animations.remove(self)