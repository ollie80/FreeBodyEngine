from typing import List, Optional, Dict, Union
from FreeBodyEngine.graphics.fbusl import Position
class ASTNode:
    def __init__(self, pos: Position = Position()):
        self.pos: Position = pos
        self.children: List['ASTNode'] = []
        self.type: Optional[dict] = None
        self.scope: Optional[Dict[str, str]] = None
        self.metadata: Dict[str, Union[str, int]] = {}
        self.value: Optional[Union[str, int, float]] = None

    def add_child(self, node: 'ASTNode'):
        self.children.append(node)

    def __repr__(self):
        return f"{self.__class__.__name__}(pos={self.pos})"


class Program(ASTNode):
    def __init__(self, pos: Position = Position()):
        super().__init__(pos)
        self.functions: List['FunctionDef'] = []
        self.outputs: List['OutputVar'] = []

    def __repr__(self):
        return f"Program(functions={self.functions}, outputs={self.outputs}, pos={self.pos})"


class FunctionDef(ASTNode):
    def __init__(self, name: str, body: List[ASTNode], return_type: str, params: List['FunctionParam'], overloads: Optional[List['FunctionParam']] = [], pos: Position = Position()):
        super().__init__(pos)
        self.name = name
        self.type = return_type
        self.params = params
        self.body: List[ASTNode] = body
        for node in self.body:
            self.add_child(node)
        self.overloads: List[Dict] = overloads

    def __repr__(self):
        return (f"FunctionDef(name={self.name}, return_type={self.type}, "
                f"params={self.params}, body={self.body}, overloads={self.overloads}, pos={self.pos})")

class FunctionParam(ASTNode):
    def __init__(self, name: str, var_type: dict, qualifier: str | None, pos: Position = Position()):
        super().__init__(pos)
        self.qualifier = qualifier
        self.name = name
        self.var_type = var_type
        

class VarDecl(ASTNode):
    def __init__(self, name: str, var_type: dict, value: Optional[ASTNode] = None, pos: Position = Position()):
        super().__init__(pos)
        self.name = name
        self.type = var_type
        self.value = value
        if value:
            self.add_child(value)

    def __repr__(self):
        return f"VarDecl(name={self.name}, type={self.type}, value={self.value}, pos={self.pos})"

class Setter(ASTNode):
    def __init__(self, node: ASTNode, to: ASTNode, pos: Position = Position()):
        super().__init__(pos)
        self.node = node
        self.to = to
        self.add_child(to)
    
    def __repr__(self):
        return f"Setter(node={self.node}, to={self.to}, pos={self.pos})"

class Output(ASTNode):
    def __init__(self, name: str, var_type: dict, qualifier: str, pos: Position = Position()):
        super().__init__(pos)
        self.name = name
        self.type = var_type
        self.qualifier = qualifier

    def __repr__(self):
        return f"Output(name={self.name}, type={self.type}, qualifier={self.qualifier}, pos={self.pos})"


class Input(ASTNode):
    def __init__(self, name: str, var_type: dict, qualifier: str, pos: Position = Position()):
        super().__init__(pos)
        self.name = name
        self.type = var_type
        self.qualifier = qualifier

    def __repr__(self):
        return f"Input(name={self.name}, type={self.type}, qualifier={self.qualifier}, pos={self.pos})"


class Uniform(ASTNode):
    def __init__(self, name: str, var_type: dict, qualifier: str, pos: Position = Position()):
        super().__init__(pos)
        self.name = name
        self.type = var_type
        self.qualifier = qualifier

    def __repr__(self):
        return f"Uniform(name={self.name}, type={self.type}, qualifier={self.qualifier}, pos={self.pos})"


class Define(ASTNode):
    def __init__(self, name: str, value: ASTNode, pos: Position = Position()):
        super().__init__(pos)
        self.name = name
        self.value = value

    def __repr__(self):
        return f"Define(name={self.name}, value={self.value}, pos={self.pos})"


class BinOp(ASTNode):
    def __init__(self, left: ASTNode, op: str, right: ASTNode, pos: Position = Position()):
        super().__init__(pos)
        self.left = left
        self.right = right
        self.op = op
        self.add_child(left)
        self.add_child(right)

    def __repr__(self):
        return f"BinOp(op={self.op}, left={self.left}, right={self.right}, pos={self.pos})"


class UnaryOp(ASTNode):
    def __init__(self, op: str, operand: ASTNode, pos: Position = Position()):
        super().__init__(pos)
        self.op = op
        self.operand = operand
        self.add_child(operand)

    def __repr__(self):
        return f"UnaryOp(op={self.op}, operand={self.operand}, pos={self.pos})"


class MemberAccess(ASTNode):
    def __init__(self, base: ASTNode, member: str, pos: Position = Position()):
        super().__init__()
        self.base = base
        self.member = member
        self.pos = pos
        self.add_child(base)

    def __repr__(self):
        return f"MemberAccess(base={self.base}, member={self.member}, pos={self.pos})"


class ArrayAccess(ASTNode):
    def __init__(self, base: ASTNode, index: ASTNode, pos: Position = Position()):
        super().__init__()
        self.base = base
        self.index = index
        self.pos = pos
        self.add_child(base)
        self.add_child(index)

    def __repr__(self):
        return f"ArrayAccess(base={self.base}, index={self.index}, pos={self.pos})"


class FuncCall(ASTNode):
    def __init__(self, func: ASTNode, args: List[ASTNode], pos: Position = Position()):
        super().__init__()
        self.func = func
        self.args = args
        self.pos = pos
        self.add_child(func)
        for arg in args:
            self.add_child(arg)

    def __repr__(self):
        return f"FuncCall(func={self.func}, args={self.args}, pos={self.pos})"


class Literal(ASTNode):
    def __init__(self, value: Union[int, float, bool], pos: Position = Position()):
        super().__init__(pos)
        self.value = value
        if isinstance(value, int):
            self.type = "int"
        elif isinstance(value, float):
            self.type = "float"
        elif isinstance(value, bool):
            self.type = "bool"

    def __repr__(self):
        return f"Literal(value={self.value}, type={self.type}, pos={self.pos})"


class Identifier(ASTNode):
    def __init__(self, name: str, pos: Position = Position()):
        super().__init__(pos)
        self.value = name

    def __repr__(self):
        return f"Identifier(name={self.value}, pos={self.pos})"
