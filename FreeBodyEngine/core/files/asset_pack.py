from FreeBodyEngine.core.files.system import FileSystem
from FreeBodyEngine.core.files.stream import FileStream

ASSET_INFO_OFFSET = 36

class AssetPack(FileStream):
    def __init__(self, data: bytes | str):
        super().__init__() 
        self._data = data   
        
        # ensure file is actually an asset pack
        if str(self._data[0:3]) == "FBAP":
            pass            
        
        self.asset_info = self.extract_asset_info()

    def extract_asset_info(self) -> dict:
        self.data


class AssetPackFileSystem(FileSystem):
    def __init__(self, data: AssetPack):
        self.data = data
        