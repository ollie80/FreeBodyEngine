"""A small SPIR-V module builder - just enough of the format for
SPIRVGenerator (graphics/vulkan/generator.py) to emit compute and
ray-query shaders directly, with no external compiler.

A SPIR-V module is a header followed by instructions in a fixed section
order (capabilities, extensions, imports, memory model, entry points,
execution modes, debug names, decorations, types/constants/globals,
functions). `Module` keeps one list per section and concatenates them in
that order at `encode()` time, so callers can add a capability or a type
whenever they discover they need one, without caring where in the file it
ends up.

Types and constants are de-duplicated (SPIR-V forbids two identical
non-aggregate type declarations), except structs and arrays, which callers
create explicitly because the same shape can legitimately need two
declarations with different layout decorations - see `type_struct`.

There's no validator in this toolchain, so `dump()` renders the module as
text in roughly the shape `spirv-dis` prints, which is what to read when a
driver rejects a module.
"""
import struct

MAGIC = 0x07230203

# Opcode numbers, from the SPIR-V 1.5 core grammar and SPV_KHR_ray_query.
OP = {
    "Undef": 1, "Source": 3, "Name": 5, "MemberName": 6, "Extension": 10,
    "ExtInstImport": 11, "ExtInst": 12, "MemoryModel": 14, "EntryPoint": 15,
    "ExecutionMode": 16, "Capability": 17,
    "TypeVoid": 19, "TypeBool": 20, "TypeInt": 21, "TypeFloat": 22,
    "TypeVector": 23, "TypeMatrix": 24, "TypeImage": 25, "TypeSampler": 26,
    "TypeSampledImage": 27, "TypeArray": 28, "TypeRuntimeArray": 29,
    "TypeStruct": 30, "TypePointer": 32, "TypeFunction": 33,
    "ConstantTrue": 41, "ConstantFalse": 42, "Constant": 43, "ConstantComposite": 44,
    "Function": 54, "FunctionParameter": 55, "FunctionEnd": 56, "FunctionCall": 57,
    "Variable": 59, "Load": 61, "Store": 62, "AccessChain": 65,
    "Decorate": 71, "MemberDecorate": 72,
    "VectorShuffle": 79, "CompositeConstruct": 80, "CompositeExtract": 81,
    "CompositeInsert": 82, "CopyObject": 83,
    "ImageSampleImplicitLod": 87, "ImageSampleExplicitLod": 88,
    "ImageRead": 98, "ImageWrite": 99,
    "ConvertFToS": 110, "ConvertSToF": 111, "Bitcast": 124,
    "SNegate": 126, "FNegate": 127, "IAdd": 128, "FAdd": 129, "ISub": 130,
    "FSub": 131, "IMul": 132, "FMul": 133, "SDiv": 135, "FDiv": 136,
    "SRem": 138, "FRem": 140, "FMod": 141,
    "VectorTimesScalar": 142, "MatrixTimesScalar": 143, "VectorTimesMatrix": 144,
    "MatrixTimesVector": 145, "MatrixTimesMatrix": 146, "Dot": 148,
    "LogicalEqual": 164, "LogicalNotEqual": 165, "LogicalOr": 166, "LogicalAnd": 167,
    "LogicalNot": 168, "Select": 169, "IEqual": 170, "INotEqual": 171,
    "SGreaterThan": 173, "SGreaterThanEqual": 175, "SLessThan": 177,
    "SLessThanEqual": 179, "FOrdEqual": 180, "FUnordNotEqual": 183,
    "FOrdLessThan": 184, "FOrdGreaterThan": 186, "FOrdLessThanEqual": 188,
    "FOrdGreaterThanEqual": 190,
    "ShiftRightLogical": 194, "ShiftRightArithmetic": 195, "ShiftLeftLogical": 196,
    "BitwiseOr": 197, "BitwiseXor": 198, "BitwiseAnd": 199, "Not": 200,
    "EmitVertex": 218, "EndPrimitive": 219, "ControlBarrier": 224, "AtomicExchange": 229, "AtomicIAdd": 234,
    "AtomicSMin": 236, "AtomicSMax": 238,
    "LoopMerge": 246, "SelectionMerge": 247, "Label": 248, "Branch": 249,
    "BranchConditional": 250, "Return": 253, "ReturnValue": 254, "Unreachable": 255,
    "TypeRayQueryKHR": 4472, "RayQueryInitializeKHR": 4473,
    "RayQueryTerminateKHR": 4474, "RayQueryProceedKHR": 4477,
    "RayQueryGetIntersectionTypeKHR": 4479,
    "TypeAccelerationStructureKHR": 5341,
    "RayQueryGetIntersectionTKHR": 6018,
    "RayQueryGetIntersectionInstanceCustomIndexKHR": 6019,
    "RayQueryGetIntersectionInstanceIdKHR": 6020,
    "RayQueryGetIntersectionGeometryIndexKHR": 6022,
    "RayQueryGetIntersectionPrimitiveIndexKHR": 6023,
    "RayQueryGetIntersectionBarycentricsKHR": 6024,
    "RayQueryGetIntersectionFrontFaceKHR": 6025,
}
OP_NAMES = {v: k for k, v in OP.items()}

# Enumerants.
CAP_SHADER = 1
CAP_GEOMETRY = 2
CAP_RAY_QUERY = 4472
STORAGE_UNIFORM_CONSTANT = 0
STORAGE_INPUT = 1
STORAGE_UNIFORM = 2
STORAGE_OUTPUT = 3
STORAGE_WORKGROUP = 4
STORAGE_PRIVATE = 6
STORAGE_FUNCTION = 7
STORAGE_STORAGE_BUFFER = 12
DEC_BLOCK = 2
DEC_COL_MAJOR = 5
DEC_ARRAY_STRIDE = 6
DEC_MATRIX_STRIDE = 7
DEC_FLAT = 14
DEC_BUILTIN = 11
DEC_LOCATION = 30
DEC_NON_WRITABLE = 24
DEC_NON_READABLE = 25
DEC_BINDING = 33
DEC_DESCRIPTOR_SET = 34
DEC_OFFSET = 35
BUILTIN_POSITION = 0
BUILTIN_POINT_SIZE = 1
BUILTIN_VERTEX_INDEX = 42
BUILTIN_INSTANCE_INDEX = 43
BUILTIN_NUM_WORKGROUPS = 24
BUILTIN_WORKGROUP_ID = 26
BUILTIN_LOCAL_INVOCATION_ID = 27
BUILTIN_GLOBAL_INVOCATION_ID = 28
EXEC_VERTEX = 0
EXEC_GEOMETRY = 3
EXEC_FRAGMENT = 4
EXEC_GLCOMPUTE = 5
MODE_INVOCATIONS = 0
MODE_ORIGIN_UPPER_LEFT = 7
# Geometry stage: input primitive, output primitive, max vertices.
MODE_GEOMETRY_INPUT = {"points": 19, "lines": 20, "lines_adjacency": 21, "triangles": 22,
                       "triangles_adjacency": 23}
MODE_GEOMETRY_OUTPUT = {"points": 27, "line_strip": 28, "triangle_strip": 29}
MODE_OUTPUT_VERTICES = 26
MODE_LOCAL_SIZE = 17
IMAGE_OPERAND_LOD = 0x2
DIM_2D = 1
IMAGE_FORMATS = {"rgba32f": 1, "rgba16f": 2, "r32f": 3, "rgba8": 4, "rg32f": 6, "r32i": 24}
SCOPE_DEVICE = 1
SCOPE_WORKGROUP = 2
SEMANTICS_ACQ_REL_WORKGROUP = 0x8 | 0x100

# GLSL.std.450 extended instructions.
GLSL = {
    "Round": 1, "FAbs": 4, "SAbs": 5, "FSign": 6, "Floor": 8, "Ceil": 9, "Fract": 10,
    "Sin": 13, "Cos": 14, "Tan": 15, "Asin": 16, "Acos": 17, "Atan": 18,
    "Atan2": 25, "Pow": 26, "Exp": 27, "Log": 28, "Sqrt": 31, "InverseSqrt": 32,
    "FMin": 37, "SMin": 39, "FMax": 40, "SMax": 42, "FClamp": 43, "SClamp": 45,
    "FMix": 46, "Step": 48, "SmoothStep": 49, "Length": 66, "Distance": 67,
    "Cross": 68, "Normalize": 69, "Reflect": 71, "Refract": 72,
}


def float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def int_bits(value: int) -> int:
    # Two's complement, wrapped to 32 bits - integer hashes legitimately use
    # constants past 2^31 (2654435761, say), which mean the same bits.
    return int(value) & 0xFFFFFFFF


def encode_string(text: str) -> list[int]:
    data = text.encode("utf-8") + b"\0"
    data += b"\0" * (-len(data) % 4)
    return list(struct.unpack(f"<{len(data) // 4}I", data))


class Instruction:
    __slots__ = ("op", "operands")

    def __init__(self, op: str, operands: list):
        self.op = op
        self.operands = operands

    def words(self) -> list[int]:
        body: list[int] = []
        for operand in self.operands:
            if isinstance(operand, str):
                body.extend(encode_string(operand))
            else:
                body.append(int(operand) & 0xFFFFFFFF)
        return [((len(body) + 1) << 16) | OP[self.op]] + body


class Module:
    SECTIONS = ("capabilities", "extensions", "imports", "memory_model", "entry_points",
                "execution_modes", "debug", "annotations", "globals", "functions")

    def __init__(self, version: tuple[int, int] = (1, 5)):
        self.version = version
        self.bound = 1
        self.sections: dict[str, list[Instruction]] = {name: [] for name in self.SECTIONS}
        self._capabilities: set[int] = set()
        self._extensions: set[str] = set()
        self._types: dict[tuple, int] = {}
        self._constants: dict[tuple, int] = {}
        self._glsl: int | None = None
        # Debug names, for dump(): id -> name.
        self.names: dict[int, str] = {}

    # -- basics --------------------------------------------------------------

    def id(self) -> int:
        value = self.bound
        self.bound += 1
        return value

    def emit(self, section: str, op: str, *operands) -> None:
        self.sections[section].append(Instruction(op, list(operands)))

    def name(self, target: int, text: str) -> None:
        self.names[target] = text
        self.emit("debug", "Name", target, text)

    def member_name(self, struct_id: int, index: int, text: str) -> None:
        self.emit("debug", "MemberName", struct_id, index, text)

    def decorate(self, target: int, decoration: int, *args) -> None:
        self.emit("annotations", "Decorate", target, decoration, *args)

    def member_decorate(self, struct_id: int, member: int, decoration: int, *args) -> None:
        self.emit("annotations", "MemberDecorate", struct_id, member, decoration, *args)

    def capability(self, cap: int) -> None:
        if cap not in self._capabilities:
            self._capabilities.add(cap)
            self.emit("capabilities", "Capability", cap)

    def extension(self, name: str) -> None:
        if name not in self._extensions:
            self._extensions.add(name)
            self.emit("extensions", "Extension", name)

    def glsl_std(self) -> int:
        if self._glsl is None:
            self._glsl = self.id()
            self.emit("imports", "ExtInstImport", self._glsl, "GLSL.std.450")
        return self._glsl

    # -- types ---------------------------------------------------------------

    def _type(self, key: tuple, op: str, *operands) -> int:
        existing = self._types.get(key)
        if existing is not None:
            return existing
        type_id = self.id()
        self._types[key] = type_id
        self.emit("globals", op, type_id, *operands)
        return type_id

    def type_void(self) -> int:
        return self._type(("void",), "TypeVoid")

    def type_bool(self) -> int:
        return self._type(("bool",), "TypeBool")

    def type_int(self, signed: bool = True) -> int:
        return self._type(("int", signed), "TypeInt", 32, 1 if signed else 0)

    def type_float(self) -> int:
        return self._type(("float",), "TypeFloat", 32)

    def type_vector(self, component: int, count: int) -> int:
        return self._type(("vec", component, count), "TypeVector", component, count)

    def type_matrix(self, column: int, count: int) -> int:
        return self._type(("mat", column, count), "TypeMatrix", column, count)

    def type_pointer(self, storage: int, pointee: int) -> int:
        return self._type(("ptr", storage, pointee), "TypePointer", storage, pointee)

    def type_function(self, result: int, params: list[int]) -> int:
        return self._type(("fn", result, tuple(params)), "TypeFunction", result, *params)

    def type_image_storage_2d(self, sampled_type: int, fmt: str) -> int:
        return self._type(("image", sampled_type, fmt), "TypeImage", sampled_type, DIM_2D,
                          0, 0, 0, 2, IMAGE_FORMATS[fmt])

    def type_image_sampled_2d(self, sampled_type: int, arrayed: bool = False) -> int:
        """A 2D image read through a sampler - format Unknown, as sampled
        images are."""
        return self._type(("image_sampled", sampled_type, arrayed), "TypeImage", sampled_type, DIM_2D,
                          0, 1 if arrayed else 0, 0, 1, 0)

    def type_sampled_image(self, image_type: int) -> int:
        return self._type(("sampled_image", image_type), "TypeSampledImage", image_type)

    def type_acceleration_structure(self) -> int:
        return self._type(("accel",), "TypeAccelerationStructureKHR")

    def type_ray_query(self) -> int:
        return self._type(("rayquery",), "TypeRayQueryKHR")

    def type_struct(self, members: list[int]) -> int:
        """Always a new declaration - see the module docstring."""
        type_id = self.id()
        self.emit("globals", "TypeStruct", type_id, *members)
        return type_id

    def type_array(self, element: int, length: int) -> int:
        """Always a new declaration, for the same reason as structs."""
        type_id = self.id()
        self.emit("globals", "TypeArray", type_id, element, self.constant_int(length, signed=False))
        return type_id

    def type_runtime_array(self, element: int) -> int:
        type_id = self.id()
        self.emit("globals", "TypeRuntimeArray", type_id, element)
        return type_id

    # -- constants -----------------------------------------------------------

    def constant(self, type_id: int, bits: int) -> int:
        key = ("const", type_id, bits)
        existing = self._constants.get(key)
        if existing is not None:
            return existing
        const_id = self.id()
        self._constants[key] = const_id
        self.emit("globals", "Constant", type_id, const_id, bits)
        return const_id

    def constant_int(self, value: int, signed: bool = True) -> int:
        return self.constant(self.type_int(signed), int_bits(value))

    def constant_float(self, value: float) -> int:
        return self.constant(self.type_float(), float_bits(value))

    def constant_bool(self, value: bool) -> int:
        key = ("bool", bool(value))
        existing = self._constants.get(key)
        if existing is not None:
            return existing
        const_id = self.id()
        self._constants[key] = const_id
        self.emit("globals", "ConstantTrue" if value else "ConstantFalse", self.type_bool(), const_id)
        return const_id

    def constant_composite(self, type_id: int, parts: list[int]) -> int:
        key = ("composite", type_id, tuple(parts))
        existing = self._constants.get(key)
        if existing is not None:
            return existing
        const_id = self.id()
        self._constants[key] = const_id
        self.emit("globals", "ConstantComposite", type_id, const_id, *parts)
        return const_id

    def undef(self, type_id: int) -> int:
        key = ("undef", type_id)
        existing = self._constants.get(key)
        if existing is not None:
            return existing
        undef_id = self.id()
        self._constants[key] = undef_id
        self.emit("globals", "Undef", type_id, undef_id)
        return undef_id

    def global_variable(self, pointer_type: int, storage: int) -> int:
        var_id = self.id()
        self.emit("globals", "Variable", pointer_type, var_id, storage)
        return var_id

    # -- output --------------------------------------------------------------

    def encode(self) -> bytes:
        major, minor = self.version
        words = [MAGIC, (major << 16) | (minor << 8), 0, self.bound, 0]
        for section in self.SECTIONS:
            for instruction in self.sections[section]:
                words.extend(instruction.words())
        return struct.pack(f"<{len(words)}I", *words)

    def dump(self) -> str:
        """The module as text, one instruction per line - for reading, not
        for feeding back into anything."""
        lines = [f"; SPIR-V {self.version[0]}.{self.version[1]}, bound {self.bound}"]
        for section in self.SECTIONS:
            for instruction in self.sections[section]:
                parts = []
                for operand in instruction.operands:
                    if isinstance(operand, str):
                        parts.append(repr(operand))
                    else:
                        label = self.names.get(operand)
                        parts.append(f"%{operand}" + (f"<{label}>" if label else ""))
                lines.append(f"{instruction.op:<32} {' '.join(parts)}")
        return "\n".join(lines)
