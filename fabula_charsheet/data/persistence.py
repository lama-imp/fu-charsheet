"""Safe reading and writing of saved character / state YAML files.

Files are written as plain YAML (``model_dump(mode="json")``), so they only
contain strings, numbers, lists and mappings and can be read with a safe loader.

Files saved by older versions of the app contain Python object tags such as
``!!python/object:uuid.UUID`` and ``!!python/object/apply:data.models.status.Status``.
``LegacySafeLoader`` reads those without importing or calling anything: an enum
tag becomes its plain value and a UUID tag becomes its string form, which is
what pydantic validation expects anyway.
"""
from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml


class LegacySafeLoader(yaml.SafeLoader):
    pass


def _construct_python_apply(loader: LegacySafeLoader, suffix: str, node: yaml.Node) -> Any:
    # Old files store enum members as `!!python/object/apply:data.models.<module>.<Enum> [value]`.
    # Nothing is imported or called: the tag is only checked, and the plain value kept.
    if suffix.startswith("data.models.") and isinstance(node, yaml.SequenceNode):
        args = loader.construct_sequence(node, deep=True)
        if len(args) == 1 and isinstance(args[0], (str, int, float, bool)):
            return args[0]
    raise yaml.constructor.ConstructorError(
        None, None, f"unsupported Python object tag 'python/object/apply:{suffix}'", node.start_mark
    )


def _construct_python_object(loader: LegacySafeLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.MappingNode):
        state = loader.construct_mapping(node, deep=True)
        if suffix == "uuid.UUID" and "int" in state:
            return str(uuid.UUID(int=state["int"]))
    raise yaml.constructor.ConstructorError(
        None, None, f"unsupported Python object tag 'python/object:{suffix}'", node.start_mark
    )


LegacySafeLoader.add_multi_constructor("tag:yaml.org,2002:python/object/apply:", _construct_python_apply)
LegacySafeLoader.add_multi_constructor("tag:yaml.org,2002:python/object:", _construct_python_object)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.load(f, Loader=LegacySafeLoader)


def dump_yaml(data: Any, path: Path) -> None:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    atomic_write(path, text.encode("utf-8"))


def atomic_write(path: Path, data: bytes) -> None:
    """Write to a temporary file next to `path`, then swap it in.

    The old file (if any) stays intact until the new content is fully on disk.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_NAME_LENGTH = 64


def safe_filename(name: str, fallback: str = "character") -> str:
    """Turn a character name into something usable as a file name prefix.

    The name is only cosmetic in the file name (files are matched by id), so it
    is fine to drop characters. Path separators are removed, so the result can
    never point outside the target directory.
    """
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name)
    cleaned = cleaned[:_MAX_NAME_LENGTH].strip(" .")
    if not cleaned or cleaned.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        return fallback
    return cleaned
