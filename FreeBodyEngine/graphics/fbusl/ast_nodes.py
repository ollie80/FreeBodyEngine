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

class Identifier(Node):
    def __init__(self, pos, name):
        super().__init__(pos)
        self.name = name
        
    def get_debug(self):
        return (f"Identifier('{self.name}')",)

class MethodIdentifier(Identifier):
    def __init__(self, pos, struct, method_name):
        super().__init__(pos, f"{struct}.{method_name}")
        self.struct = struct
        self.method_name = method_name
    def get_debug(self):
        return (f"MethodIdentifier('{self.method_name}')", self.struct)

class Buffer(Node):
    def __init__(self, pos, name: Identifier, fields: list):
        super().__init__(pos)
        self.name = name
        self.fields = fields
    
    def get_debug(self):
        return (f"Buffer", self.name, self.fields)

class Type(Node):
    def __init__(self, pos, name: Identifier, length=1):
        super().__init__(pos)
        self.name = name
        self.length = length
    
    def base_type(self):
        return Type(self.pos, self.name)

    def get_debug(self):
        return (f"Type('{self.name.name}'), len={self.length}",)

    def __eq__(self, other):
        if isinstance(other, Type):
            return other.name.name == self.name.name and other.length == self.length

    def __str__(self):
        if not self.length > 1:
            return f"Type({self.name.name})"
        else:
            return f"Type({self.name.name})[{self.length}]"


class BufferField(Node):
    def __init__(self, pos, name: Identifier, type: str):
        super().__init__(pos)
        self.name = name
        self.type = type

    def get_debug(self):
        return (f"BufferField {self.type}", self.name)


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
        return (f"VariableDeclaration", self.name, self.type, self.val)

class UniformDecl(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"UniformDeclaration", self.name, self.type)

class Get(Node):
    def __init__(self, pos, name: Identifier, array_access: bool, array_index=0):
        super().__init__(pos)
        self.name = name
        self.array_access = array_access
        self.array_index = array_index

    def get_debug(self):
        return (f"Get array={self.array_access}", self.name)
    
class MethodGet(Node):
    def __init__(self, pos, struct_name: Node, name: Identifier, array_access: bool, array_index=0):
        super().__init__(pos)
        self.struct_name = struct_name
        self.name = name                
        self.array_access = array_access
        self.array_index = array_index

    def get_debug(self):
        kind = "array" if self.array_access else "field"
        return (f"MethodGet ({kind}) to {self.name.name}", self.struct_name)


class InputDecl(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"InputDeclaration", self.name, self.type)

class OutputDecl(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"OutputDeclaration", self.name, self.type)

class Define(Node):
    def __init__(self, pos, name, val):
        super().__init__(pos)
        self.name = name
        self.val = val
    def get_debug(self):
        return (f"Definition", self.name, self.val)

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
        return (f"SetMethod", self.ident, self.method, self.value)

class Not(Node):
    def __init__(self, pos, node):
        super().__init__(pos)
        self.node = node
    def get_debug(self):
        return ("Not", self.node)

class And(Node):
    def __init__(self, pos, left, right):
        super().__init__(pos)
        self.left = left
        self.right = right
    def get_debug(self):
        return ("And", self.left, self.right)

class Or(Node):
    def __init__(self, pos, left, right):
        super().__init__(pos)
        self.left = left
        self.right = right
    def get_debug(self):
        return ("Or", self.left, self.right)

class IfStatement(Node):
    def __init__(self, pos, condition, body):
        super().__init__(pos)
        self.condition = condition
        self.body = body

    def get_debug(self):
        return ("IfStatement", self.condition, *self.body)

class ElseIfStatement(IfStatement):
    def get_debug(self):
        return ("ElseIfStatement", self.condition, *self.body)

class ElseStatement(Node):
    def __init__(self, pos, body):
        super().__init__(pos)
        self.body = body

    def get_debug(self):
        return ("ElseStatement", *self.body)

class Condition(Node):
    def __init__(self, pos, left, right, comparison):
        super().__init__(pos)
        self.left = left
        self.right = right
        self.comparison = comparison
    def get_debug(self):
        return (f"Condition('{self.comparison}')", self.left, self.right)

class TernaryExpression(Node):
    def __init__(self, pos, left, right, condition):
        super().__init__(pos)
        self.left = left
        self.right = right
        self.condition = condition
    def get_debug(self):
        return ("TernaryExpression", self.left, self.right, self.condition)

class Param(Node):
    def __init__(self, pos, name, type):
        super().__init__(pos)
        self.name = name
        self.type = type
    def get_debug(self):
        return (f"Param", self.name, self.type)

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
        return (f"Function -> {self.return_type}", self.name, *self.params, *self.body)

class StructField(Node):
    def __init__(self, pos, name, type, precision):
        super().__init__(pos)
        self.name = name
        self.type = type
        self.precision = precision
    def get_debug(self):
        return (f"Field", self.name, self.type)

class Call(Node):
    def __init__(self, pos, name, args):
        super().__init__(pos)
        self.name = name
        self.args = args
    def get_debug(self):
        return (f"Call", self.name, *self.args)

class Arg(Node):
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
        return (f"Struct", self.name, *self.methods)

class TypeCast(Node):
    def __init__(self, pos, target, type):
        super().__init__(pos)
        self.type = type
        self.target = target
    def get_debug(self):
        return ("TypeCast", self.target, self.type)

# Literals
class Int(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Integer({self.value})",)

class Float(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Float({self.value})",)

class Bool(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Boolean({self.value})",)

class Vec2(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Vector2({self.value})",)

class Vec3(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Vector3({self.value})",)

class Vec4(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Vector4({self.value})",)

class Mat2(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Matrix2x2({self.value})",)

class Mat3(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Matrix3x3({self.value})",)

class Mat4(Expression):
    def __init__(self, pos, value):
        super().__init__(pos)
        self.value = value
    def get_debug(self):
        return (f"Matrix4x4({self.value})",)