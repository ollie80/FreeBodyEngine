import os
import shutil

from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe, Recipe


class FreeBodyEngineNativeRecipe(CppCompiledComponentsPythonRecipe):
    """Cross-compiles this engine's own native (C++/pybind11) UI module
    (see FreeBodyEngine/ui/native/node.hpp) for Android, using the exact
    same generated `.cpp`/`setup.py` every other platform's
    `compile_cpp_scripts()` (FreeBodyEngine/cli/cpp/compile.py) produces -
    just handed to python-for-android's own NDK cross-compile machinery
    instead of a host compiler, via `CppCompiledComponentsPythonRecipe`
    (p4a's own base class for "a real C++ extension that needs the
    cxx-stl linked in", the same shape as any other compiled-extension
    recipe - see pythonforandroid/recipe.py).

    Deliberately has no `url` - unlike a normal recipe, this one's source
    is pre-generated on the *host*, not fetched. See
    Builder._generate_native_sources_for_android() in build/builder.py: it
    calls compile_cpp_scripts(..., generate_only=True) - pure text
    generation, no compiler involved, so doing it host-side ahead of time
    is correct regardless of target platform - writing the generated
    sources into <android build root>/FreeBodyEngine/ui/native/
    cpp_scripts/.

    unpack() below finds that directory itself, relative to *this file's
    own* location, rather than through p4a's usual `P4A_<NAME>_DIR`
    environment-variable mechanism (the officially-documented way to hand
    a recipe pre-existing local source - see Recipe.unpack() in p4a's own
    recipe.py) - that was the first approach tried here, but a real build
    showed the variable doesn't actually survive the buildozer ->
    (subprocess) -> p4a toolchain call chain (confirmed live: "Skipping
    freebodyengine_native unpack as no URL is set" even with the var set
    in the parent process - buildozer's own Buildozer.environ is a
    one-time `os.environ.copy()` at its own startup that should have
    carried it, but evidently doesn't reach the actual `python -m
    pythonforandroid.toolchain create` invocation intact). Locating it
    relative to `__file__` instead sidesteps that uncertainty entirely: by
    the time p4a even considers this recipe, it has already been copied
    (by _write_local_p4a_recipes(), verbatim, directory structure intact)
    to `<android build root>/p4a-recipes/freebodyengine_native/
    __init__.py` - a fixed, known position two directories above the
    pre-generated sources this recipe needs, with no environment or
    timing dependency at all.

    unpack()/should_build() are both overridden to always start fresh -
    matching this engine's own "regenerated fresh on every build"
    philosophy for everything else in the Android dev-build pipeline (see
    build_for_dev_android()'s own docstring), so a real source change
    (node.hpp edited between two `fb run --android` invocations) is never
    silently missed the way p4a's usual "skip if the build dir already
    exists" caching would risk. The underlying compiler invocation
    (`setup.py build_ext`) still does its own incremental object-file
    caching regardless, so this doesn't turn every rebuild into a full
    one - it just makes sure a real source change is never missed.
    """

    name = "freebodyengine_native"
    version = "0.1"
    url = None
    depends = ["python3", "pybind11"]

    def get_recipe_env(self, arch, **kwargs):
        # The generated setup.py (compile_cpp_scripts() in cli/cpp/
        # compile.py - identical on every platform) normally does `import
        # pybind11; ... pybind11.get_include()` to find pybind11's
        # headers - correct and simplest on desktop, where pybind11 is a
        # normal pip-installed package in whatever Python runs setup.py.
        # Confirmed live NOT to work here though: p4a's own pybind11
        # recipe (install_in_hostpython = True) doesn't make it
        # `import`-able from the hostpython this recipe's inherited
        # build_arch() actually runs setup.py with -
        # "ModuleNotFoundError: No module named 'pybind11'", raised at
        # setup.py's own top level before the Extension() definition (and
        # so include_dirs) was ever reached. compile_cpp_scripts()'s
        # generated setup.py checks the FBCPP_PYBIND11_INCLUDE env var
        # first specifically for this - set here, reading the same
        # build-dir-relative header path every other p4a recipe needing
        # pybind11 would use (Recipe.get_recipe('pybind11', ctx).
        # get_include_dir()) - the officially-supported way to consume
        # another recipe's own output, as opposed to a live `import` of
        # it, which never actually got a chance to run.
        env = super().get_recipe_env(arch, **kwargs)
        env['FBCPP_PYBIND11_INCLUDE'] = Recipe.get_recipe('pybind11', self.ctx).get_include_dir(arch)
        return env

    def _pregenerated_source_dir(self):
        # <android build root>/p4a-recipes/freebodyengine_native/__init__.py
        # -> <android build root>/FreeBodyEngine/ui/native/cpp_scripts
        recipe_dir = os.path.dirname(os.path.abspath(__file__))
        android_root = os.path.dirname(os.path.dirname(recipe_dir))
        return os.path.join(android_root, "FreeBodyEngine", "ui", "native", "cpp_scripts")

    def unpack(self, arch):
        # `arch` here is the plain arch-name *string* (e.g. "arm64-v8a"),
        # not an Arch object - p4a's own convention specifically for
        # unpack()/get_build_dir()/get_build_container_dir() (confirmed
        # against a real build traceback: build.py's build_recipes() calls
        # `recipe.prepare_build_dir(arch.arch)`, which passes that string
        # straight through to unpack() unchanged) - unlike build_arch()/
        # get_recipe_env(), which conventionally *do* receive a real Arch
        # object elsewhere in this same base class.
        source_dir = self._pregenerated_source_dir()
        if not os.path.isdir(source_dir):
            raise RuntimeError(
                f"freebodyengine_native: expected pre-generated sources at {source_dir!r} "
                "(see Builder._generate_native_sources_for_android() in build/builder.py) "
                "but found none - this recipe never fetches its own source."
            )

        build_dir = self.get_build_dir(arch)
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)
        os.makedirs(os.path.dirname(build_dir), exist_ok=True)
        shutil.copytree(source_dir, build_dir)

    def should_build(self, arch):
        return True


recipe = FreeBodyEngineNativeRecipe()
