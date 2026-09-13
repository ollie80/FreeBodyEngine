import os

from FreeBodyEngine import register_event, emit_event

FILE_CHANGE = "ENGINE_file_change"


class FileWatcher:
    """Polls `directory` for files whose mtime changed since the last check
    and emits FILE_CHANGE(relative_path) for each one (a project-relative
    path using "/", matching the same path strings load_file()/get_file()
    use elsewhere) - dev-mode hot reload's only way of finding out a file
    changed at all (see core/files/hot_reload.py for what happens with that
    event, and DevFileSystem for how this gets its update() called).

    A plain mtime-polling watcher (checked once every POLL_EVERY_N_FRAMES
    frames, not an OS-level file-events API like inotify/FSEvents/
    ReadDirectoryChangesW) - works identically on every platform with no
    extra dependency, and a project's asset directory is small enough that
    a full os.walk() a couple of times a second is cheap. Not itself a
    registered Service - DevFileSystem owns one directly and drives its
    update() from its own on_initialize(), since a bare directory-watcher
    has nothing meaningful to depend on or be depended on by.

    New files are recorded silently on the pass they're first seen (there's
    nothing live yet to reload for a file nobody has loaded before) -
    only a *change* to an already-known file's mtime fires the event.
    """
    POLL_EVERY_N_FRAMES = 30

    def __init__(self, directory: str):
        """Registers the FILE_CHANGE event and takes an initial silent scan
        of `directory` to record every existing file's mtime, so the first
        real scan (from update()) only reports genuine changes, not every
        file as "new"."""
        self.directory = directory
        self._mtimes: dict[str, float] = {}
        self._frame_count = 0
        register_event(FILE_CHANGE)
        self._scan(initial=True)

    def _scan(self, initial: bool = False):
        if not os.path.isdir(self.directory):
            return

        for dirpath, _, filenames in os.walk(self.directory):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, self.directory).replace(os.sep, "/")

                try:
                    mtime = os.path.getmtime(abs_path)
                except OSError:
                    continue

                previous = self._mtimes.get(rel_path)
                self._mtimes[rel_path] = mtime

                if not initial and previous is not None and mtime != previous:
                    emit_event(FILE_CHANGE, rel_path)

    def update(self):
        """Call once per frame; actually rescans the directory only every
        POLL_EVERY_N_FRAMES calls."""
        self._frame_count += 1
        if self._frame_count % self.POLL_EVERY_N_FRAMES == 0:
            self._scan()
