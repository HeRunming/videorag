"""Leakage-resistant subprocess execution for AV-TRACE agents.

This package provides a serialization and process-isolation boundary.  It is
deliberately not an OS sandbox: an untrusted child may still use whatever
filesystem, network, process, and system-call capabilities its operating
environment grants.
"""

from .errors import AgentRuntimeError
from .runtime import RuntimeConfig, SubprocessEpisodeRuntime, run_subprocess_episode

__all__ = [
    "AgentRuntimeError",
    "RuntimeConfig",
    "SubprocessEpisodeRuntime",
    "run_subprocess_episode",
]
