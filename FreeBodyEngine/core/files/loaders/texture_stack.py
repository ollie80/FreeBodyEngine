from FreeBodyEngine.core.files import FileResource
TEXTURE_STACK_FILE = "TEXTURE_STACK_FILE"
from FreeBodyEngine import get_service
from io import BytesIO

def load_texture_stack(files: list[FileResource]):
    """Loads several image files into one layered texture stack (e.g. a
    material's albedo/normal/roughness maps loaded together)."""
    # Works identically in dev and release: dev mode's file.read() reads a
    # loose asset file directly, release mode's reads a standalone pak entry
    # (see build/builder.py's build_for_release, which bundles every source
    # image standalone specifically so this keeps working post-atlas-packing).
    # This used to be gated behind DEVMODE and unconditionally returned None
    # in release builds, which is why texture stacks rendered as black.
    return get_service('renderer').texture_manager._create_standalone_texture_stack(
        [BytesIO(file.read(bytes=True)) for file in files]
    )
