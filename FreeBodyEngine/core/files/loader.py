from FreeBodyEngine import get_service


def load_file(path: str | tuple, file_type=None):
    """Loads `path` (or, for loaders that accept multiple files at once -
    e.g. TEXTURE_STACK_FILE's layered images - a tuple of paths) through
    the registered `loaders` table in core/files/__init__.py, and returns
    whatever that loader produces.

    If `file_type` is given (one of the `*_FILE` constants), only that
    loader is tried, and it must both accept every path's extension and
    (when multiple paths are given) support multiple files - otherwise this
    returns `''`. If `file_type` is omitted, every registered loader is
    tried in `loaders`' insertion order and the first one whose supported
    extensions match every path's extension (and, again, supports multiple
    files if more than one path was given) wins - loader order matters when
    two loaders claim the same extension (see the comment on `loaders`).

    Also returns `''` for an empty `path` tuple, for any path with no
    extension (or whose last `.` falls before its last path separator, e.g.
    a dotted directory name with no extension on the filename itself), or
    if nothing matches."""
    from FreeBodyEngine.core.files import loaders  # lazy — safe, resolved at call time

    paths = (path,) if isinstance(path, str) else tuple(path)

    if not paths:
        return ''

    files = []
    extensions = []

    for p in paths:
        file = get_service('files').get_file(p)

        dot_index = p.rfind('.')
        slash_index = max(p.rfind('/'), p.rfind('\\'))

        if dot_index == -1 or dot_index < slash_index:
            return ''

        extension = p[dot_index:].lower()
        files.append(file)
        extensions.append(extension)

    multiple_files = len(files) > 1

    if file_type is not None:
        loader_info = loaders.get(file_type)
        if loader_info is None:
            return ''
        loader, supported_extensions, supports_multiple = loader_info
        supported_extensions = tuple(ext.lower() for ext in supported_extensions)
        if any(extension not in supported_extensions for extension in extensions):
            return ''
        if multiple_files and not supports_multiple:
            return ''
        return loader(files if multiple_files else files[0])

    for loader, supported_extensions, supports_multiple in loaders.values():
        supported_extensions = tuple(ext.lower() for ext in supported_extensions)
        if any(extension not in supported_extensions for extension in extensions):
            continue
        if multiple_files and not supports_multiple:
            continue
        return loader(files if multiple_files else files[0])

    return ''
