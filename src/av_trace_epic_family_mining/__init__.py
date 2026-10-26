"""EPIC-specific machine P-tier candidate mining and authoring assistance."""

from av_trace_mini_pilot_families.mining import (
    FrozenClipQueryEncoder,
    HashFixtureEncoder,
)

from .adapters import (
    EpicFamilyInputError,
    EpicIndexInputs,
    HumanObservation,
    PrescreenBundle,
    PrescreenSourceGate,
    load_canonical_epic_index,
    load_human_complete_prescreen,
)
from .authoring import build_candidate_registry, task145_cbrn_template
from .contracts import (
    ALLOWED_COMPOSITION_OPERATORS,
    HUMAN_TIER_MARKERS,
    OBSERVATION_CLASSES,
    P_TIERS,
    SCHEMA_VERSION,
    assert_machine_provisional_only,
    validate_candidate_registry,
    validate_hop_structure,
)
from .fixtures import build_rehearsal_plan
from .mining import (
    DYNAMIC_VISUAL_PROMPTS,
    STATIC_TEXT_VISUAL_PROMPTS,
    VisualQueryEncoder,
    mine_initial_machine_leads,
)

__all__ = [
    "ALLOWED_COMPOSITION_OPERATORS",
    "DYNAMIC_VISUAL_PROMPTS",
    "HUMAN_TIER_MARKERS",
    "OBSERVATION_CLASSES",
    "P_TIERS",
    "SCHEMA_VERSION",
    "STATIC_TEXT_VISUAL_PROMPTS",
    "EpicFamilyInputError",
    "EpicIndexInputs",
    "FrozenClipQueryEncoder",
    "HashFixtureEncoder",
    "HumanObservation",
    "PrescreenBundle",
    "PrescreenSourceGate",
    "VisualQueryEncoder",
    "assert_machine_provisional_only",
    "build_candidate_registry",
    "build_rehearsal_plan",
    "load_canonical_epic_index",
    "load_human_complete_prescreen",
    "mine_initial_machine_leads",
    "task145_cbrn_template",
    "validate_candidate_registry",
    "validate_hop_structure",
]
