"""Scale-1B learned grounded-generation and agent pilot.

The package deliberately keeps evaluator-private benchmark state in the
parent process and sends only a reduced public view to the Qwen worker.
"""

from .core import (
    GAPilotError,
    build_ga_pilot,
    freeze_ga_contract,
    run_ga_pilot,
    verify_ga_pilot,
    verify_prerequisite_gates,
)

__all__ = [
    "GAPilotError",
    "build_ga_pilot",
    "freeze_ga_contract",
    "run_ga_pilot",
    "verify_ga_pilot",
    "verify_prerequisite_gates",
]
