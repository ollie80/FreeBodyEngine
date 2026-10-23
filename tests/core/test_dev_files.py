"""Tests for DevFileSystem's handling of paths that don't exist.

get_file() on a writable path created an empty file there on the spot, so a
mistyped asset path - or path_exists() itself, which went through get_file()
and so answered True for everything - left empty files in the project's
assets. Its existence check for read-only paths was also inverted.
"""
import os

import pytest

import FreeBodyEngine.core.files as files_module
import FreeBodyEngine.core.files.dev as dev
from FreeBodyEngine.core.files import ASSET_WRITES_PERMITTED


@pytest.fixture
def assets(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'FileWatcher', lambda *args, **kwargs: None)
    (tmp_path / 'there.txt').write_bytes(b'hello')
    fs = dev.DevFileSystem(str(tmp_path))
    monkeypatch.setattr(files_module, 'get_service', lambda name: fs)
    return tmp_path, fs


def test_missing_path_is_not_created_by_looking_at_it(assets):
    root, fs = assets
    resource = fs.get_file('typo.png')
    assert resource.read(bytes=True) == b''
    assert not os.path.exists(root / 'typo.png')


def test_first_write_creates_the_file(assets):
    root, fs = assets
    fs.get_file('saves/new.txt').write('data')
    assert (root / 'saves' / 'new.txt').read_bytes() == b'data'


def test_path_exists(assets):
    root, fs = assets
    assert files_module.path_exists('there.txt')
    assert not files_module.path_exists('actions.toml')
    assert not os.path.exists(root / 'actions.toml')


def test_read_only_paths(assets, monkeypatch):
    root, fs = assets
    monkeypatch.setattr(dev, 'get_flag', lambda key, default: False if key == ASSET_WRITES_PERMITTED else default)
    assert fs.get_file('there.txt').read(bytes=True) == b'hello'   # was refused
    assert fs.get_file('missing.txt') is None
