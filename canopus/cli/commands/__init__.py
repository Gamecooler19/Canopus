"""CLI command modules for Canopus.

Re-exports the primary entry points so ``cli/app.py`` has a single,
clean import surface.
"""

from canopus.cli.commands.chat import chat
from canopus.cli.commands.doctor import doctor
from canopus.cli.commands.profile import profile_app, profile_list, profile_show
from canopus.cli.commands.run_cmd import run_prompt
from canopus.cli.commands.version_cmd import version

__all__ = [
    "chat",
    "doctor",
    "profile_app",
    "profile_list",
    "profile_show",
    "run_prompt",
    "version",
]
