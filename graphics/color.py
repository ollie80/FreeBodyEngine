
class Color:
    def __init__(self, value: str | tuple | list):
        if isinstance(value, (tuple, list)):
            if isinstance(value[0], float):
                if len(value) == 3:
                    self.float_normalized_a = tuple(value) + (1.0,)
                elif len(value) == 4:
                    self.float_normalized_a = tuple(value)

            elif isinstance(value[0], int):
                self.float_normalized_a = self._rgb_to_fn(value)

        elif isinstance(value, str):
            self.float_normalized_a = self._hex_to_fn(value)

    def _hex_to_fn(self, hex_value: str):
        hex_value = hex_value.lstrip("#")

        if len(hex_value) == 6:
            return tuple(
                int(hex_value[i : i + 2], 16) / 255.0 for i in range(0, 6, 2)
            ) + (1.0,)
        elif len(hex_value) == 8:
            return tuple(int(hex_value[i : i + 2], 16) / 255.0 for i in range(0, 8, 2))
        else:
            raise ValueError(
                "Invalid hex string. It must be either 6 (RGB) or 8 (RGBA) characters long."
            )

    def _rgb_to_fn(self, rgb_value: tuple):
        if len(rgb_value) == 3:
            return tuple(c / 255.0 for c in rgb_value) + (1.0,)
        elif len(rgb_value) == 4:
            return tuple(c / 255.0 for c in rgb_value)
        else:
            raise ValueError(
                "Invalid tuple length. It must have 3 (RGB) or 4 (RGBA) values."
            )

    def _fn_to_rgb(self, val: tuple, alpha: bool = False):
        rgb = tuple(round(c * 255) for c in val[:3])
        if not alpha:
            return rgb
        else:
            return rgb + (round(val[3] * 255),)

    def _fn_to_hex(self, val: tuple, alpha: bool = False):
        hex_color = "".join(f"{int(c):02x}" for c in val[:3])
        if alpha:
            hex_color += f"{int(val[3] * 255):02x}"
        return f"#{hex_color}"

    @property
    def rgb(self) -> tuple[int, int, int]:
        """
        (R, G, B)
        """
        return self._fn_to_rgb(self.float_normalized_a)

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        """
        (R, G, B, A)
        """
        return self._fn_to_rgb(self.float_normalized_a, True)

    @property
    def hex(self) -> str:
        """
        #RRGGBB
        """
        return self._fn_to_hex(self.float_normalized_a)

    @hex.setter
    def hex(self, new):
        self.float_normalized_a = self._hex_to_fn(new)

    @hex.setter
    def hex(self, new):
        self.float_normalized_a = self._hex_to_fn(new)

    @hex.setter
    def hex(self, new):
        self.float_normalized_a = self._hex_to_fn(new)

    @hex.setter
    def rgb(self, new):
        self.float_normalized_a = self._rgb_to_fn(new)

    @property
    def hexa(self) -> str:
        """
        #RRGGBBAA
        """
        return self._fn_to_rgb(self.float_normalized_a, True)

    @property
    def float_normalized(self) -> tuple[float, float, float]:
        """
        (R, G, B), values are stored in floats between 0-1
        """
        return (
            self.float_normalized_a[0],
            self.float_normalized_a[1],
            self.float_normalized_a[2],
        )

    def __iter__(self):
        return iter(self.float_normalized_a)

    def __len__(self):
        return len(self.float_normalized_a)
