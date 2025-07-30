import struct
import json
from FreeBodyEngine.graphics.model import Model
from FreeBodyEngine.graphics.mesh import Mesh
from FreeBodyEngine.graphics.material import Material
import numpy as np

class GLBParser:
    def __init__(self, path):
        "Parses .glb (glTF blob) files into its glTF + bin data."
        self.path = path
        self.json_chunk = None
        self.bin_chunk = None
        self._parse()

    def _parse(self):
        with open(self.path, 'rb') as f:
            data = f.read()

        offset = 0

        magic, version, length = struct.unpack_from('<4sII', data, offset)
        offset += 12

        if magic != b'glTF':
            raise ValueError("Not a valid .glb file")

        if version != 2:
            raise ValueError("Only glTF version 2.0 is supported")

        # JSON chunk
        chunk_length, chunk_type = struct.unpack_from('<I4s', data, offset)
        offset += 8
        if chunk_type != b'JSON':
            raise ValueError("First chunk must be JSON")

        json_bytes = data[offset:offset+chunk_length]
        self.json_chunk = json.loads(json_bytes.decode('utf-8'))
        offset += chunk_length

        # BIN chunk
        if offset < len(data):
            chunk_length, chunk_type = struct.unpack_from('<I4s', data, offset)
            offset += 8
            if chunk_type != b'BIN\x00':
                raise ValueError("Second chunk must be BIN")
            self.bin_chunk = data[offset:offset+chunk_length]

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

    def build_model(self, model_name: str) -> Model:
        model = self.gltf['meshes'][self.get_model_index(model_name)]
        
        meshes = {}
        materials = {}

        material_map = {}
        
        i = 0
        for material in model['materials']:
            Material()
        
        for mesh in model['primitives']:
            pos_accessor = mesh['attributes']['POSITION']
            positions = np.array(self.get_accessor_data(pos_accessor), np.float32)
            
            normal_accessor = mesh['attributes']['NORMAL']
            normals = np.array(self.get_accessor_data(normal_accessor), np.float32)
            
            uv_accessor = mesh['attributes']['TEXCOORD_0']
            uvs = np.array(self.get_accessor_data(uv_accessor), np.float32)

            index_accessor = mesh['indices']
            indices = np.array(self.get_accessor_data(index_accessor), np.int32)

            mesh_name = f"Mesh_{i}"
            
            material_index = mesh['material']
            material = self.gltf['materials'][material_index]
            material_name = material.get('name', f'material_{material_index}')

            meshes[mesh_name] = (Mesh(positions, normals, uvs, indices))
            material_map[mesh_name] = material_name

            i += 1

        return Model(meshes, material_map, materials)



if __name__ == "__main__":
    glb = GLBParser("C:\\Users\\Ollie\\Documents\\GitHub\\wultuh.glb")
    parser = GLTFParser(glb.get_json(), glb.get_binary_buffer())
    print(parser.gltf)