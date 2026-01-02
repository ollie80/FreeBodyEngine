import os
from importlib.resources import files

ASSET_PACK_SIGNATURE = "FBAP" 
TEMP_BLOB_PATH = "./temp.pak"
MAX_CHUNK_SIZE = 64 # KB

class AssetPackParser:
    def __init__(self, path: str):
        self.path = path
        self.directory_path = os.path.dirname(self.path)


        sig = self.data[:3].decode()
        if sig != ASSET_PACK_SIGNATURE:
            print('Could not create asset pack, .')

class AssetPackBuilder:
    """
    Builds the data for a asset pack file.
    """
    def __init__(self, paths: dict[str, str], out_path: str):
        """
        :param paths: The paths used to get the assets. Key is the path used in the asset pack, and the item is the file path.
        :type paths: dict[str, str]
        """
        self.out_path = out_path
        self.paths = paths
        self.current_id = 0
        self.asset_path_id_map: dict[str, int] = {}

    def create_file(self):
        open(self.out_path, 'wb').write(ASSET_PACK_SIGNATURE)

    def create_temp_file(self):
        open(TEMP_BLOB_PATH, 'wb')

    def get_asset_id(self):
        asset_id = self.current_id
        
        self.current_id += 1
        return asset_id

    def create_asset_blob(self):
        """
        Fills the temp blob file with the data from the assets. Returns the total size of the blob and the asset info.
        """
        total_size = 0
        asset_info = bytes()
        
        for path in self.paths:
            file_path = self.paths[path] 
            
            asset_id = self.get_asset_id()
            
            asset_info += asset_id.to_bytes()
            asset_info += total_size.to_bytes()

            data = open(file_path, 'rb').read()
            total_size += len(data)
            
            open(TEMP_BLOB_PATH, 'ab').write(data)

        return total_size, asset_info

    def create_header(self, asset_blob_size: int, asset_info: bytes):
        header = bytes()

        header += asset_blob_size.to_bytes(8)
        
        header += asset_info

        return header
    
    def create_asset_chunks(self, asset_blob_size: int):
        num_chunks = round((asset_blob_size/1000)/MAX_CHUNK_SIZE)
        position = 0

        

        with open(TEMP_BLOB_PATH) as blob_file:
            for i in range(num_chunks):
                chunk_path = f"{self.out_path}/chunk{i}.pak"
                
                blob_file.seek(position)

                chunk_data = blob_file.read(MAX_CHUNK_SIZE)
                
                open(chunk_path, 'wb').write(chunk_data)

                position += MAX_CHUNK_SIZE

    def clear_temp_blob(self):
        open(TEMP_BLOB_PATH, 'w').write(bytes())

    def inject_engine_assets(self, paths: dict[str, str]) -> dict[str, str]:
        """
        Get all engine assets, build the chunks,
        """
        engine_assets = files("FreeBodyEngine.engine_assets")

        current_size = 0
        for path in engine_assets.iterdir():
            if path.is_file():
                
                chunk_id = 0
                
                current_chunk_path = f'{self.out_path}/engine_chunk{chunk_id}.pak'

                
                

    def get_path_from_id(self, target_id: int):
        """
        Get a file path from its asset ID.
        """
        for path in self.asset_path_id_map:
            if self.asset_path_id_map[path] == target_id:
                return path

    def create_path_blob(self, paths: list[str]):
        #          dict of asset_id, start_pos, end_pos, with the asset_id as the key 
        path_info: dict[int, tuple[int, int]] = []

        with open(TEMP_BLOB_PATH) as temp_blob:
            for path in paths:
                path_info.append((self.asset_path_id_map[]))
                
                bytes(path)


    def build(self):
        self.create_file()
        self.create_temp_file()
        
        assets_blob_size, asset_info = self.create_asset_blob()
        asset_blob_size, asset_info = self.inject_engine_assets(asset_blob_size, asset_info)

        header = self.create_header(assets_blob_size, asset_info)
        
        open(self.out_path, 'wb').write(header)
        
        
        self.create_asset_chunks(assets_blob_size)
        
        self.clear_temp_blob()