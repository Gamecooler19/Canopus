"""Workflow loader — discovery and parsing of workflow YAML files.

:class:`WorkflowLoader` discovers ``.yaml`` / ``.yml`` files in a given
directory, parses them into :class:`~canopus.workflows.models.WorkflowDef`
objects, and validates them. The loader is intentionally separate from the
engine so loading can be tested without executing anything.

Workflow file format (YAML)::

    name: directory_summary
    description: List a directory and summarise its contents.
    tags:
      - filesystem
      - summarisation
    inputs:
      - name: path
        description: Directory path to summarise.
        required: true
    steps:
      - id: list_dir
        kind: capability
        description: List the target directory.
        capability: filesystem.list_dir
        inputs:
          path: "{{ inputs.path }}"
          max_entries: 50

      - id: summarise
        kind: model
        description: Summarise the directory listing.
        prompt: |
          Summarise this directory listing concisely:

          {{ steps.list_dir.text }}

      - id: result
        kind: output
        description: Final summary.
        value: "{{ steps.summarise.text }}"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from canopus.workflows.errors import (
    WorkflowLoadError,
    WorkflowNotFoundError,
    WorkflowValidationError,
)
from canopus.workflows.models import WorkflowDef

# File extensions accepted as workflow definitions
_WORKFLOW_EXTENSIONS = {".yaml", ".yml"}


class WorkflowLoader:
    """Discovers and loads workflow definitions from a directory.

    Args:
        workflows_dir: The directory to scan for workflow files. If the
            directory does not exist it is treated as empty (no workflows).
    """

    def __init__(self, workflows_dir: Path) -> None:
        self._dir = workflows_dir

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_workflow_names(self) -> list[str]:
        """Return a sorted list of discovered workflow names (file stems).

        Returns:
            Alphabetically sorted list of workflow name strings.
        """
        if not self._dir.exists():
            return []
        return sorted(
            p.stem
            for p in self._dir.iterdir()
            if p.is_file() and p.suffix.lower() in _WORKFLOW_EXTENSIONS
        )

    def list_workflow_paths(self) -> list[Path]:
        """Return sorted paths to all discovered workflow files."""
        if not self._dir.exists():
            return []
        return sorted(
            p
            for p in self._dir.iterdir()
            if p.is_file() and p.suffix.lower() in _WORKFLOW_EXTENSIONS
        )

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, name: str) -> WorkflowDef:
        """Load and validate a workflow by name.

        Args:
            name: Workflow name, matching the file stem (without extension).

        Returns:
            A validated :class:`~canopus.workflows.models.WorkflowDef`.

        Raises:
            :class:`~canopus.workflows.errors.WorkflowNotFoundError`: If no
                matching file exists in the workflows directory.
            :class:`~canopus.workflows.errors.WorkflowLoadError`: If the file
                cannot be read or contains invalid YAML.
            :class:`~canopus.workflows.errors.WorkflowValidationError`: If the
                YAML is valid but the workflow schema is violated.
        """
        path = self._find_path(name)
        return self._load_path(path)

    def load_all(self) -> list[WorkflowDef]:
        """Load all valid workflows found in the directory.

        Failed workflows are silently skipped. Use :meth:`validate` to get
        detailed errors for individual workflows.

        Returns:
            List of successfully loaded workflow definitions.
        """
        results: list[WorkflowDef] = []
        for path in self.list_workflow_paths():
            try:
                results.append(self._load_path(path))
            except (WorkflowLoadError, WorkflowValidationError):
                pass
        return results

    def validate(self, name: str) -> list[str]:
        """Validate a workflow and return a list of error messages.

        Returns an empty list if the workflow is valid.

        Args:
            name: Workflow name.

        Returns:
            List of human-readable validation issues. Empty means valid.
        """
        try:
            self.load(name)
            return []
        except WorkflowNotFoundError as exc:
            return [str(exc)]
        except WorkflowLoadError as exc:
            return [str(exc)]
        except WorkflowValidationError as exc:
            return [exc.reason]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_path(self, name: str) -> Path:
        """Find the workflow file for *name*, trying each accepted extension."""
        if not self._dir.exists():
            raise WorkflowNotFoundError(name)
        for ext in _WORKFLOW_EXTENSIONS:
            candidate = self._dir / f"{name}{ext}"
            if candidate.exists():
                return candidate
        raise WorkflowNotFoundError(name)

    def _load_path(self, path: Path) -> WorkflowDef:
        """Parse and validate a single workflow file."""
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkflowLoadError(str(path), str(exc)) from exc

        try:
            raw_data: Any = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise WorkflowLoadError(str(path), f"YAML parse error: {exc}") from exc

        if not isinstance(raw_data, dict):
            raise WorkflowLoadError(
                str(path), "top-level value must be a YAML mapping (dict)"
            )

        # Inject source_path so callers know where the workflow came from
        raw_data["source_path"] = str(path)

        # Use the file stem as name if not explicitly declared
        if "name" not in raw_data:
            raw_data["name"] = path.stem

        try:
            return WorkflowDef.model_validate(raw_data)
        except ValidationError as exc:
            errors = "; ".join(
                f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            )
            raise WorkflowValidationError(raw_data.get("name", path.stem), errors) from exc
