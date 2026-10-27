"""Tests for the C++ scripts build (cli/cpp/compile.py) on Windows.

Every Windows build got MSVC's `/std:c++17`, including the ones going
through the bundled clang++, which read it as a file name. The bundled
clang's path reached setuptools with backslashes, which its mingw32
compiler's shlex.split() ate ("[WinError 2]"). A relative code path was
joined onto itself, since setup.py runs from its own directory. And the
engine's UI module and a project's were both `_fbcpp`, so Python only ever
loaded one of them. The bundled clang is a bare clang++.exe, without
clang's own headers, so it got the Windows SDK's offsetof, which pybind11
can't use - MSVC, wherever it's installed, builds instead.
"""
import os
import shlex

import pytest

import FreeBodyEngine.cli.cpp.compile as compile_module
from FreeBodyEngine.cli.cpp.compile import compile_cpp_scripts, engine_extension_name

SCRIPT = '''#pragma once
//@bind
class Thing {
public:
    Thing() {}
    int twice(int x) { return x * 2; }
};
'''

CLANG = r'C:\Program Files\FreeBody\lib\windows\clang++.exe'


@pytest.fixture
def code(tmp_path, monkeypatch):
    monkeypatch.delenv('CXX', raising=False)
    (tmp_path / 'code').mkdir()
    (tmp_path / 'code' / 'thing.hpp').write_text(SCRIPT)
    return tmp_path / 'code'


def _setup_py(code_dir) -> str:
    return (code_dir / 'cpp_scripts' / 'setup.py').read_text()


def _generate(code_dir, platform, **kwargs):
    assert compile_cpp_scripts(str(code_dir), 'python', platform_name=platform, generate_only=True, **kwargs) == 'generated'
    return _setup_py(code_dir)


@pytest.fixture
def no_msvc(monkeypatch):
    monkeypatch.setattr(compile_module, '_msvc_installed', lambda: False)
    monkeypatch.setattr(compile_module, '_windows_bundled_clang', lambda: CLANG)


def test_the_bundled_clang_gets_flags_clang_understands(code, no_msvc):
    setup = _generate(code, 'windows')
    assert "extra_compile_args=['-std=c++17', '-O2', '-D_CRT_USE_BUILTIN_OFFSETOF']" in setup
    assert '/std:' not in setup


def test_msvc_gets_its_own_spelling(code, monkeypatch):
    monkeypatch.setattr(compile_module, '_msvc_installed', lambda: False)
    monkeypatch.setattr(compile_module, '_windows_bundled_clang', lambda: None)
    assert "extra_compile_args=['/std:c++17']" in _generate(code, 'windows')


def test_msvc_is_used_whenever_it_is_installed(code, monkeypatch):
    monkeypatch.setattr(compile_module, '_msvc_installed', lambda: True)
    monkeypatch.setattr(compile_module, '_windows_bundled_clang', lambda: CLANG)
    assert "extra_compile_args=['/std:c++17']" in _generate(code, 'windows')
    assert compile_module._extra_setup_args('windows') == []
    assert compile_module._build_env('windows').get('CXX') is None


def test_a_chosen_compiler_is_left_alone(code, monkeypatch):
    """CXX set: the mingw32 compiler isn't asked for, so MSVC builds it."""
    monkeypatch.setattr(compile_module, '_msvc_installed', lambda: False)
    monkeypatch.setattr(compile_module, '_windows_bundled_clang', lambda: CLANG)
    monkeypatch.setenv('CXX', 'g++')
    assert "extra_compile_args=['/std:c++17']" in _generate(code, 'windows')
    assert compile_module._extra_setup_args('windows') == []


def test_other_platforms_get_the_gcc_spelling(code):
    assert "extra_compile_args=['-std=c++17']" in _generate(code, 'linux')


def test_the_bundled_clang_path_survives_shlex(monkeypatch, no_msvc):
    monkeypatch.delenv('CXX', raising=False)
    env = compile_module._build_env('windows')
    assert shlex.split(env['CXX']) == [CLANG.replace('\\', '/')]
    assert env['CC'] == env['CXX']
    assert compile_module._extra_setup_args('windows') == ['--compiler=mingw32']


def test_a_relative_code_path_builds_from_the_right_place(code, monkeypatch):
    monkeypatch.setattr(compile_module, '_windows_bundled_clang', lambda: None)
    monkeypatch.chdir(code.parent)
    ran = {}

    class Done:
        returncode = 0
        stdout = stderr = ''

    def fake_run(cmd, cwd, **kwargs):
        ran['cmd'], ran['cwd'] = cmd, cwd
        return Done()

    monkeypatch.setattr(compile_module.subprocess, 'run', fake_run)
    assert compile_cpp_scripts('code', 'python', platform_name='linux', force=True) == 'ok'
    setup_path = ran['cmd'][1]
    assert os.path.isabs(setup_path) and os.path.isfile(setup_path)
    assert os.path.isabs(ran['cwd'])


def test_a_project_module_is_still_fbcpp(code):
    _generate(code, 'linux')
    scripts = code / 'cpp_scripts'
    assert 'PYBIND11_MODULE(_fbcpp, m)' in (scripts / 'gen' / '_module.cpp').read_text()
    assert 'from _fbcpp import thing' in (scripts / 'thing.py').read_text()
    assert 'name="fbcpp"' in _setup_py(code)


def test_engine_modules_get_their_own_names(tmp_path):
    native = tmp_path / 'ui' / 'native'
    native.mkdir(parents=True)
    (native / 'thing.hpp').write_text(SCRIPT)
    name = engine_extension_name(str(native))
    assert name == '_fbengine_ui'

    _generate(native, 'linux', extension_name=name)
    scripts = native / 'cpp_scripts'
    assert 'PYBIND11_MODULE(_fbengine_ui, m)' in (scripts / 'gen' / '_module.cpp').read_text()
    assert 'from _fbengine_ui import thing' in (scripts / 'thing.py').read_text()
    setup = _setup_py(native)
    assert '"_fbengine_ui",' in setup and 'name="fbengine_ui"' in setup


def test_the_ui_imports_the_name_its_module_is_built_under():
    """Read, not imported: importing it needs the module built."""
    import FreeBodyEngine.ui
    ui_dir = os.path.dirname(FreeBodyEngine.ui.__file__)
    source = open(os.path.join(ui_dir, 'native_element.py'), encoding='utf-8').read()
    assert f'import {engine_extension_name(os.path.join(ui_dir, "native"))}\n' in source.replace('  #', '\n#')
