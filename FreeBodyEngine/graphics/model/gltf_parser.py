import struct
import json
from FreeBodyEngine.graphics.model import Model
from FreeBodyEngine.graphics.mesh import Mesh
from FreeBodyEngine.graphics.material import Material
from FreeBodyEngine.graphics.pipeline import GraphicsPipeline
from FreeBodyEngine.graphics.renderer import Renderer
from FreeBodyEngine.graphics.gl33 import GL33Renderer
from FreeBodyEngine.graphics.pbr.pipeline import PBRPipeline
import numpy as np

class GLBParser:
    def __init__(self, data_bytes):
        "Parses .glb (glTF blob) files into its glTF + bin data."
        self.bytes = data_bytes
        self.json_chunk = None
        self.bin_chunk = None
        self._parse()

    def _parse(self):
        offset = 0

        magic, version, length = struct.unpack_from('<4sII', self.bytes, offset)
        offset += 12

        if magic != b'glTF':
            raise ValueError("Not a valid .glb file")

        if version != 2:
            raise ValueError("Only glTF version 2.0 is supported")

        chunk_length, chunk_type = struct.unpack_from('<I4s', self.bytes, offset)
        offset += 8
        if chunk_type != b'JSON':
            raise ValueError("First chunk must be JSON")

        json_bytes = self.bytes[offset:offset+chunk_length]
        self.json_chunk = json.loads(json_bytes.decode('utf-8'))
        offset += chunk_length

        if offset < len(self.bytes):
            chunk_length, chunk_type = struct.unpack_from('<I4s', self.bytes, offset)
            offset += 8
            if chunk_type != b'BIN\x00':
                raise ValueError("Second chunk must be BIN")
            self.bin_chunk = self.bytes[offset:offset+chunk_length]

    def get_json(self):
        return self.json_chunk

    def get_binary_buffer(self):
        return self.bin_chunk



class GLTFParser:
    def __init__(self, gltf_dict, bin_data):
        self.gltf = gltf_dict
        self.bin_data = bin_data

    def get_accessor_data(self, accessor_index):
        accessor = self.gltf["accessors"][accessor_index]
        buffer_view = self.gltf["bufferViews"][accessor["bufferView"]]

        buffer_offset = buffer_view.get("byteOffset", 0)
        accessor_offset = accessor.get("byteOffset", 0)
        total_offset = buffer_offset + accessor_offset

        count = accessor["count"]
        component_type = accessor["componentType"]
        data_type = accessor["type"]

        type_num_components = {
            "SCALAR": 1,
            "VEC2": 2,
            "VEC3": 3,
            "VEC4": 4,
            "MAT2": 4,
            "MAT3": 9,
            "MAT4": 16
        }

        component_format = {
            5120: 'b',  # BYTE
            5121: 'B',  # UNSIGNED_BYTE
            5122: 'h',  # SHORT
            5123: 'H',  # UNSIGNED_SHORT
            5125: 'I',  # UNSIGNED_INT
            5126: 'f',  # FLOAT
        }

        num_components = type_num_components[data_type]
        fmt_char = component_format[component_type]
        component_size = struct.calcsize(fmt_char)

        total_size = count * num_components * component_size
        byte_stride = buffer_view.get("byteStride", num_components * component_size)

        values = []
        for i in range(count):
            start = total_offset + i * byte_stride
            end = start + num_components * component_size
            chunk = self.bin_data[start:end]
            fmt = '<' + fmt_char * num_components
            values.append(struct.unpack(fmt, chunk))

        return values
    

    def get_model_index(self, name: str):
        i = 0
        for model in self.gltf['meshes']:
            if model['name'] == name:
                return i
            i += 1   

    def get_image_data(self, image_index):
        image = self.gltf['images'][image_index]

        if "bufferView" in image:
            buffer_view = self.gltf["bufferViews"][image["bufferView"]]
            offset = buffer_view.get("byteOffset", 0)
            length = buffer_view["byteLength"]
            return self.bin_data[offset:offset + length]
        
        elif "uri" in image:
            uri = image["uri"]
            if uri.startswith("data:"):
                import base64
                header, encoded = uri.split(",", 1)
                return base64.b64decode(encoded)
            else:
                raise NotImplementedError("External images not supported in this context")
        
        else:
            raise ValueError("Image has no bufferView or URI")

    def build_model(self, model_name: str, pipeline: GraphicsPipeline, renderer: Renderer, scale: tuple[int, int, int] = None) -> Model:
        if model_name is None:
            print(self.gltf['meshes'])
            model_name = self.gltf['meshes'][0].get('name')

        model = self.gltf['meshes'][self.get_model_index(model_name)]

        meshes = {}
        materials = {}
        textures = {}
        material_map = {}

        # Load all textures
        for texture_index in range(len(self.gltf['images'])):
            data = self.get_image_data(texture_index)
            textures[texture_index] = renderer.texture_manager._create_standalone_texture(data)

        # Load all materials
        for i, material in enumerate(self.gltf['materials']):
            data = {
                'albedo': [0.0, 0.0, 0.0, 1.0],
                'normal': [0.0, 0.0, 0.0, 1.0],
                'emmisive': [0.0, 0.0, 0.0, 1.0],
                'roughness': 0.0,
                'metallic': 1.0,
            }

            pbr = material.get('pbrMetallicRoughness', {})
            if 'baseColorFactor' in pbr:
                data['albedo'] = pbr['baseColorFactor']
            if 'baseColorTexture' in pbr:
                tex = textures[pbr['baseColorTexture']['index']]
                data['albedo'] = tex

            materials[material.get('name', f'material_{i}')] = pipeline.create_material(data)

        # Meshes
        for i, mesh in enumerate(model['primitives']):
            pos_accessor = mesh['attributes']['POSITION']
            positions = np.array(self.get_accessor_data(pos_accessor), np.float32)

            # ✅ Apply scale here
            if scale:
                positions *= np.array(scale, dtype=np.float32)

            normal_accessor = mesh['attributes'].get('NORMAL')
            normals = np.array(self.get_accessor_data(normal_accessor), np.float32) if normal_accessor is not None else None

            uv_accessor = mesh['attributes'].get('TEXCOORD_0')
            uvs = np.array(self.get_accessor_data(uv_accessor), np.float32) if uv_accessor is not None else None

            index_accessor = mesh['indices']
            indices = np.array(self.get_accessor_data(index_accessor), np.int32)

            mesh_name = f"Mesh_{i}"

            material_index = mesh.get('material')
            material_name = "default"
            if material_index is not None:
                material = self.gltf['materials'][material_index]
                material_name = material.get('name', f'material_{material_index}')

            meshes[mesh_name] = renderer.mesh_class(positions, normals, uvs, indices)
            material_map[mesh_name] = material_name

        return Model(meshes, material_map, materials)
