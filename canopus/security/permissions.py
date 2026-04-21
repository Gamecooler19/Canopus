"""Minimal security metadata types for capability governance.

This module provides the enumerations that every capability must declare:
side-effect level, confirmation policy, and permission tokens. These are
intentionally kept simple — a full policy enforcement engine is Phase 7.

Adding a new permission is as simple as adding a member to
:class:`Permission`. The rest of the system uses these as typed strings.
"""

from __future__ import annotations

from enum import StrEnum


class SideEffectLevel(StrEnum):
    """How disruptive a capability's execution is to external state.

    Attributes:
        NONE: Pure read or computation; no observable side effects.
        LOW: Minor, easily reversible state changes (e.g. write a temp file).
        MEDIUM: Significant but scoped state changes (e.g. modify a user file).
        HIGH: Broad, hard-to-reverse, or external side effects
            (e.g. send an email, run a shell command).
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfirmationPolicy(StrEnum):
    """When human confirmation is required before executing a capability.

    Attributes:
        NEVER: Execute immediately without asking.
        SMART: Ask when the policy engine or heuristics flag the request as risky.
        ALWAYS: Always ask before executing, regardless of risk assessment.
    """

    NEVER = "never"
    SMART = "smart"
    ALWAYS = "always"


class Permission(StrEnum):
    """Fine-grained permission tokens declared by each capability.

    The policy layer checks these against the active profile's permission
    grants before allowing execution.
    """

    # Filesystem
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"

    # Network
    NETWORK_HTTP = "network.http"

    # System
    SYSTEM_INFO = "system.info"

    # Shell
    SHELL_EXEC = "shell.exec"

    # Processes
    PROCESS_LIST = "process.list"

    # Email
    EMAIL_READ = "email.read"
    EMAIL_SEND = "email.send"

    # Calendar
    CALENDAR_READ = "calendar.read"
    CALENDAR_WRITE = "calendar.write"

    # Contacts
    CONTACTS_READ = "contacts.read"
