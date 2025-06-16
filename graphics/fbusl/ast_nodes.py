class Tree:
    def __init__(self):
        self.children = []
    
    def build_tree_lines(self, node_repr, prefix="", is_last=True):
        label = node_repr[0]
        lines = [prefix + ("└── " if is_last else "├── ") + label]
        children = node_repr[1:]
        for i, child in enumerate(children):
            is_child_last = i == len(children) - 1
            if isinstance(child, Node):
                
                lines += self.build_tree_lines(child.get_debug(),
                    prefix + ("    " if is_last else "│   "),
                    is_child_last
                )
            else:
                # Leaf node
                lines.append(
                    prefix + ("    " if is_last else "│   ") +
                    ("└── " if is_child_last else "├── ") + str(child)
                )
        return lines

    def __str__(self):

        if not self.children:
            return ""

        lines = []
        for i, child in enumerate(self.children):
            is_last = i == len(self.children) - 1
            lines += self.build_tree_lines(child.get_debug(), "", is_last)

        return "\n".join(lines)

class Node:
    def __init__(self, pos: int):
        self.pos = pos

class Expression(Node):
    def __init__(self, pos: int):
        super().__init__(pos)

class BinOp(Expression):
    def __init__(self, pos: int, left, op, right):
        super().__init__(pos)
        self.left = left
        self.op = op
        self.right = right
    def get_debug(self):
        return (f"BinOp('{self.op}')", self.left, self.right)

class VarDecl(Node):
    def __init__(self, pos, name, type, val, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.val = val
        self.precision = precision
    def get_debug(self):
        return (f"VariableDeclaration('{self.name}', '{self.type}')", self.val)

class UniformDecl(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"UniformDeclaration('{self.name}', '{self.type}')",)

class InputDecl(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"InputDeclaration('{self.name}', '{self.type}')",)

class OutputDecl(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"OutputDeclaration('{self.name}', '{self.type}')",)

class Define(Node):
    def __init__(self, pos, name, val):
        super().__init__(pos)
        self.name = name
        self.val = val
    def get_debug(self):
        return (f"Definition('{self.name}')", self.val)

class Set(Node):
    def __init__(self, pos, ident, value):
        super().__init__(pos)
        self.ident = ident
        self.value = value
    def get_debug(self):
        return ("Set", self.ident, self.value)

class SetMethod(Set):
    def __init__(self, pos, identifier, method, value):
        super().__init__(pos, identifier, value)
        self.method = method
    def get_debug(self):
        return (f"SetMethod({self.ident})", self.method, self.value)

class Type(Node):
    def __init__(self, pos):
        super().__init__(pos)

class Param(Node):
    def __init__(self, pos, name, type):
        super().__init__(pos)
        self.name = name
        self.type = type
    def get_debug(self):
        return (f"Param({self.name}: {self.type})",)

class Return(Node):
    def __init__(self, pos, expr):
        super().__init__(pos)
        self.expr = expr
    def get_debug(self):
        return ("Return", self.expr)

class FuncDecl(Node):
    def __init__(self, pos, name, return_type, params, body):
        super().__init__(pos)
        self.name = name
        self.return_type = return_type
        self.params = params
        self.body = body
    def get_debug(self):
        return (f"Function('{self.name}') -> {self.return_type}", *self.params, *self.body)

class StructField(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"Field('{self.name}', '{self.type}')",)

class FuncCall(Node):
    def __init__(self, pos, name, args):
        super().__init__(pos)
        self.name = name
        self.args = args
    def get_debug(self):
        return (f"FunctionCall('{self.name}')", *self.args)

class FuncArg(Node):
    def __init__(self, pos, val):
        super().__init__(pos)
        self.val = val
    def get_debug(self):
        return ("Argument", self.val)

class StructDecl(Node):
    def __init__(self, pos, name, methods):
        super().__init__(pos)
        self.name = name
        self.methods = methods
    def get_debug(self):
        return (f"Struct('{self.name}')", *self.methods)

class Identifier(Type):
    def __init__(self, pos, name):
        super().__init__(pos)
        self.name = name
    def get_debug(self):
        return (f"Identifier('{self.name}')",)

class MethodIdentifier(Identifier):
    def __init__(self, pos, struct_name, method_name):
        super().__init__(pos, f"{struct_name}.{method_name}")
        self.struct_name = struct_name
        self.method_name = method_name
    def get_debug(self):
        return (f"MethodIdentifier('{self.struct_name}.{self.method_name}')",)

class Int(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Integer({self.value})",)

class Float(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Float({self.value})",)

class Bool(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Boolean({self.value})",)

class Vec2(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Vector2({self.value})",)

class Vec3(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Vector3({self.value})",)

class Vec4(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Vector4({self.value})",)

class Mat2(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Matrix2x2({self.value})",)

class Mat3(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Matrix3x3({self.value})",)

class Mat4(Type):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Matrix4x4({self.value})",)
