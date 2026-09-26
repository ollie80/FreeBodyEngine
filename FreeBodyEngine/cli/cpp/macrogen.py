import re
from typing import List, Optional, Tuple

# A bound declaration's parameters are stored as an ordered list of
# (cpp_type, name) tuples - never a set. A 2-element set (the original
# implementation's approach) has no defined iteration order, so unpacking it
# back into (type, name) would silently swap the two at random.
Param = Tuple[str, str]


class CppFunction:
    """A parsed C++ function/method signature: name, ordered parameter
    list, and return type (defaults to "void")."""
    def __init__(self, name: str, params: Optional[List[Param]] = None, return_type: Optional[str] = None):
        """Stores the parsed name, parameters and return type."""
        self.name = name
        self.params: List[Param] = params or []
        self.return_type = return_type or "void"


class CppClass:
    """A parsed C++ class/struct: its public constructors, methods and
    attributes, as discovered by `CppBindingGenerator`."""
    def __init__(self, name: str):
        """Stores the class name and starts with empty constructor/method/
        attribute lists, filled in as parsing proceeds."""
        self.name = name
        self.constructors: List[CppFunction] = []
        self.methods: List[CppFunction] = []
        self.attributes: List[str] = []

    def add_constructor(self, params_raw: str, parse_params) -> None:
        """Parses `params_raw` with `parse_params` (passed in by the caller
        to avoid a circular reference back to the generator) and records the
        resulting constructor."""
        self.constructors.append(CppFunction(self.name, parse_params(params_raw)))

    def add_method(self, name: str, params_raw: str, return_type: str, parse_params) -> None:
        """Parses `params_raw` with `parse_params` and records the
        resulting method, unless `name` matches the class name (a
        constructor mis-parsed as a method)."""
        if name != self.name:  # avoid constructor as method
            self.methods.append(CppFunction(name, parse_params(params_raw), return_type))

    def add_attribute(self, name: str):
        """Records a public attribute name."""
        self.attributes.append(name)


class CppBindingGenerator:
    """Parses one C++ file's `//@bind`-marked functions/classes and can emit
    a pybind11 registration function for them - `register(m)`, which the
    caller wires into whatever module/submodule it wants, rather than a
    self-contained `PYBIND11_MODULE` block. That split is what lets many
    bound files share a single compiled extension (only one PYBIND11_MODULE
    entry point may exist per shared library), which in turn is what lets
    ordinary multi-file C++ - separate translation units linked together -
    work at all.
    """
    def __init__(self, source: str, module_name: str = "my_module"):
        """Stores the raw C++ `source` and target `module_name`, plus the
        C++ -> Python type map used by `_cpp_to_python_type`. Call
        `parse()` before using any of the generation methods."""
        self.source = source
        self.module_name = module_name
        self.classes: List[CppClass] = []
        self.functions: List[CppFunction] = []

        self.type_map = {
            'void': 'None',
            'bool': 'bool',
            'int': 'int',
            'long': 'int',
            'float': 'float',
            'double': 'float',
            'std::string': 'str',
            'string': 'str',
            'const std::string&': 'str',
            'const std::string &': 'str',
            'std::vector': 'list',
            'vector': 'list',
        }

    def parse(self):
        """Scans `source` line by line for `//@bind` markers, dispatching
        each one into class/struct parsing or free-function parsing, and
        populates `self.classes`/`self.functions`."""
        lines = self.source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line == "//@bind" and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("class ") or next_line.startswith("struct "):
                    i = self._parse_class_or_struct(lines, i + 1)
                else:
                    func_match = re.match(r'([\w:<>&*\s]+?)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)', next_line)
                    if func_match:
                        return_type = func_match.group(1).strip()
                        func_name = func_match.group(2).strip()
                        params = self._parse_params(func_match.group(3))
                        self.functions.append(CppFunction(func_name, params, return_type=return_type))
                    i += 2
            else:
                i += 1

    def _parse_class_or_struct(self, lines: List[str], start_index: int) -> int:
        class_line = lines[start_index].strip()
        parts = class_line.split()
        keyword = parts[0]  # "class" or "struct"
        class_name = parts[1].split("{")[0].strip()
        cpp_class = CppClass(class_name)

        in_public = True if keyword == "struct" else False

        brace_count = class_line.count("{") - class_line.count("}")
        class_body_lines = [class_line]
        i = start_index + 1

        while i < len(lines) and brace_count > 0:
            line = lines[i]
            brace_count += line.count("{") - line.count("}")
            class_body_lines.append(line)
            i += 1

        nested_brace_depth = 0

        for line_idx, line in enumerate(class_body_lines):
            stripped = line.strip()

            if line_idx == 0:
                if "public:" in stripped:
                    in_public = True
                elif "private:" in stripped or "protected:" in stripped:
                    in_public = False
                continue

            if nested_brace_depth == 0:
                if stripped == "public:":
                    in_public = True
                    continue
                elif stripped in ("private:", "protected:"):
                    in_public = False
                    continue

            open_braces = line.count("{")
            close_braces = line.count("}")

            if nested_brace_depth > 0:
                nested_brace_depth += open_braces - close_braces
                continue

            if not in_public or not stripped:
                nested_brace_depth += open_braces - close_braces
                continue

            ctor_pattern = rf'{re.escape(class_name)}\s*\(([^)]*)\)'
            ctor_match = re.search(ctor_pattern, stripped)
            if ctor_match:
                cpp_class.add_constructor(ctor_match.group(1).strip(), self._parse_params)
                nested_brace_depth += open_braces - close_braces
                continue

            method_pattern = r'([\w:<>&*\s]+)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:const)?\s*[;{]?'
            method_match = re.match(method_pattern, stripped)
            if method_match:
                return_type = method_match.group(1).strip()
                method_name = method_match.group(2).strip()
                params_raw = method_match.group(3)
                if method_name != class_name and return_type and not return_type.startswith(class_name):
                    cpp_class.add_method(method_name, params_raw, return_type, self._parse_params)
                    nested_brace_depth += open_braces - close_braces
                    continue

            void_method_pattern = r'([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:const)?\s*[;{]?'
            void_method_match = re.match(void_method_pattern, stripped)
            if void_method_match:
                method_name = void_method_match.group(1).strip()
                params_raw = void_method_match.group(2)
                if method_name != class_name:
                    cpp_class.add_method(method_name, params_raw, "void", self._parse_params)
                    nested_brace_depth += open_braces - close_braces
                    continue

            attr_match = re.match(r'^([\w:<>&*\s]+)\s+([A-Za-z_]\w*)\s*(=\s*[^;]+)?\s*;', stripped)
            if attr_match:
                cpp_class.add_attribute(attr_match.group(2))
                nested_brace_depth += open_braces - close_braces
                continue

            nested_brace_depth += open_braces - close_braces

        self.classes.append(cpp_class)
        return i

    def _split_top_level(self, raw: str) -> List[str]:
        """Splits a parameter list on commas, ignoring commas nested inside
        `<...>` (template args) or `(...)` (default-argument calls, function
        pointers)."""
        parts = []
        current = ""
        depth = 0
        for ch in raw:
            if ch in '<(':
                depth += 1
            elif ch in '>)':
                depth -= 1
            if ch == ',' and depth == 0:
                parts.append(current)
                current = ""
                continue
            current += ch
        if current.strip():
            parts.append(current)
        return [p.strip() for p in parts if p.strip()]

    def _typed_param(self, param: str) -> Param:
        """Splits one "TYPE NAME" (optionally "TYPE NAME = default") chunk
        into (type, name) - the name is whatever trailing identifier the
        chunk ends with, everything before it (including any trailing `&`/
        `*` with no space, e.g. `int&x`) is the type."""
        param = param.split('=')[0].strip()
        match = re.match(r'^(.*?)([A-Za-z_]\w*)$', param)
        if not match:
            return (param, '')
        return (match.group(1).strip(), match.group(2))

    def _parse_params(self, raw: str) -> List[Param]:
        if not raw.strip():
            return []
        return [self._typed_param(p) for p in self._split_top_level(raw)]

    def _constructor_init_types(self, ctor: CppFunction) -> str:
        return ', '.join(t for t, _ in ctor.params if t)

    def _cpp_to_python_type(self, cpp_type: str) -> str:
        """Convert C++ type to Python type annotation"""
        cpp_type = cpp_type.strip()

        cpp_type = re.sub(r'\bconst\s+', '', cpp_type)
        cpp_type = re.sub(r'&$', '', cpp_type).strip()
        cpp_type = re.sub(r'\*$', '', cpp_type).strip()

        if cpp_type in self.type_map:
            return self.type_map[cpp_type]

        if cpp_type.startswith('std::vector<') or cpp_type.startswith('vector<'):
            inner_type = re.search(r'<(.+)>', cpp_type)
            if inner_type:
                inner = self._cpp_to_python_type(inner_type.group(1))
                return f'list[{inner}]'
            return 'list'

        if cpp_type in [cls.name for cls in self.classes]:
            return cpp_type

        return 'typing.Any'

    def has_bindings(self) -> bool:
        """True if this file declared any `//@bind` classes or free
        functions."""
        return bool(self.classes or self.functions)

    def generate_bindings_function(self, function_name: str) -> str:
        """Emits `void <function_name>(pybind11::module_& m) { ... }`,
        registering every //@bind class/function this file declared into
        whatever module or submodule `m` the caller passes in."""
        lines = [f'void {function_name}(pybind11::module_& m) {{']

        for cls in self.classes:
            # Every bound class gets a std::shared_ptr<T> holder, not
            # pybind11's default std::unique_ptr<T> - so a bound method
            # can accept/return std::shared_ptr<T> (e.g. a tree node
            # storing its children as shared_ptr<Node>, the way Node in
            # ui/native/node.hpp does) and have pybind11 hand it the same
            # underlying object Python already holds, instead of a second,
            # independently-owned copy. Transparent to classes that never
            # touch shared_ptr<T> themselves - it only changes what type
            # of smart pointer owns the C++ instance a bound Python object
            # wraps, not any binding declared below.
            lines.append(f'    py::class_<{cls.name}, std::shared_ptr<{cls.name}>>(m, "{cls.name}")')

            if cls.constructors:
                for ctor in cls.constructors:
                    param_types = self._constructor_init_types(ctor)
                    if param_types:
                        lines.append(f'        .def(py::init<{param_types}>())')
                    else:
                        lines.append(f'        .def(py::init<>())')
            else:
                lines.append(f'        .def(py::init<>())')

            for method in cls.methods:
                lines.append(f'        .def("{method.name}", &{cls.name}::{method.name})')

            for attr in cls.attributes:
                lines.append(f'        .def_readwrite("{attr}", &{cls.name}::{attr})')

            lines[-1] += ';'

        for func in self.functions:
            lines.append(f'    m.def("{func.name}", &{func.name});')

        lines.append('}')
        return "\n".join(lines)

    def free_function_declarations(self) -> List[str]:
        """Forward declarations for this file's bound free functions -
        enough for a separate translation unit to reference them (and link
        against wherever they're actually defined) without needing to
        `#include` the file itself, which would double-define them if that
        file is also compiled on its own."""
        decls = []
        for func in self.functions:
            params = ', '.join(t for t, _ in func.params)
            decls.append(f'{func.return_type} {func.name}({params});')
        return decls

    def generate_pyi(self) -> str:
        """Generate Python stub file (.pyi) for type checking"""
        lines = ['from typing import Any', '']

        for cls in self.classes:
            lines.append(f'class {cls.name}:')

            ctors = cls.constructors or [CppFunction(cls.name)]
            for ctor in ctors:
                params_str = ''.join(
                    f', {name or f"arg{i}"}: {self._cpp_to_python_type(ptype)}'
                    for i, (ptype, name) in enumerate(ctor.params)
                )
                lines.append(f'    def __init__(self{params_str}) -> None: ...')

            for method in cls.methods:
                return_type = self._cpp_to_python_type(method.return_type)
                params_str = ''.join(
                    f', {name or f"arg{i}"}: {self._cpp_to_python_type(ptype)}'
                    for i, (ptype, name) in enumerate(method.params)
                )
                lines.append(f'    def {method.name}(self{params_str}) -> {return_type}: ...')

            for attr in cls.attributes:
                lines.append(f'    {attr}: Any')

            lines.append('')

        for func in self.functions:
            return_type = self._cpp_to_python_type(func.return_type)
            params_str = ', '.join(
                f'{name or f"arg{i}"}: {self._cpp_to_python_type(ptype)}'
                for i, (ptype, name) in enumerate(func.params)
            )
            lines.append(f'def {func.name}({params_str}) -> {return_type}: ...')

        return '\n'.join(lines) + '\n'
