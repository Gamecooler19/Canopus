"""``filesystem.list_dir`` — safely list directory contents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.specs import CapabilitySpec
from canopus.core.errors import CapabilityError
from canopus.security.permissions import ConfirmationPolicy, Permission, SideEffectLevel

# Cap on number of entries returned to prevent overwhelming output
_MAX_ENTRIES = 500

SPEC = CapabilitySpec(
    name="filesystem.list_dir",
    description=(
        "Lists the contents of a directory, returning file names, types, and sizes."
    ),
    tags=["filesystem", "directory", "list", "files"],
    permissions=[Permission.FS_READ],
    side_effect_level=SideEffectLevel.NONE,
    confirmation_policy=ConfirmationPolicy.NEVER,
    transport="native",
    examples=[
        "list files in /tmp",
        "what files are in the current directory",
        "show directory contents of ~/documents",
        "list directory ~/projects",
    ],
)


def handler(inputs: dict[str, Any], ctx: CapabilityContext) -> dict[str, Any]:
    """Return a directory listing for *inputs[\"path\"]*.

    Args:
        inputs: Must contain ``"path"`` — a string path to the directory.
            Optional ``"show_hidden"`` (bool, default ``False``) controls
            whether entries starting with ``.`` are included.
        ctx: Runtime context (unused by this handler).

    Returns:
        Dict with keys:
        - ``path``: Resolved absolute path string.
        - ``entries``: List of entry dicts, each with ``name``, ``type``
          (``"file"`` or ``"directory"``), and ``size_bytes`` (files only).
        - ``total_entries``: Total count before any truncation.
        - ``truncated``: ``True`` if more than :data:`_MAX_ENTRIES` entries exist.

    Raises:
        :class:`~canopus.core.errors.CapabilityError`: On missing/invalid
            input, non-existent path, or permission errors.
    """
    raw_path = inputs.get("path")
    if not raw_path or not isinstance(raw_path, str):
        raise CapabilityError(
            "filesystem.list_dir requires a 'path' string input."
        )

    show_hidden: bool = bool(inputs.get("show_hidden", False))

    path = _validate_path(raw_path)

    if not path.exists():
        raise CapabilityError(f"Directory not found: {path}")

    if not path.is_dir():
        raise CapabilityError(f"Path is not a directory: {path}")

    try:
        all_children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError as exc:
        raise CapabilityError(f"Permission denied reading directory {path}: {exc}") from exc
    except OSError as exc:
        raise CapabilityError(f"Could not list directory {path}: {exc}") from exc

    if not show_hidden:
        all_children = [c for c in all_children if not c.name.startswith(".")]

    total = len(all_children)
    truncated = total > _MAX_ENTRIES
    visible = all_children[:_MAX_ENTRIES]

    entries = []
    for child in visible:
        entry: dict[str, Any] = {
            "name": child.name,
            "type": "directory" if child.is_dir() else "file",
        }
        if child.is_file():
            try:
                entry["size_bytes"] = child.stat().st_size
            except OSError:
                entry["size_bytes"] = None
        entries.append(entry)

    return {
        "path": str(path),
        "entries": entries,
        "total_entries": total,
        "truncated": truncated,
    }


def _validate_path(raw: str) -> Path:
    """Resolve and validate the input path.

    Raises:
        :class:`~canopus.core.errors.CapabilityError`: If the path contains
            null bytes.
    """
    if "\x00" in raw:
        raise CapabilityError("Path contains null bytes.")

    return Path(raw).expanduser().resolve()
