import re
from typing import List, Optional, Dict

class CppFunction:
    def __init__(self, name: str, params: dict[str, str] = {}, return_type: Optional[str] = None):
        self.name = name
        self.params = params or ""
        self.return_type = return_type or "None"

    def is_constructor(self, class_name: str) -> bool:
        return self.name == class_name

class CppClass:
    def __init__(self, name: str):
        self.name = name
        self.constructors: List[CppFunction] = []
        self.methods: List[CppFunction] = []
        self.attributes: List[str] = []

    def add_constructor(self, params: str):
        self.constructors.append(CppFunction(self.name, params))

    def add_method(self, name: str, return_type: str = "None"):
        if name != self.name:  # avoid constructor as method
            self.methods.append(CppFunction(name, return_type=return_type))

    def add_attribute(self, name: str):
        self.attributes.append(name)

class CppBindingGenerator:
    def __init__(self, source: str, module_name="my_module"):
        self.source = source
        self.module_name = module_name
        self.classes: List[CppClass] = []
        self.functions: List[CppFunction] = []
        
        self.type_map = {
            'void': 'None',
            'bool': 'bool',
            'int': 'int',
            'long': 'int',
            'std::string': 'str',
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
        lines = self.source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line == "//@bind" and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("class ") or next_line.startswith("struct "):
                    i = self._parse_class_or_struct(lines, i + 1)
                else:
                
                    func_match = re.match(r'([\w:<>&*\s]+)\s+([A-Za-z_]\w*)\s*\([^)]*\)', next_line)
                    if func_match:
                        params = next_line.split('(')[1].split(')')[0].split(',')
                        parsed_params = []
                        for param in params:
                            parsed_params.append({f'{param.split(' ')[0]}', f'{param.split(' ')[1]}'})                               
                        return_type = func_match.group(1).strip()
                        func_name = func_match.group(2).strip()

                        self.functions.append(CppFunction(func_name, parsed_params, return_type=return_type))
                    
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
                params = ctor_match.group(1).strip()
                cpp_class.add_constructor(params)
                nested_brace_depth += open_braces - close_braces
                continue

            method_pattern = r'([\w:<>&*\s]+)\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*(?:const)?\s*[;{]?'
            method_match = re.match(method_pattern, stripped)
            if method_match:
                return_type = method_match.group(1).strip()
                method_name = method_match.group(2).strip()
                if method_name != class_name and return_type and not return_type.startswith(class_name):
                    cpp_class.add_method(method_name, return_type)
                    nested_brace_depth += open_braces - close_braces
                    continue

            void_method_pattern = r'([A-Za-z_]\w*)\s*\([^)]*\)\s*(?:const)?\s*[;{]?'
            void_method_match = re.match(void_method_pattern, stripped)
            if void_method_match:
                method_name = void_method_match.group(1).strip()
                if method_name != class_name:
                    cpp_class.add_method(method_name, "void")
                    nested_brace_depth += open_braces - close_braces
                    continue

            attr_match = re.match(r'^([\w:<>&*\s,]+)\s+([A-Za-z_]\w*)\s*(=\s*[^;]+)?\s*;', stripped)
            if attr_match:
                attr_name = attr_match.group(2)
                cpp_class.add_attribute(attr_name)
                nested_brace_depth += open_braces - close_braces
                continue

            nested_brace_depth += open_braces - close_braces

        self.classes.append(cpp_class)
        return i


    def _parse_constructor_params(self, params: str) -> str:
        """Parse constructor parameters and extract types for pybind11"""
        if not params.strip():
            return ""
        
        param_parts = []
        current_param = ""
        angle_bracket_depth = 0
        
        for char in params:
            if char == '<':
                angle_bracket_depth += 1
            elif char == '>':
                angle_bracket_depth -= 1
            elif char == ',' and angle_bracket_depth == 0:
                param_parts.append(current_param.strip())
                current_param = ""
                continue
            current_param += char
        
        if current_param.strip():
            param_parts.append(current_param.strip())
        
        types = []
        for param in param_parts:
            param = param.strip()
            if not param:
                continue
                
            if '=' in param:
                param = param.split('=')[0].strip()
            
            words = param.split()
            if len(words) >= 2:
                type_part = ' '.join(words[:-1])
                types.append(type_part)
            elif len(words) == 1:
                types.append(words[0])
        
        return ', '.join(types)

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

    def generate_macro(self) -> str:
        lines = [f'#include <pybind11/pybind11.h>', "#include <pybind11/stl.h>", 'namespace py = pybind11;', '', f'PYBIND11_MODULE({self.module_name}, m) {{']

        for cls in self.classes:
            lines.append(f'    py::class_<{cls.name}>(m, "{cls.name}")')

            if cls.constructors:
                for ctor in cls.constructors:
                    if not ctor.params.strip():
                        lines.append(f'        .def(py::init<>())')
                    else:
                        param_types = self._parse_constructor_params(ctor.params)
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

    def generate_pyi(self) -> str:
        """Generate Python stub file (.pyi) for type checking"""
        lines = ['from typing import Any, overload', '', '']
        
        for cls in self.classes:
            lines.append(f'class {cls.name}:')
            
            if cls.constructors:
                for ctor in cls.constructors:
                    if not ctor.params.strip():
                        lines.append('    def __init__(self) -> None: ...')
                    else:
                        param_types = self._parse_constructor_params(ctor.params)
                        if param_types:
                            py_params = []
                            for i, param_type in enumerate(param_types.split(', ')):
                                py_type = self._cpp_to_python_type(param_type)
                                py_params.append(f'arg{i}: {py_type}')
                            param_str = ', '.join(py_params)
                            lines.append(f'    def __init__(self, {param_str}) -> None: ...')
                        else:
                            lines.append('    def __init__(self) -> None: ...')
            else:
                lines.append('    def __init__(self) -> None: ...')
            
            for method in cls.methods:
                return_type = self._cpp_to_python_type(method.return_type)
                params_str = ""
                i = 0
                for param_name, param_type in method.params:
                    python_param_type = self._cpp_to_python_type(param_type)

                    params_str += f"{param_name}: {python_param_type}"
                    if i != len(method.params) - 1:
                        param_str += ', '
                    i += 1

                lines.append(f'    def {method.name}(self, {params_str}) -> {return_type}: ...')
            
            for attr in cls.attributes:
                lines.append(f'    {attr}: Any')
            
            lines.append('')  
        
        for func in self.functions:
            
            return_type = self._cpp_to_python_type(func.return_type)
            
            params_str = ""
            i = 0
            for param_type, param_name in func.params:
                python_param_type = self._cpp_to_python_type(param_type)

                params_str += f"{param_name}: {python_param_type}"
                if i != len(func.params) - 1:
                    param_str += ', '

                i += 1
            
            lines.append(f'def {func.name}({params_str}) -> {return_type}: ...')
        
        return '\n'.join(lines)

    def generate(self) -> str:
        return self.source + "\n\n" + self.generate_macro()
    