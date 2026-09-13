"""Generates one API reference page per module under FreeBodyEngine/, plus
the nav structure for that section (reference/SUMMARY.md, read by the
mkdocs-literate-nav plugin) - run automatically by mkdocs-gen-files on every
`mkdocs build`/`mkdocs serve`, so the API reference never needs hand
maintenance as modules are added, removed, or renamed.

Standard mkdocstrings recipe (https://mkdocstrings.github.io/recipes/),
pointed at this repo's own package layout.
"""

from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

root = Path(__file__).parent.parent
src = root / "FreeBodyEngine"

for path in sorted(src.rglob("*.py")):
    module_path = path.relative_to(root).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("reference", doc_path)

    parts = tuple(module_path.parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        full_doc_path = full_doc_path.with_name("index.md")
    elif parts[-1] == "__main__":
        continue

    # `parts` is empty exactly when this is FreeBodyEngine/__init__.py
    # itself (the root package's own __init__, not a submodule's) - that
    # still needs its own reference page (it's where get_service(),
    # register_service_update(), and the rest of the top-level fb.* API
    # actually live), just keyed by the package name rather than a
    # now-empty parts tuple.
    nav_key = parts if parts else (src.name,)
    ident = ".".join(parts) if parts else src.name

    nav[nav_key] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        fd.write(f"::: {ident}\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, path.relative_to(root))

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
