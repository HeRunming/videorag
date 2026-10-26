"""CaptainCook4D event-centric provisional family mining."""

from .adapters import (
    CaptainCook4DFamilyInputError,
    CaptainCook4DIndexInputs,
    HumanObservation,
    PrescreenBundle,
    PrescreenSourceGate,
    load_canonical_captaincook4d_index,
    load_human_complete_prescreen,
)
from .authoring import build_candidate_registry, task145_cbrn_template
from .contracts import (
    ALLOWED_COMPOSITION_OPERATORS,
    ARTIFACT_CLASS,
    EXPECTED_SOURCE_GROUPS,
    EXPECTED_SOURCE_IDS,
    OBSERVATION_CLASSES,
    P_TIERS,
    SCHEMA_VERSION,
    assert_machine_expert_provisional_only,
    validate_candidate_registry,
    validate_hop_structure,
)
from .fixtures import build_rehearsal_plan
from .inspection import (
    direct_inspection_assistance,
    unexecuted_inspection_scaffold,
)
from .mining import (
    DYNAMIC_VISUAL_PROMPTS,
    STATIC_TEXT_VISUAL_PROMPTS,
    FrozenClipQueryEncoder,
    HashFixtureEncoder,
    VisualQueryEncoder,
    mine_initial_machine_leads,
)

__all__ = [
    "ALLOWED_COMPOSITION_OPERATORS",
    "ARTIFACT_CLASS",
    "DYNAMIC_VISUAL_PROMPTS",
    "EXPECTED_SOURCE_GROUPS",
    "EXPECTED_SOURCE_IDS",
    "OBSERVATION_CLASSES",
    "P_TIERS",
    "SCHEMA_VERSION",
    "STATIC_TEXT_VISUAL_PROMPTS",
    "CaptainCook4DFamilyInputError",
    "CaptainCook4DIndexInputs",
    "FrozenClipQueryEncoder",
    "HashFixtureEncoder",
    "HumanObservation",
    "PrescreenBundle",
    "PrescreenSourceGate",
    "VisualQueryEncoder",
    "assert_machine_expert_provisional_only",
    "build_candidate_registry",
    "build_rehearsal_plan",
    "direct_inspection_assistance",
    "load_canonical_captaincook4d_index",
    "load_human_complete_prescreen",
    "mine_initial_machine_leads",
    "task145_cbrn_template",
    "unexecuted_inspection_scaffold",
    "validate_candidate_registry",
    "validate_hop_structure",
]
