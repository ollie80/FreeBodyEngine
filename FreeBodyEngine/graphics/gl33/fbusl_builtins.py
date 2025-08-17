GL33_BUILTINS = {
    "round": {"return": "int", "params": {"x": "float"}, "kind": "function"},
    "vec4": {'return': 'vec4', "kind": "function", "overloads": [
        {'x': 'float'},
        {'x': 'float', 'y': 'float'},
        {'x': 'float', 'y': 'float', 'z': 'float'},
        {'x': 'float', 'y': 'float', 'z': 'float', 'w': 'float'},

        ]
    },
    "VERTEX_POSITION": {"type": "vec2", "kind": "output"},
}

