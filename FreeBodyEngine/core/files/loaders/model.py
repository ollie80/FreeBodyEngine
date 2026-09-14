import struct
import json
import io
import base64
from pathlib import PurePosixPath
from urllib.parse import unquote

import numpy as np
from PIL import Image

from json import loads

from FreeBodyEngine import get_service
from FreeBodyEngine.graphics.model import Model
from FreeBodyEngine.graphics.mesh import create_static_mesh
from FreeBodyEngine.core.files.resource import FileResource
from FreeBodyEngine.core.files import get_file, load_file


class GLBParser:
    """Splits a `.glb` (binary glTF) blob into its JSON and binary chunks,
    per the glTF 2.0 binary container spec - the JSON chunk always comes
    first and is required, the BIN chunk is optional and, when present,
    always second."""
    def __init__(self, data_bytes):
        """Parses `data_bytes` immediately - raises ValueError if it isn't a
        valid, version-2 `.glb` container, or if its declared length
        exceeds the actual data."""
        self.bytes = data_bytes
        self.json_chunk = None
        self.bin_chunk = None
        self._parse()

    def _parse(self):
        if len(self.bytes) < 12:
            raise ValueError("Invalid GLB: file is too small")

        magic, version, length = struct.unpack_from(
            "<4sII", self.bytes, 0
        )

        if magic != b"glTF":
            raise ValueError("Not a valid .glb file")

        if version != 2:
            raise ValueError("Only glTF 2.0 is supported")

        if length > len(self.bytes):
            raise ValueError("Invalid GLB: declared length exceeds file")

        offset = 12

        # JSON chunk
        chunk_length, chunk_type = struct.unpack_from(
            "<I4s", self.bytes, offset
        )
        offset += 8

        if chunk_type != b"JSON":
            raise ValueError("First GLB chunk must be JSON")

        json_bytes = self.bytes[offset:offset + chunk_length]
        self.json_chunk = json.loads(
            json_bytes.decode("utf-8").rstrip("\x00 ")
        )

        offset += chunk_length

        # BIN chunk
        if offset + 8 <= len(self.bytes):
            chunk_length, chunk_type = struct.unpack_from(
                "<I4s", self.bytes, offset
            )
            offset += 8

            if chunk_type == b"BIN\x00":
                self.bin_chunk = self.bytes[
                    offset:offset + chunk_length
                ]

    def get_json(self):
        """Returns the parsed glTF JSON document (the same schema a `.gltf`
        text file contains)."""
        return self.json_chunk

    def get_binary_buffer(self):
        """Returns the raw BIN chunk bytes, or `b""` if the file had none."""
        return self.bin_chunk or b""


class GLTFParser:
    """Builds a Model from a parsed glTF JSON document (`gltf_dict`) plus
    its binary buffer data - works for both `.gltf` (with `bin_data` either
    empty or decoded from a `data:` URI) and `.glb` (with `bin_data` from
    GLBParser.get_binary_buffer()). `base_path` is the directory the source
    file lives in, needed to resolve any `uri` that points at an external
    sibling file (a separate `.bin` or image) rather than embedding its data
    inline."""

    _NORMALIZED_MAX = {
        5120: 127.0,
        5121: 255.0,
        5122: 32767.0,
        5123: 65535.0,
    }

    COMPONENT_FORMAT = {
        5120: "b",
        5121: "B",
        5122: "h",
        5123: "H",
        5125: "I",
        5126: "f",
    }

    # Same keys as COMPONENT_FORMAT, as NumPy dtypes instead of struct.
    # format chars - lets get_accessor_data() reinterpret the raw buffer
    # directly instead of unpacking one element at a time in Python.
    NUMPY_DTYPE = {
        5120: np.int8,
        5121: np.uint8,
        5122: np.int16,
        5123: np.uint16,
        5125: np.uint32,
        5126: np.float32,
    }

    NUM_COMPONENTS = {
        "SCALAR": 1,
        "VEC2": 2,
        "VEC3": 3,
        "VEC4": 4,
        "MAT2": 4,
        "MAT3": 9,
        "MAT4": 16,
    }

    def __init__(self, gltf_dict, bin_data, base_path=None):
        """Stores the parsed inputs; does no work itself - see the class docstring."""
        self.gltf = gltf_dict
        self.bin_data = bin_data or b""
        self.base_path = base_path

    # ------------------------------------------------------------
    # Buffer/accessor loading
    # ------------------------------------------------------------

    def _get_buffer_data(self, buffer_index):
        buffers = self.gltf.get("buffers", [])

        if buffer_index >= len(buffers):
            raise IndexError(f"Invalid buffer index {buffer_index}")

        buffer = buffers[buffer_index]

        # GLB buffer
        if "uri" not in buffer:
            return self.bin_data

        uri = buffer["uri"]

        if uri.startswith("data:"):
            _, encoded = uri.split(",", 1)
            return base64.b64decode(encoded)

        if self.base_path is None:
            raise RuntimeError(
                f"External buffer '{uri}' requires a base path"
            )

        path = str(PurePosixPath(self.base_path) / unquote(uri))

        return get_file(path).read(bytes=True)

    def get_accessor_data(self, accessor_index):
        """Returns a (count, num_components) NumPy array for the accessor -
        every caller already immediately wraps this in np.asarray()/
        np.array(), so returning an array directly (instead of a Python
        list of tuples) is a transparent change, not an API break.

        Reinterprets the raw buffer bytes straight into a strided NumPy
        view (np.ndarray(buffer=...)) rather than calling struct.unpack()
        once per element in a Python loop - for a glTF file with real
        vertex counts (tens of thousands to low millions for a detailed
        mesh), that per-element Python loop dominates load time; this does
        the equivalent reinterpretation as a single C-level pass.
        """

        accessor = self.gltf["accessors"][accessor_index]

        # Sparse accessors are not handled by this simple implementation.
        if "sparse" in accessor:
            raise NotImplementedError(
                "Sparse glTF accessors are not supported yet"
            )

        num_components = self.NUM_COMPONENTS[accessor["type"]]
        count = accessor["count"]

        buffer_view_index = accessor.get("bufferView")

        if buffer_view_index is None:
            # Accessors without bufferView are zero initialized.
            return np.zeros((count, num_components), dtype=np.float32)

        buffer_view = self.gltf["bufferViews"][buffer_view_index]

        buffer_index = buffer_view.get("buffer", 0)

        buffer_data = self._get_buffer_data(buffer_index)

        buffer_offset = buffer_view.get("byteOffset", 0)
        accessor_offset = accessor.get("byteOffset", 0)

        total_offset = buffer_offset + accessor_offset

        component_type = accessor["componentType"]
        normalized = accessor.get("normalized", False)

        dtype = self.NUMPY_DTYPE[component_type]
        component_size = np.dtype(dtype).itemsize

        element_size = num_components * component_size

        byte_stride = buffer_view.get(
            "byteStride",
            element_size
        )

        required_bytes = total_offset + byte_stride * max(count - 1, 0) + element_size
        if required_bytes > len(buffer_data):
            raise ValueError(
                f"Accessor {accessor_index} ran past buffer "
                f"(wanted {required_bytes} bytes, buffer has {len(buffer_data)})"
            )

        # A strided view straight over the raw bytes - `strides` walks
        # `byte_stride` bytes between elements (which equals `element_size`
        # for tightly-packed data, the common case) and `component_size`
        # bytes between an element's own components. `buffer_data` may be
        # a plain `bytes` object, which is read-only, so this view would be
        # too - copied immediately below since build_model() and callers
        # elsewhere mutate an accessor's returned array in place (e.g. the
        # V-flip on UVs a bit further down), and `np.asarray(x, dtype=x.dtype)`
        # (used there) returns `x` itself with no copy when the dtype
        # already matches, unlike `np.array()`. The original struct.unpack-
        # per-element implementation this replaces always produced a fresh,
        # independent list too, so this preserves that same "never aliases
        # the source buffer" contract.
        values = np.ndarray(
            shape=(count, num_components),
            dtype=dtype,
            buffer=buffer_data,
            offset=total_offset,
            strides=(byte_stride, component_size),
        ).copy()

        if normalized:
            norm_divisor = self._NORMALIZED_MAX[component_type]
            values = values.astype(np.float32) / norm_divisor
            if dtype in (np.int8, np.int16):
                values = np.maximum(values, -1.0)

        return values

    # ------------------------------------------------------------
    # Image loading
    # ------------------------------------------------------------

    def get_image_data(self, image_index):
        """Returns the raw encoded bytes (PNG/JPEG, not yet decoded) of
        image `image_index` - from the GLB BIN chunk, a base64 `data:` URI,
        or (only when `base_path` was given) an external sibling file."""

        image = self.gltf["images"][image_index]

        # Embedded image in GLB BIN
        if "bufferView" in image:

            buffer_view = self.gltf["bufferViews"][
                image["bufferView"]
            ]

            buffer_index = buffer_view.get("buffer", 0)

            buffer_data = self._get_buffer_data(buffer_index)

            offset = buffer_view.get("byteOffset", 0)
            length = buffer_view["byteLength"]

            return buffer_data[offset:offset + length]

        # URI image
        if "uri" in image:

            uri = image["uri"]

            # Embedded base64 image
            if uri.startswith("data:"):

                header, encoded = uri.split(",", 1)

                return base64.b64decode(encoded)

            # External image
            if self.base_path is None:
                raise RuntimeError(
                    f"External texture '{uri}' requires a base path"
                )

            image_path = str(
                PurePosixPath(self.base_path) / unquote(uri)
            )

            try:
                return get_file(image_path).read(bytes=True)

            except Exception as e:
                raise RuntimeError(
                    f"Failed to load glTF texture:\n"
                    f"  URI: {uri}\n"
                    f"  Resolved: {image_path}\n"
                    f"  Error: {e}"
                ) from e

        raise ValueError(
            f"Image {image_index} has neither bufferView nor URI"
        )

    # ------------------------------------------------------------
    # Texture resolution
    # ------------------------------------------------------------

    def _get_texture_image_index(self, texture_index):

        textures = self.gltf.get("textures", [])

        if texture_index is None:
            return None

        if texture_index < 0 or texture_index >= len(textures):
            return None

        texture = textures[texture_index]

        # Normal glTF texture
        if "source" in texture:
            return texture["source"]

        # KHR_texture_basisu
        if "extensions" in texture:
            basisu = texture["extensions"].get(
                "KHR_texture_basisu"
            )

            if basisu and "source" in basisu:
                return basisu["source"]

        return None

    def resolve_texture(self, texture_ref, textures):
        """Looks a glTF texture reference (e.g. a material's
        `baseColorTexture`, `{"index": ..., "texCoord": ...}`) up in
        `textures` (an image-index -> loaded-Texture map, as built by
        build_model()) and returns the resolved Texture, or None if
        `texture_ref` is None or names a texture/image that doesn't
        exist."""

        if texture_ref is None:
            return None

        texture_index = texture_ref.get("index")

        image_index = self._get_texture_image_index(
            texture_index
        )

        if image_index is None:
            return None

        return textures.get(image_index)

    # ------------------------------------------------------------
    # Materials
    # ------------------------------------------------------------

    def build_materials(self, renderer, pipeline):
        """Builds a real Material (via `pipeline.create_material()`) for
        every entry in the glTF's `materials` array, keyed by material name
        (a generated `material_{i}` for an unnamed one, or `{name}_{i}` if
        that name collides with an earlier material). Relies on
        `self._textures` (image_index -> loaded Texture) already being
        populated - build_model() always builds textures before calling
        this. Note glTF's own default `baseColorFactor`/`roughnessFactor`/
        etc. are white/rough/metallic, not black - this mirrors those
        defaults exactly rather than reusing whatever this engine's own
        Material default happens to be."""

        materials = {}

        gltf_materials = self.gltf.get("materials", [])

        for i, material in enumerate(gltf_materials):

            # IMPORTANT:
            # glTF defaults are NOT black.
            data = {
                "albedo": [1.0, 1.0, 1.0, 1.0],
                "normal": [0.0, 0.0, 1.0, 1.0],
                "emmisive": [0.0, 0.0, 0.0, 1.0],
                "roughness": 1.0,
                "metallic": 1.0,
            }

            pbr = material.get(
                "pbrMetallicRoughness",
                {}
            )

            # Base color
            if "baseColorFactor" in pbr:
                data["albedo"] = pbr["baseColorFactor"]

            if "baseColorTexture" in pbr:

                tex = self.resolve_texture(
                    pbr["baseColorTexture"],
                    self._textures
                )

                if tex is not None:
                    data["albedo"] = tex

            # Metallic
            if "metallicFactor" in pbr:
                data["metallic"] = pbr["metallicFactor"]

            # Roughness
            if "roughnessFactor" in pbr:
                data["roughness"] = pbr["roughnessFactor"]

            # Metallic/roughness texture
            #
            # IMPORTANT:
            # Keep the original packed texture.
            #
            # glTF:
            #   G = roughness
            #   B = metallic
            #
            # Your PBR shader should sample the appropriate
            # channels rather than us converting the image.
            if "metallicRoughnessTexture" in pbr:

                tex = self.resolve_texture(
                    pbr["metallicRoughnessTexture"],
                    self._textures
                )

                if tex is not None:

                    data["metallic"] = tex
                    data["roughness"] = tex

            # Normal
            if "normalTexture" in material:

                tex = self.resolve_texture(
                    material["normalTexture"],
                    self._textures
                )

                if tex is not None:
                    data["normal"] = tex

            # Emissive
            if "emissiveTexture" in material:

                tex = self.resolve_texture(
                    material["emissiveTexture"],
                    self._textures
                )

                if tex is not None:
                    data["emmisive"] = tex

            elif "emissiveFactor" in material:

                factor = material["emissiveFactor"]

                data["emmisive"] = [
                    factor[0],
                    factor[1],
                    factor[2],
                    1.0
                ]

            material_name = (
                material.get("name")
                or f"material_{i}"
            )

            if material_name in materials:
                material_name = (
                    f"{material_name}_{i}"
                )

            

            materials[material_name] = (
                pipeline.create_material(
                    data,
                    None
                )
            )

        return materials

    # ------------------------------------------------------------
    # Model
    # ------------------------------------------------------------

    def build_model(
        self,
        model_name=None,
        scale=None
    ):
        """Builds a Model from this glTF: every image is decoded and
        uploaded once and every material is built once, both cached on
        `self` (as `_textures`/`_materials`) so calling build_model()
        again on the same parser - e.g. once per piece of a multi-mesh
        file like a glTF chess set - doesn't redo that work.

        `model_name` selects which mesh(es) to include: None (the default)
        combines every mesh in the file into one Model, a string selects
        the mesh with that exact `name` (raising ValueError if none
        matches), and an int selects the mesh at that index directly -
        needed because glTF mesh names aren't guaranteed unique. `scale`,
        if given, is applied to every included mesh's raw vertex
        positions.

        Raises ValueError if the glTF has no meshes at all, or if
        `model_name` doesn't resolve to any mesh."""

        renderer = get_service("renderer")
        pipeline = get_service("graphics")

        if not self.gltf.get("meshes"):
            raise ValueError(
                "glTF contains no meshes"
            )

        # --------------------------------------------------------
        # Load every image exactly once - cached on `self` so calling
        # build_model() repeatedly on the same parser (e.g. once per piece
        # of a multi-mesh file like a glTF chess set) decodes and uploads
        # each image only the first time, not once per call.
        # --------------------------------------------------------

        textures = getattr(self, "_textures", None)

        if textures is None:

            textures = {}

            for image_index in range(
                len(self.gltf.get("images", []))
            ):

                try:

                    image_data = self.get_image_data(
                        image_index
                    )

                    textures[image_index] = (
                        renderer.texture_manager
                        ._create_standalone_texture(
                            image_data
                        )
                    )

                    print(
                        f"[glTF] Loaded image "
                        f"{image_index} "
                        f"({len(image_data)} bytes)"
                    )

                except Exception as e:

                    print(
                        f"[glTF] FAILED image "
                        f"{image_index}: {e}"
                    )

            self._textures = textures

        # --------------------------------------------------------
        # Materials - likewise cached per-parser, since every material in
        # the file is rebuilt (and its shader recompiled) up front
        # regardless of which single mesh is being requested this call.
        # --------------------------------------------------------

        materials = getattr(self, "_materials", None)

        if materials is None:
            materials = self.build_materials(
                renderer,
                pipeline
            )
            self._materials = materials

        # Material index -> material name
        material_index_to_name = {}

        for i, material in enumerate(
            self.gltf.get("materials", [])
        ):

            name = (
                material.get("name")
                or f"material_{i}"
            )

            if name in materials:
                material_index_to_name[i] = name

            else:
                material_index_to_name[i] = (
                    f"{name}_{i}"
                )

        # --------------------------------------------------------
        # Meshes
        # --------------------------------------------------------

        meshes = {}
        material_map = {}

        mesh_entries = list(enumerate(self.gltf["meshes"]))
        if isinstance(model_name, int):
            # glTF mesh *names* aren't guaranteed unique (e.g. a chess set
            # exported with both King meshes literally named "King_Shared")
            # - an integer selects one mesh by its actual index instead,
            # unambiguous regardless of duplicate names.
            mesh_entries = [(i, m) for i, m in mesh_entries if i == model_name]
            if not mesh_entries:
                raise ValueError(f"No mesh at index {model_name} in glTF")
        elif model_name is not None:
            mesh_entries = [
                (i, m) for i, m in mesh_entries
                if m.get("name") == model_name
            ]
            if not mesh_entries:
                raise ValueError(
                    f"No mesh named '{model_name}' in glTF"
                )

        for gltf_mesh_index, model in mesh_entries:

            for primitive_index, primitive in enumerate(
                model.get("primitives", [])
            ):

                attributes = primitive["attributes"]

                # Position
                pos_accessor = attributes["POSITION"]

                positions = np.asarray(
                    self.get_accessor_data(
                        pos_accessor
                    ),
                    dtype=np.float32
                )

                if scale is not None:
                    positions *= np.asarray(
                        scale,
                        dtype=np.float32
                    )

                # Normals
                normal_accessor = attributes.get(
                    "NORMAL"
                )

                if normal_accessor is not None:

                    normals = np.asarray(
                        self.get_accessor_data(
                            normal_accessor
                        ),
                        dtype=np.float32
                    )

                else:
                    normals = None

                # ------------------------------------------------
                # Material
                # ------------------------------------------------

                material_index = primitive.get(
                    "material"
                )

                material_name = "default"

                if material_index is not None:

                    material_name = (
                        material_index_to_name.get(
                            material_index,
                            "default"
                        )
                    )

                # ------------------------------------------------
                # UV set
                # ------------------------------------------------

                uv_set_index = 0

                if material_index is not None:

                    material = self.gltf[
                        "materials"
                    ][material_index]

                    base_color_tex = (
                        material
                        .get(
                            "pbrMetallicRoughness",
                            {}
                        )
                        .get(
                            "baseColorTexture"
                        )
                    )

                    if base_color_tex is not None:

                        uv_set_index = (
                            base_color_tex.get(
                                "texCoord",
                                0
                            )
                        )

                uv_accessor = attributes.get(
                    f"TEXCOORD_{uv_set_index}"
                )

                if uv_accessor is not None:

                    uvs = np.asarray(
                        self.get_accessor_data(
                            uv_accessor
                        ),
                        dtype=np.float32
                    )
                    uvs[:, 1] = 1.0 - uvs[:, 1]
                    uvs[:, 0] = 1.0 - uvs[:, 0]
                    # DO NOT flip here.
                    #
                    # The texture loader should decide whether
                    # the image itself is vertically flipped.
                    #
                    # Flipping the UVs here can cause the same
                    # texture to be flipped twice.
                    #
                    # uvs[:, 1] = 1.0 - uvs[:, 1]

                else:

                    uvs = None

                # ------------------------------------------------
                # Indices
                # ------------------------------------------------

                if "indices" in primitive:

                    indices = np.asarray(
                        self.get_accessor_data(
                            primitive["indices"]
                        ),
                        dtype=np.uint32
                    )

                else:

                    # Non-indexed primitive
                    indices = np.arange(
                        len(positions),
                        dtype=np.uint32
                    )

                mesh_name = (
                    f"Mesh_{gltf_mesh_index}"
                    f"_{primitive_index}"
                )

                meshes[mesh_name] = (
                    create_static_mesh(
                        positions,
                        uvs,
                        normals,
                        indices
                    )
                )

                material_map[mesh_name] = (
                    material_name
                )

                
        if not meshes:
            raise ValueError(
                "glTF contains no mesh primitives"
            )

        return Model(
            meshes,
            material_map,
            materials
        )

# build/builder.py's build_models() pre-bakes every project model it finds
# into a flat `.fbmesh` (see bake_gltf_to_fbmesh() below) and records
# {original_relative_path: built_relative_path} in this manifest - same
# convention as FONT_MANIFEST_KEY in loaders/font.py. `None` means "not
# checked yet"; `{}` means "checked, nothing built" (dev mode never writes
# this file at all) - both cached so a missing manifest is only looked up
# once per process.
MODEL_MANIFEST_KEY = "_ENGINE_model_manifest.json"
_MODEL_MANIFEST: dict[str, str] | None = None


def _load_model_manifest() -> dict[str, str]:
    global _MODEL_MANIFEST
    if _MODEL_MANIFEST is not None:
        return _MODEL_MANIFEST

    manifest_file = get_file(MODEL_MANIFEST_KEY)
    content = manifest_file.read() if manifest_file is not None else ""
    try:
        # DevFileSystem.get_file() on a path that doesn't exist yet
        # (true for any project that hasn't run a dev/release build since
        # this manifest was introduced) auto-creates an empty stub file
        # there when writes are permitted (true by default in dev mode) -
        # `manifest_file` then comes back non-None but empty, not None,
        # so this can't just be an `if manifest_file is not None` check.
        _MODEL_MANIFEST = loads(content) if content else {}
    except ValueError:
        _MODEL_MANIFEST = {}
    return _MODEL_MANIFEST


def bake_gltf_to_fbmesh(parser: 'GLTFParser', image_name_prefix: str) -> tuple[bytes, dict[str, bytes]]:
    """Pre-decodes every mesh primitive and material in `parser`'s glTF into
    a flat `.fbmesh`: a `b"FBMH"` magic, a little-endian uint32 giving the
    length of a JSON header, that header, then a binary blob the header's
    per-array `{"offset", "length"}` entries point into (each array 4-byte
    aligned within the blob, so a reader can `np.frombuffer()` straight over
    it with no copy or re-parse - see load_baked_model()).

    This is intentionally independent of build_model()/build_materials()
    above: those call `get_service('renderer')`/`get_service('graphics')`
    to create real GL textures/materials immediately, which needs a live
    GL context this build-time tool never has. Baked materials instead
    reference textures by *path* - embedded images are extracted to real
    files (returned as {relative_name: bytes} for the caller to bundle
    alongside everything else) and loaded back through the normal
    load_file()/load_texture() path at runtime, the same as any other
    project image (including, in a release build, that image's own shared-
    atlas packing).

    Some material-building logic (default values, factor-vs-texture
    resolution) is deliberately mirrored from build_materials() rather than
    shared with it, since that version is wired directly to GL object
    creation - keep the two in sync by hand if glTF material handling ever
    changes.
    """
    gltf = parser.gltf
    images_out: dict[str, bytes] = {}
    image_paths: dict[int, str] = {}

    for image_index in range(len(gltf.get("images", []))):
        data = parser.get_image_data(image_index)
        ext = ".jpg" if data[:2] == b"\xff\xd8" else ".png"
        name = f"{image_name_prefix}_{image_index}{ext}"
        images_out[name] = data
        image_paths[image_index] = name

    def resolve_tex(tex_ref):
        """Resolves a glTF texture reference to the baked image filename recorded in `image_paths` above, or None if `tex_ref` is None or names a texture/image absent from the file - mirrors `GLTFParser.resolve_texture()`, but returns a path string instead of a loaded Texture since no GL context exists at bake time."""
        if tex_ref is None:
            return None
        image_index = parser._get_texture_image_index(tex_ref.get("index"))
        return image_paths.get(image_index) if image_index is not None else None

    materials: dict[str, dict] = {}
    material_index_to_name: dict[int, str] = {}

    for i, material in enumerate(gltf.get("materials", [])):
        data = {
            "albedo": [1.0, 1.0, 1.0, 1.0],
            "normal": [0.0, 0.0, 1.0, 1.0],
            "emmisive": [0.0, 0.0, 0.0, 1.0],
            "roughness": 1.0,
            "metallic": 1.0,
        }

        pbr = material.get("pbrMetallicRoughness", {})
        if "baseColorFactor" in pbr:
            data["albedo"] = pbr["baseColorFactor"]
        base_color_tex = resolve_tex(pbr.get("baseColorTexture"))
        if base_color_tex is not None:
            data["albedo"] = {"texture": base_color_tex}

        if "metallicFactor" in pbr:
            data["metallic"] = pbr["metallicFactor"]
        if "roughnessFactor" in pbr:
            data["roughness"] = pbr["roughnessFactor"]
        mr_tex = resolve_tex(pbr.get("metallicRoughnessTexture"))
        if mr_tex is not None:
            data["metallic"] = {"texture": mr_tex}
            data["roughness"] = {"texture": mr_tex}

        normal_tex = resolve_tex(material.get("normalTexture"))
        if normal_tex is not None:
            data["normal"] = {"texture": normal_tex}

        emissive_tex = resolve_tex(material.get("emissiveTexture"))
        if emissive_tex is not None:
            data["emmisive"] = {"texture": emissive_tex}
        elif "emissiveFactor" in material:
            factor = material["emissiveFactor"]
            data["emmisive"] = [factor[0], factor[1], factor[2], 1.0]

        name = material.get("name") or f"material_{i}"
        if name in materials:
            name = f"{name}_{i}"
        material_index_to_name[i] = name
        materials[name] = data

    blob = bytearray()

    def append_array(arr: np.ndarray) -> dict:
        """Appends `arr`'s raw bytes to `blob`, first padding to a 4-byte boundary so `load_baked_model()` can `np.frombuffer()` straight over the blob with no alignment issues, and returns the `{"offset", "length"}` entry the mesh header stores to find it again."""
        pad = (-len(blob)) % 4
        blob.extend(b"\x00" * pad)
        offset = len(blob)
        raw = arr.tobytes()
        blob.extend(raw)
        return {"offset": offset, "length": len(raw)}

    meshes_header: dict[str, dict] = {}

    for mesh_index, mesh in enumerate(gltf.get("meshes", [])):
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            attributes = primitive["attributes"]

            positions = np.asarray(parser.get_accessor_data(attributes["POSITION"]), dtype=np.float32)

            normal_accessor = attributes.get("NORMAL")
            normals = np.asarray(parser.get_accessor_data(normal_accessor), dtype=np.float32) if normal_accessor is not None else None

            uv_accessor = attributes.get("TEXCOORD_0")
            uvs = np.asarray(parser.get_accessor_data(uv_accessor), dtype=np.float32).copy() if uv_accessor is not None else None
            if uvs is not None:
                uvs[:, 1] = 1.0 - uvs[:, 1]
                uvs[:, 0] = 1.0 - uvs[:, 0]

            if "indices" in primitive:
                indices = np.asarray(parser.get_accessor_data(primitive["indices"]), dtype=np.uint32)
            else:
                indices = np.arange(len(positions), dtype=np.uint32)

            material_index = primitive.get("material")
            material_name = material_index_to_name.get(material_index, "default") if material_index is not None else "default"

            mesh_name = f"Mesh_{mesh_index}_{primitive_index}"
            meshes_header[mesh_name] = {
                "material": material_name,
                "positions": append_array(positions.reshape(-1)),
                "normals": append_array(normals.reshape(-1)) if normals is not None else None,
                "uvs": append_array(uvs.reshape(-1)) if uvs is not None else None,
                "indices": append_array(indices.reshape(-1)),
            }

    header = {"meshes": meshes_header, "materials": materials}
    header_bytes = json.dumps(header).encode("utf-8")

    out = bytearray()
    out += b"FBMH"
    out += struct.pack("<I", len(header_bytes))
    out += header_bytes
    out += blob
    return bytes(out), images_out


def load_baked_model(file: FileResource) -> Model:
    """Loads a `.fbmesh` written by bake_gltf_to_fbmesh() - every array is a
    direct `np.frombuffer()` view over the file's own bytes (no JSON
    accessor indirection, no per-element decode of any kind), and every
    material's textures load through the normal load_file() path (so a
    release build's shared texture atlas still applies to them)."""
    raw = file.read(bytes=True)
    if raw[:4] != b"FBMH":
        raise ValueError(f"'{file.file_path}' is not a valid .fbmesh file")

    header_length = struct.unpack_from("<I", raw, 4)[0]
    header = json.loads(raw[8:8 + header_length])
    blob = raw[8 + header_length:]

    pipeline = get_service("graphics")

    materials = {}
    for name, props in header["materials"].items():
        data = {}
        for prop, value in props.items():
            if isinstance(value, dict) and "texture" in value:
                data[prop] = load_file(value["texture"])
            else:
                data[prop] = value
        materials[name] = pipeline.create_material(data, None)

    def read_array(entry, dtype, components):
        """Reconstructs one array from `blob` via `np.frombuffer()` - a zero-copy view at the recorded offset/length, not a decode - reshaped to `components` columns, mirroring `append_array()`'s encoding. Returns None if `entry` is None (an array that wasn't present when the mesh was baked, e.g. no normals)."""
        if entry is None:
            return None
        count = entry["length"] // np.dtype(dtype).itemsize
        return np.frombuffer(blob, dtype=dtype, count=count, offset=entry["offset"]).reshape(-1, components)

    meshes = {}
    material_map = {}
    for mesh_name, info in header["meshes"].items():
        positions = read_array(info["positions"], np.float32, 3)
        normals = read_array(info.get("normals"), np.float32, 3)
        uvs = read_array(info.get("uvs"), np.float32, 2)
        indices = read_array(info["indices"], np.uint32, 1).reshape(-1)

        meshes[mesh_name] = create_static_mesh(positions, uvs, normals, indices)
        material_map[mesh_name] = info["material"]

    return Model(meshes, material_map, materials)


def load_model(file: FileResource):
    """Loads a `.gltf` or `.glb` model file into a Model.

    Checks build/builder.py's model manifest first - if this asset has a
    pre-baked `.fbmesh` from a `freebody build`/dev build, loads that
    instead (via load_baked_model(), no glTF parsing or texture decode at
    all). Otherwise parses the glTF fresh on the spot (resolving any
    external `.bin`/image siblings relative to the file's own directory)
    and builds every mesh in it into one combined Model - callers that need
    one specific mesh out of a multi-mesh file go through
    GLTFParser.build_model() directly instead of this loader.

    Raises ValueError if `file`'s extension is neither `.gltf` nor `.glb`."""
    manifest = _load_model_manifest()
    built_path = manifest.get(file.file_path)
    if built_path is not None:
        baked_file = get_file(built_path)
        if baked_file is not None:
            return load_baked_model(baked_file)

    # ------------------------------------------------------------
    # GLTF
    # ------------------------------------------------------------

    if file.file_path.endswith(".gltf"):

        data = loads(file.read())

        # Directory containing the .gltf.
        #
        # This is important for:
        #
        #   "textures/diffuse.png"
        #   "textures/normal.png"
        #
        # inside the glTF.
        base_path = str(
            PurePosixPath(
                file.file_path
            ).parent
        )

        # Load referenced .bin if necessary.
        buffers = data.get("buffers", [])

        bin_data = b""

        if buffers:

            first_buffer = buffers[0]

            if "uri" not in first_buffer:

                # This situation normally belongs to GLB,
                # but keep it safe.
                bin_data = b""

            else:

                uri = first_buffer["uri"]

                if uri.startswith("data:"):

                    _, encoded = uri.split(",", 1)

                    bin_data = base64.b64decode(
                        encoded
                    )

                else:

                    bin_path = str(
                        PurePosixPath(
                            base_path
                        ) / unquote(uri)
                    )

                    bin_data = get_file(
                        bin_path
                    ).read(bytes=True)

        parser = GLTFParser(
            data,
            bin_data,
            base_path
        )

        # `model_name=None` builds every mesh in the file into one combined
        # Model - the right default for a generic "load this file" call
        # site, which has no particular mesh name to ask for. Callers that
        # need one specific mesh out of a multi-mesh file (e.g. a single
        # piece out of a glTF chess set) go through GLTFParser.build_model()
        # directly instead of this loader.
        return parser.build_model(
            None,
            None
        )

    # ------------------------------------------------------------
    # GLB
    # ------------------------------------------------------------

    elif file.file_path.endswith(".glb"):

        data = file.read(bytes=True)

        glb_parser = GLBParser(data)

        parser = GLTFParser(
            glb_parser.get_json(),
            glb_parser.get_binary_buffer(),
            str(
                PurePosixPath(
                    file.file_path
                ).parent
            )
        )

        return parser.build_model(
            None,
            None
        )

    raise ValueError(
        f"Unsupported model format: "
        f"{file.file_path}"
    )
