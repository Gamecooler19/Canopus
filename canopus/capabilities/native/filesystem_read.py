"""``filesystem.read_text`` — safely read a text file from disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from canopus.capabilities.context import CapabilityContext
from canopus.capabilities.specs import CapabilitySpec
from canopus.core.errors import CapabilityError
from canopus.security.permissions import ConfirmationPolicy, Permission, SideEffectLevel

# Maximum file size we will read. Prevents memory exhaustion from huge files.
_MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MiB

SPEC = CapabilitySpec(
    name="filesystem.read_text",
    description="Reads a text file from disk and returns its contents.",
    tags=["filesystem", "file", "read", "text"],
    permissions=[Permission.FS_READ],
    side_effect_level=SideEffectLevel.NONE,
    confirmation_policy=ConfirmationPolicy.NEVER,
    transport="native",
    examples=[
        "read file notes.txt",
        "show me the contents of README.md",
        "read /path/to/file",
        "what is in config.toml",
    ],
)


def handler(inputs: dict[str, Any], ctx: CapabilityContext) -> dict[str, Any]:
    """Read and return the text contents of *inputs[\"path\"]*.

    Args:
        inputs: Must contain ``"path"`` — a string path to the file.
        ctx: Runtime context (unused by this handler).

    Returns:
        Dict with keys: ``path``, ``content``, ``size_bytes``, ``encoding``.

    Raises:
        :class:`~canopus.core.errors.CapabilityError`: On missing input,
            path traversal attempts, oversized files, binary files, or I/O
            errors.
    """
    raw_path = inputs.get("path")
    if not raw_path or not isinstance(raw_path, str):
        raise CapabilityError("filesystem.read_text requires a 'path' string input.")

    path = _validate_path(raw_path)

    if not path.exists():
        raise CapabilityError(f"File not found: {path}")

    if not path.is_file():
        raise CapabilityError(f"Path is not a file: {path}")

    size = path.stat().st_size
    if size > _MAX_FILE_BYTES:
        raise CapabilityError(
            f"File is too large to read ({size:,} bytes). "
            f"Maximum is {_MAX_FILE_BYTES:,} bytes (1 MiB)."
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise CapabilityError(
            f"File {path} does not appear to be valid UTF-8 text. "
            "Binary files are not supported."
        ) from None
    except OSError as exc:
        raise CapabilityError(f"Could not read file {path}: {exc}") from exc

    return {
        "path": str(path),
        "content": content,
        "size_bytes": size,
        "encoding": "utf-8",
    }


def _validate_path(raw: str) -> Path:
    """Resolve and validate the input path.

    Raises:
        :class:`~canopus.core.errors.CapabilityError`: If the path contains
            null bytes or other clearly malicious patterns.
    """
    if "\x00" in raw:
        raise CapabilityError("Path contains null bytes.")

    return Path(raw).resolve()
