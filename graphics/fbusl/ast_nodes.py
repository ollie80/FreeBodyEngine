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
    pass

class Expression(Node):
    pass

class BinOp(Expression):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

    def get_debug(self):
        return (f"BinOp('{self.op}')", self.left, self.right)
  
class VarDecl(Node):
    def __init__(self, name, type, val, precision):
        self.name = name
        self.type = type
        self.val = val
        self.precision = precision

    def get_debug(self):

        return (f"VariableDeclaration('{self.name}', '{self.type}')", self.val)

class UniformDecl(Node):
    def __init__(self, name, type, precision):
        self.name = name
        self.type = type
        self.precision = precision

    def get_debug(self):
        return (f"UniformDeclaration('{self.name}', '{self.type}')",)

class InputDecl(Node):
    def __init__(self, name, type, precision):
        self.name = name
        self.type = type
        self.precision = precision

    def get_debug(self):
        return (f"InputDeclaration('{self.name}', '{self.type}')",)

class OutputDecl(Node):
    def __init__(self, name, type, precision):
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"OutputDeclaration('{self.name}', '{self.type}')",)

class Define(Node):
    def __init__(self, name, val):self.name=name;self.val=val;
    def get_debug(self):
        return (f"Definition('self.name')", self.val)

class Set(Node):
    def __init__(self, ident: 'Identifier', value: any):
        self.ident = ident
        self.value = value

    def get_debug(self):
        return (f"Set", self.ident, self.value)

class SetMethod(Set):
    def __init__(self, identifier: "Identifier", method: "Identifier", value: any):
        super().__init__(identifier, value)
        self.method = method
    def get_debug(self):
        return (f"SetMethod({self.identifier})", self.method, self.value)

class Type(Node):
    pass

class Param(Node):
    def __init__(self, name: str, type: str):
        self.name = name
        self.type = type

    def get_debug(self):
        return (f"Param({self.name}: {self.type})", )

class Return(Node):
    def __init__(self, expr: Expression):
        self.expr = expr

    def get_debug(self):
        return ("Return", self.expr)

class FuncDecl(Node):
    def __init__(self, name: str, return_type: str, params: list[Param], body: list[Node]):
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body

    def get_debug(self):
        return (f"Function('{self.name}') -> {self.return_type}", *self.params, *self.body)

class StructMethod(Node):
    def __init__(self, name: str, type: str, precision: str):
        self.name = name
        self.type = type
        self.precision = precision

    def get_debug(self):
        return (f"Method('{self.name}', '{self.type}')",)

class FuncCall(Node):
    def __init__(self, name, args):
        self.name = name
        self.args = args
    def get_debug(self):
        return (f"FunctionCall('{self.name}')", *self.args)

class FuncArg(Node):
    def __init__(self, val):
        self.val = val
    def get_debug(self):
        return (f"Argument '{self.val}'",)

class StructDecl(Node):
    def __init__(self, name: str, methods: list[StructMethod]):
        self.name = name
        self.methods = methods

    def get_debug(self):
        return (f"Struct('{self.name}')", *self.methods)

class Identifier(Type):
    def __init__(self, name: str):
        self.name = name

    def get_debug(self):
        return (f"Identifier('{self.name}')",)

class Int(Type):
    def __init__(self, value: int):
        self.value = value

    def get_debug(self):
        return (f"Integer({self.value})",)

class Float(Type):
    def __init__(self, value: float):
        self.value = value

    def get_debug(self):
        return (f"Float({self.value})",)

class Bool(Type):
    def __init__(self, value: bool):
        self.value = value
    
    def get_debug(self):
        return (f"Boolean({self.value})",)
    
class Vec2(Type):
    def __init__(self, value):
        self.value = value

    def get_debug(self):
        return (f"Vector2({self.value})")

class Vec3(Type):
    def __init__(self, value):
        self.value = value

    def get_debug(self):
        return (f"Vector3({self.value})")

class Vec4(Type):
    def __init__(self, value):
        self.value = value

    def get_debug(self):
        return (f"Vector4({self.value})")
    
class Mat2(Type):
    def __init__(self, value):
        self.value = value

    def get_debug(self):
        return (f"Matrix2x2({self.value})")

class Mat3(Type):
    def __init__(self, value):
        self.value = value

    def get_debug(self):
        return (f"Matrix3x3({self.value})")
    

class Mat4(Type):
    def __init__(self, value):
        self.value = value

    def get_debug(self):
        return (f"Matrix4x4({self.value})")
    