from itertools import product


def generate_overloads_with_cost(param_slots, allowed_types_map, max_size=None):
    """
    Generate overloads using types from allowed_types_map.
    Each overload keeps track of type costs.
    """
    overloads = []
    n_slots = max_size if max_size else len(param_slots)

    type_list = list(allowed_types_map.keys())

    for n in range(1, n_slots + 1):
        slots_subset = param_slots[:n]

        for combo in product(type_list, repeat=n):
            overload = {"params": {name: t for name, t in zip(slots_subset, combo)}}
            overload["cost"] = sum(allowed_types_map[t] for t in combo)
            overloads.append(overload)

    return overloads


TYPES = {
    "int": {
        "operations": {
            "+": {"int": "int"},
            "-": {"int": "int"},
            "*": {"int": "int"},
            "/": {"int": "int"},
            "%": {"int": "int"},
            "&": {"int": "int"},
            "|": {"int": "int"},
            "^": {"int": "int"},
            "<<": {"int": "int"},
            ">>": {"int": "int"},
            "-_unary": {"": "int"},
            "+_unary": {"": "int"},
            "~": {"": "int"},
            "==": {"int": "bool"},
            "!=": {"int": "bool"},
            "<": {"int": "bool"},
            "<=": {"int": "bool"},
            ">": {"int": "bool"},
            ">=": {"int": "bool"},
        }
    },
    "float": {
        "operations": {
            "+": {"float": "float"},
            "-": {"float": "float"},
            "*": {"float": "float"},
            "/": {"float": "float"},
            "-_unary": {"": "float"},
            "+_unary": {"": "float"},
            "==": {"float": "bool"},
            "!=": {"float": "bool"},
            "<": {"float": "bool"},
            "<=": {"float": "bool"},
            ">": {"float": "bool"},
            ">=": {"float": "bool"},
        }
    },
    "vec2": {
        "fields": {"x": "float", "y": "float", "xy": "vec2", "yx": "vec2"},
        "operations": {
            "+": {"vec2": "vec2"},
            "-": {"vec2": "vec2"},
            "*": {"float": "vec2"},
            "/": {"float": "vec2"},
        },
    },
    "vec3": {
        "fields": {
            "x": "float",
            "y": "float",
            "z": "float",
            "xy": "vec2",
            "yx": "vec2",
            "yz": "vec2",
            "zy": "vec2",
            "xz": "vec2",
            "zx": "vec2",
            "xyz": "vec3",
            "xzy": "vec3",
            "yxz": "vec3",
            "yzx": "vec3",
            "zxy": "vec3",
            "zyx": "vec3",
        },
        "operations": {
            "+": {"vec3": "vec3"},
            "-": {"vec3": "vec3"},
            "*": {"float": "vec3"},
            "/": {"float": "vec3"},
        },
    },
    "vec4": {
        "fields": {
            "x": "float",
            "y": "float",
            "z": "float",
            "w": "float",
            "xy": "vec2",
            "xz": "vec2",
            "xw": "vec2",
            "yx": "vec2",
            "yz": "vec2",
            "yw": "vec2",
            "zx": "vec2",
            "zy": "vec2",
            "zw": "vec2",
            "wx": "vec2",
            "wy": "vec2",
            "wz": "vec2",
            "xyz": "vec3",
            "xzy": "vec3",
            "xwy": "vec3",
            "xwz": "vec3",
            "yxz": "vec3",
            "yzx": "vec3",
            "ywx": "vec3",
            "ywz": "vec3",
            "zxy": "vec3",
            "zyx": "vec3",
            "zwx": "vec3",
            "zwy": "vec3",
            "wxy": "vec3",
            "wyx": "vec3",
            "wzx": "vec3",
            "wzy": "vec3",
            "xyzw": "vec4",
            "xzyw": "vec4",
            "xwzy": "vec4",
            "xwyz": "vec4",
            "yxzw": "vec4",
            "yzxw": "vec4",
            "ywxz": "vec4",
            "ywzx": "vec4",
            "zxyw": "vec4",
            "zyxw": "vec4",
            "zwxy": "vec4",
            "zwyx": "vec4",
            "wxyz": "vec4",
            "wyxz": "vec4",
            "wzxy": "vec4",
            "wzyx": "vec4",
        },
        "operations": {
            "+": {"vec4": "vec4"},
            "-": {"vec4": "vec4"},
            "*": {"float": "vec4"},
            "/": {"float": "vec4"},
        },
    },
    "mat2": {
        "fields": {"col0": "vec2", "col1": "vec2"},
        "operations": {"*": {"float": "mat2", "vec2": "vec2", "mat2": "mat2"}},
    },
    "mat3": {
        "fields": {"col0": "vec3", "col1": "vec3", "col2": "vec3"},
        "operations": {"*": {"float": "mat3", "vec3": "vec3", "mat3": "mat3"}},
    },
    "mat4": {
        "fields": {"col0": "vec4", "col1": "vec4", "col2": "vec4", "col3": "vec4"},
        "operations": {"*": {"float": "mat4", "vec4": "vec4", "mat4": "mat4"}},
    },
    "texture": {"fields"},
    "array": {
        "data": {"element_type": str, "length": int},
        "operations": {[]: lambda array_type: array_type["data"]["element_type"]},
    },
}

BUILTINS = {
    "all": {
        "round": {"return": "int", "params": {"x": "float"}, "kind": "function"},
        "float": {"return": "float", "params": {"x": "int"}, "kind": "function"},
        "vec2": {
            "return": "vec2",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y"], {"float": 1, "vec2": "2"}, max_size=2
            ),
        },
        "vec3": {
            "return": "vec3",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y", "z"], {"float": 1, "vec2": "2", "vec3": 3}, max_size=3
            ),
        },
        "vec4": {
            "return": "vec4",
            "kind": "function",
            "overloads": generate_overloads_with_cost(
                ["x", "y", "z", "w"],
                {"float": 1, "vec2": 2, "vec3": 3, "vec4": 4},
                max_size=4,
            ),
        },
        "mat2": {
            "return": "mat2",
            "kind": "function",
            "overloads": [
                {"params": {"x": "float"}},
                {"params": {"col0": "vec2", "col1": "vec2"}},
            ],
        },
        "mat3": {
            "return": "mat3",
            "kind": "function",
            "overloads": [
                {"params": {"x": "float"}},
                {"params": {"col0": "vec3", "col1": "vec3", "col2": "vec3"}},
            ],
        },
        "mat4": {
            "return": "mat4",
            "kind": "function",
            "overloads": [
                {"params": {"x": "float"}},
                {
                    "params": {
                        "col0": "vec4",
                        "col1": "vec4",
                        "col3": "vec4",
                        "col3": "vec4",
                    }
                },
            ],
        },
    },
    "vertex": {"VERTEX_POSITION": {"type": "vec2", "kind": "output"}},
}
