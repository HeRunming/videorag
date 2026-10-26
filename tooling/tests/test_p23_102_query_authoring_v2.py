from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_query_authoring_v2.py"
PLAN_PATH = (
    ROOT / "data/rehearsal_plan/p23_102_query_authoring_v2_plan.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_query_authoring_v2", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _constraint_metadata(tool, factor_kind: str) -> dict:
    context = tool.trusted_ambient_constraint_context()
    key = (
        "attempt_constraint"
        if factor_kind == "ambient"
        else "json_boundary_constraint"
    )
    return json.loads(json.dumps(context[key]))


@pytest.fixture(scope="module")
def local_omni_processor():
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    from transformers import Qwen2_5OmniProcessor

    snapshot = (
        ROOT
        / "data/restricted/strong_baselines/models"
        / "Qwen--Qwen2.5-Omni-7B--ae9e1690543f"
    )
    return Qwen2_5OmniProcessor.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=False,
    )


def test_repaired_bundle_projects_exact_structural_scope() -> None:
    tool = load_tool()
    structural = tool.load_structural_bundle(ROOT)
    assert structural["counts"] == {
        "families": 20,
        "handles": 56,
        "target_clips": 28,
        "near_families": 12,
        "far_families": 8,
        "queries": 76,
    }
    assert len({row["clip_key"] for row in structural["targets"]}) == 28
    assert all(
        len(row["intervals"]) == (1 if row["shape"] == "one_component" else 2)
        for row in structural["families"]
    )
    assert all(
        len(interval["private_evidence_handle_ids"]) == 2
        for family in structural["families"]
        for interval in family["intervals"]
    )


def test_model_visible_prompts_exclude_private_inputs() -> None:
    tool = load_tool()
    structural = tool.load_structural_bundle(ROOT)
    manifest = tool.build_prompt_manifest(structural)
    assert manifest["prompt_count"] == 76
    assert manifest["visual_prompt_count"] == 28
    assert manifest["ambient_prompt_count"] == 28
    assert manifest["composition_prompt_count"] == 20
    for row in [
        *manifest["visual_prompts"],
        *manifest["ambient_prompts"],
    ]:
        visible = tool.canonical_bytes(
            {
                "system": row["system_prompt"],
                "payload": row["user_payload"],
            }
        ).decode("utf-8")
        assert not tool.PRIVATE_ID_RE.search(visible)
        assert not tool.TIMESTAMP_RE.search(visible)
        assert not any(
            literal.casefold() in visible.casefold()
            for literal in tool.SOURCE_LITERALS
        )
        assert not any(
            key in visible for key in tool.FORBIDDEN_MODEL_VISIBLE_KEYS
        )
        assert row["user_payload"]["constraints"][
            "retrieval_information_supplied"
        ] is False
        assert row["user_payload"]["constraints"][
            "human_semantic_labels_supplied"
        ] is False


def test_query_materialization_has_separate_handle_and_family_routes() -> None:
    tool = load_tool()
    structural = tool._synthetic_structural()
    queries, descriptions = tool.materialize_query_records(
        structural, tool._synthetic_parsed(structural)
    )
    assert len(queries) == 76
    assert len(descriptions) == 76
    assert sum(row["query_kind"] == "visual" for row in queries) == 28
    assert sum(row["query_kind"] == "ambient" for row in queries) == 28
    assert (
        sum(row["query_kind"] == "family_compositional" for row in queries)
        == 20
    )
    assert all(
        row["machine_observation_status"]
        == "PENDING_MACHINE_SEMANTIC_GATES"
        for row in queries
    )
    assert all(row["human_grounded"] is False for row in queries)
    assert all(
        set(row["field_gate_status"]) == set(tool.SEMANTIC_GATE_NAMES)
        for row in queries
    )
    assert all("content_grounded" not in row for row in queries)
    assert all(row["template_only_control"] is False for row in queries)
    assert all(
        row["human_semantic_label"] is False for row in descriptions
    )


def test_literal_leakage_audit_catches_all_required_classes() -> None:
    tool = load_tool()
    findings = tool.literal_leakage_findings(
        [
            {
                "key": "q",
                "family_key": "family-001",
                "clip_key": "clip-001",
                "text": (
                    "P23_102 visual clip eh.abc at 01:02 repeats "
                    "please turn on the water now and OBJECT OR STATE"
                ),
            }
        ],
        transcripts_by_clip={"clip-001": "please turn on the water now"},
        slot_names_by_family={"family-001": ["OBJECT_OR_STATE"]},
    )
    kinds = {row["kind"] for row in findings}
    assert {
        "private_id",
        "timestamp",
        "source_name",
        "modality_label",
        "provisional_slot_literal",
        "copied_asr_ngram",
    } <= kinds


def test_duplicate_and_embedding_collision_audits_fail_closed() -> None:
    tool = load_tool()
    rows = [
        {
            "query_key": "q1",
            "query_kind": "visual",
            "query_text": "a hand lifts a metal bowl from the counter",
        },
        {
            "query_key": "q2",
            "query_kind": "visual",
            "query_text": "a hand lifts a metal bowl from the counter",
        },
    ]
    lexical = tool.lexical_collision_findings(rows)
    assert any(row["kind"] == "exact_duplicate" for row in lexical)
    embedded = tool.embedding_collision_findings(
        rows,
        embed_visual=lambda texts: [[1.0, 0.0] for _ in texts],
        embed_ambient=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    assert embedded["findings"]
    assert embedded["target_embeddings_read"] is False
    assert embedded["non_target_embeddings_read"] is False
    assert embedded["query_embeddings_persisted"] is False


def _semantic_fixture(tool, *, far: bool = False):
    structural = {
        "families": [
            {
                "family_key": "family-test",
                "shape": (
                    "two_component_ordered" if far else "one_component"
                ),
                "slot_names": [],
                "intervals": [
                    {"clip_key": "clip-001"},
                    *([{"clip_key": "clip-002"}] if far else []),
                ],
            }
        ]
    }
    ambient_one = tool._accepted_ambient_factor(
        {
            "event_kind": "tap",
            "acoustic_properties": {
                "timbre": "sharp",
                "loudness": "soft",
                "temporal_pattern": "repeated",
            },
        }
    )
    components = [
        {
            "ordinal": 1,
            "visual_description": (
                "An operator slices vegetables on a wooden board."
            ),
            "visual_query": "operator slicing vegetables on a wooden board",
            **ambient_one,
        }
    ]
    if far:
        components.append(
            {
                "ordinal": 2,
                "visual_description": (
                    "An operator transfers vegetables into a metal pot."
                ),
                "visual_query": (
                    "operator transferring vegetables into a metal pot"
                ),
                **tool._accepted_ambient_factor(
                    {
                        "event_kind": "clank",
                        "acoustic_properties": {
                            "timbre": "metallic",
                            "loudness": None,
                            "temporal_pattern": "brief",
                        },
                    }
                ),
            }
        )
    composition = {
        "relation_kind": (
            "ordered_1_then_2" if far else "local_cooccurrence"
        )
    }
    parsed = {
        "family-test": {
            "components": components,
            **composition,
            **tool._mechanical_composition_texts(
                components,
                composition,
                family_shape=structural["families"][0]["shape"],
            ),
        }
    }
    original_queries = tool.EXPECTED_QUERY_COUNT
    tool.EXPECTED_QUERY_COUNT = 5 if far else 3
    try:
        return structural, tool.materialize_query_records(structural, parsed)
    finally:
        tool.EXPECTED_QUERY_COUNT = original_queries


def _semantic_embed(texts):
    vectors = []
    for text in texts:
        words = set(text.lower().split())
        vectors.append(
            [
                float(bool(words & {"sound", "clank", "impact", "sharp"})),
                float(bool(words & {"slice", "slicing", "vegetable"})),
                float(bool(words & {"transfer", "pot", "metal"})),
                0.25,
            ]
        )
    return vectors


def test_v15_action_only_ambient_and_identity_fail_closed() -> None:
    tool = load_tool()
    structural, (queries, descriptions) = _semantic_fixture(tool)
    ambient_query = next(
        row for row in queries if row["query_kind"] == "ambient"
    )
    ambient_description = next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )
    ambient_query["query_text"] = "A pot is set on the stove."
    ambient_description["description_text"] = "A pot is set on the stove."
    acoustic = tool.ambient_acoustic_grounding_audit(
        queries, descriptions, embed_ambient=_semantic_embed
    )
    identity = tool.query_description_identity_audit(queries, descriptions)
    assert acoustic["status"] == "FAIL"
    assert acoustic["findings"][0]["kind"] == (
        "ambient_action_only_or_non_acoustic_paraphrase"
    )
    assert identity["status"] == "FAIL"
    assert structural["families"][0]["shape"] == "one_component"


def test_degenerate_asr_quarantines_unsupported_human_vocalization() -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    ambient_query = next(
        row for row in queries if row["query_kind"] == "ambient"
    )
    ambient_description = next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )
    ambient_query["query_text"] = "A person speaks softly nearby."
    ambient_description["description_text"] = "A nearby person is talking."
    audit = tool.asr_vocalization_quarantine_audit(
        queries,
        descriptions,
        transcripts_by_clip={"clip-001": "Ugh " * 40},
    )
    assert audit["status"] == "FAIL"
    assert audit["analysis_by_clip"]["clip-001"]["degenerate"] is True

    ambient_query["query_text"] = "A brief nonverbal cough is audible."
    ambient_description["description_text"] = (
        "One short cough interrupts the room noise."
    )
    accepted = tool.asr_vocalization_quarantine_audit(
        queries,
        descriptions,
        transcripts_by_clip={"clip-001": "Ugh " * 40},
    )
    assert accepted["status"] == "PASS"
    assert accepted["quarantined_field_keys"]


def test_non_degenerate_lexical_speech_fails_closed() -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    ambient_query = next(
        row for row in queries if row["query_kind"] == "ambient"
    )
    ambient_description = next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )
    ambient_query["query_text"] = "A nearby person says several words."
    ambient_description["description_text"] = (
        "Clear dialogue and speaking are audible."
    )
    audit = tool.asr_vocalization_quarantine_audit(
        queries,
        descriptions,
        transcripts_by_clip={
            "clip-001": "please place the bowl beside the pan"
        },
    )
    assert audit["analysis_by_clip"]["clip-001"]["degenerate"] is False
    assert audit["status"] == "FAIL"
    assert {
        finding["kind"] for finding in audit["findings"]
    } == {"lexical_speech_forbidden"}


@pytest.mark.parametrize(
    "speech_text",
    [
        "People chat nearby.",
        "Two people are chatting.",
        "A narrator narrates the action.",
        "Someone begins to recite.",
        "A person reads aloud.",
        "A group chants rhythmically.",
    ],
)
def test_extended_lexical_speech_terms_fail_closed(
    speech_text: str,
) -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    next(row for row in queries if row["query_kind"] == "ambient")[
        "query_text"
    ] = speech_text
    next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )["description_text"] = speech_text
    audit = tool.asr_vocalization_quarantine_audit(
        queries,
        descriptions,
        transcripts_by_clip={"clip-001": "ordinary complete transcript"},
    )
    assert audit["status"] == "FAIL"
    assert {
        finding["kind"] for finding in audit["findings"]
    } == {"lexical_speech_forbidden"}


def test_generic_sound_or_quiet_does_not_satisfy_acousticness() -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    ambient_query = next(
        row for row in queries if row["query_kind"] == "ambient"
    )
    ambient_description = next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )
    ambient_query["query_text"] = "A quiet sound is nearby."
    ambient_description["description_text"] = "The room is quiet."
    audit = tool.ambient_acoustic_grounding_audit(
        queries,
        descriptions,
        embed_ambient=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    assert audit["status"] == "FAIL"
    assert all(
        result["generic_acoustic_claim_only"]
        for result in audit["field_results"].values()
    )


@pytest.mark.parametrize(
    "text",
    [
        "color choice impacts appearance",
        "person taps a button",
        "clicks a menu button",
        "hand scratches a label",
    ],
)
def test_r9_ambiguous_action_tokens_without_acoustic_context_fail_closed(
    text: str,
) -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    next(row for row in queries if row["query_kind"] == "ambient")[
        "query_text"
    ] = text
    next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )["description_text"] = text
    audit = tool.ambient_acoustic_grounding_audit(
        queries,
        descriptions,
        embed_ambient=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    assert audit["status"] == "FAIL"
    assert all(
        not result["specific_acoustic_terms"]
        for result in audit["field_results"].values()
    )
    assert all(
        result["rejected_ambiguous_acoustic_mentions"]
        for result in audit["field_results"].values()
    )


@pytest.mark.parametrize(
    ("text", "concept"),
    [
        ("a sharp tap is heard", "tap"),
        ("metallic clicking sounds", "click"),
        ("scraping noise", "scrape"),
        ("a knock echoes", "knock"),
        ("a brief metallic clank", "clank"),
        ("a low hiss", "hiss"),
        ("a heavy thud", "thud"),
        ("a beep", "beep"),
        ("a soft rustle", "rustle"),
    ],
)
def test_r9_valid_acoustic_events_pass_lexical_gate(
    text: str, concept: str
) -> None:
    tool = load_tool()
    evidence = tool._acoustic_context_evidence(text)
    assert concept in evidence["concepts"]
    assert tool._specific_acoustic_terms(text)


def test_r11_controlled_auditory_marker_has_one_exclusive_role() -> None:
    tool = load_tool()
    evidence = tool._acoustic_context_evidence("a knock echoes")
    assert evidence["concepts"] == ["knock"]
    assert evidence["rejected_ambiguous"] == []
    assert evidence["controlled_auditory_markers"] == [
        {
            "index": 2,
            "token": "echoes",
            "role": "controlled_auditory_marker",
            "governing_event_index": 1,
            "governing_event_concept": "knock",
        }
    ]
    assert all(
        row["index"] != 2
        for row in [
            *evidence["accepted"],
            *evidence["rejected_ambiguous"],
        ]
    )


@pytest.mark.parametrize(
    "text",
    [
        "sound menu button click",
        "sound color choice impacts appearance",
        "quiet person taps a button",
        "noise hand scratches a label",
    ],
)
def test_r9_unbound_sentence_level_auditory_word_does_not_bypass(
    text: str,
) -> None:
    tool = load_tool()
    assert tool._specific_acoustic_terms(text) == []


def _ambient_factor(
    text: str, query: str = "which matching event is audible"
) -> dict[str, str]:
    return {
        "ambient_description": text,
        "ambient_query": query,
    }


@pytest.mark.parametrize(
    "text",
    [
        "A person taps a button.",
        "a beep sounds while a person taps a button",
        "color choice impacts sound quality",
        "a beep sounds while color choice impacts sound quality",
        "click sound menu button",
        "a beep sounds beside a click sound menu button",
    ],
)
def test_r10_ambient_factor_rejects_unbound_ambiguous_mentions(
    text: str,
) -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID:"
        "ambient_description",
    ):
        tool.validate_legacy_ambient_factor_output(_ambient_factor(text))


@pytest.mark.parametrize(
    "text",
    [
        "scraping noise",
        "throat clearing",
        "sound of a button click",
        "audible clicking",
        "Metallic clicking sounds are heard.",
    ],
)
def test_r10_ambient_factor_accepts_specific_acoustic_phrases(
    text: str,
) -> None:
    tool = load_tool()
    query = f"which {text} is audible"
    assert tool.validate_legacy_ambient_factor_output(_ambient_factor(text, query))


def test_r11_ambient_factor_accepts_controlled_echo_marker_end_to_end() -> None:
    tool = load_tool()
    assert tool.validate_legacy_ambient_factor_output(
        {
            "ambient_description": "a knock echoes",
            "ambient_query": "which knock echoes",
        }
    ) == {
        "ambient_description": "a knock echoes",
        "ambient_query": "which knock echoes",
    }


@pytest.mark.parametrize(
    "text",
    [
        "the design echoes a theme",
        "echo button",
        "a beep sounds while the design echoes a theme",
    ],
)
def test_r11_ambient_factor_rejects_independent_non_acoustic_echo(
    text: str,
) -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID:"
        "ambient_description",
    ):
        tool.validate_legacy_ambient_factor_output(_ambient_factor(text))


def test_r11_ambient_factor_accepts_echo_with_explicit_auditory_context() -> None:
    tool = load_tool()
    assert tool.validate_legacy_ambient_factor_output(
        _ambient_factor("an echo is heard", "which echo is heard")
    )


def test_r12_acoustic_registry_is_single_exact_form_source_of_truth() -> None:
    tool = load_tool()
    required = {
        "creak",
        "clink",
        "jingle",
        "ding",
        "ping",
        "pop",
        "crunch",
        "grind",
        "screech",
        "squeal",
        "rumble",
        "whoosh",
        "swish",
        "drip",
        "trickle",
        "gurgle",
        "slosh",
        "bubble",
        "tick",
        "alarm",
        "siren",
        "bell",
        "horn",
        "footstep",
        "applause",
        "bark",
        "meow",
        "chirp",
    }
    assert required <= set(tool.ACOUSTIC_CONCEPT_REGISTRY)
    derived_forms = {
        form
        for row in tool.ACOUSTIC_CONCEPT_REGISTRY.values()
        for form in row["forms"]
    }
    assert derived_forms == set(tool.ACOUSTIC_FORM_TO_CONCEPT)
    assert tool.ACOUSTIC_CONCEPT_REGISTRY_MANIFEST_SHA256 == (
        tool.semantic_hash(tool.ACOUSTIC_CONCEPT_REGISTRY_MANIFEST)
    )
    assert all(
        tool.ACOUSTIC_CONCEPT_REGISTRY[concept]["role"] == "ambiguous"
        for concept in tool.CONTEXT_BOUND_ACTION_CONCEPTS
    )


@pytest.mark.parametrize(
    "text",
    ["creak", "creaks", "creaked", "creaking"],
)
def test_r12_creak_exact_inflections_pass_acoustic_gate(text: str) -> None:
    tool = load_tool()
    evidence = tool._acoustic_context_evidence(text)
    assert evidence["concepts"] == ["creak"]
    assert evidence["rejected_ambiguous"] == []


@pytest.mark.parametrize(
    "validator,value,error_code",
    [
        (
            "visual",
            {
                "visual_description": "A hand lifts a metal bowl.",
                "visual_query": "a HAND lifts, a metal bowl!",
            },
            "MODEL_VISUAL_QUERY_DESCRIPTION_IDENTITY",
        ),
        (
            "visual",
            {
                "visual_description": "A hand lifts a metal bowl.",
                "visual_query": "metal bowl hand lifts a",
            },
            "MODEL_VISUAL_QUERY_DESCRIPTION_IDENTITY",
        ),
        (
            "ambient",
            {
                "ambient_description": "A door creaks open.",
                "ambient_query": "a DOOR creaks open!",
            },
            "MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY",
        ),
        (
            "ambient",
            {
                "ambient_description": "A door creaks open.",
                "ambient_query": "open door creaks a",
            },
            "MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY",
        ),
    ],
)
def test_r12_factor_identity_rejects_punctuation_case_and_reordering(
    validator: str, value: dict[str, str], error_code: str
) -> None:
    tool = load_tool()
    validate = (
        tool.validate_visual_factor_output
        if validator == "visual"
        else tool.validate_legacy_ambient_factor_output
    )
    with pytest.raises(tool.AuthoringError, match=error_code):
        validate(value)


def test_r12_nonidentical_contained_pairs_pass() -> None:
    tool = load_tool()
    assert tool.validate_visual_factor_output(
        {
            "visual_description": (
                "A hand lifts a metal bowl from a counter."
            ),
            "visual_query": (
                "Which metal bowl is a hand lifting from the counter?"
            ),
        }
    )
    assert tool.validate_legacy_ambient_factor_output(
        {
            "ambient_description": "A door creaks softly.",
            "ambient_query": "Which soft creaking is audible?",
        }
    )


@pytest.mark.parametrize(
    "query",
    [
        "Which metal bowl is a hand lifting from the counter?",
        "Which metal bowl is being lifted from the counter?",
        "metal bowl lifting from the counter",
    ],
)
def test_r15_visual_queries_pass_without_agentive_by(query: str) -> None:
    tool = load_tool()
    value = {
        "visual_description": "A hand lifts a metal bowl from a counter.",
        "visual_query": query,
    }
    assert tool.validate_visual_factor_output(value) == value


@pytest.mark.parametrize(
    ("description", "query", "addition"),
    [
        (
            "A hand lifts a metal bowl from a counter.",
            "Which metal bowl is lifted by the hand from the counter?",
            "by",
        ),
        (
            "A hand lifts a metal bowl from a counter.",
            "Which metal bowl is lifted by a worker from the counter?",
            "by",
        ),
        (
            "A hand lifts a metal bowl from a counter.",
            (
                "Which metal bowl is dropped then lifted by the hand "
                "from the counter?"
            ),
            "by",
        ),
        (
            "A hand lifts a metal bowl from a counter.",
            (
                "Which ceramic metal bowl is lifted by the hand "
                "from the counter?"
            ),
            "by",
        ),
        (
            "A hand lifts a metal bowl from a counter.",
            "Which metal bowl rests by the hand on the counter?",
            "by",
        ),
        (
            "A worker and a sealed box stand nearby.",
            "Which sealed box is sealed by the worker?",
            "by",
        ),
        (
            "A covered bowl sits while a hand rests nearby.",
            "Which covered bowl is covered by the hand?",
            "by",
        ),
        (
            "A red bowl sits while a hand rests nearby.",
            "Which red bowl is red by the hand?",
            "by",
        ),
    ],
)
def test_r15_visual_query_standalone_by_always_fails_closed(
    description: str, query: str, addition: str
) -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match=rf"MODEL_VISUAL_QUERY_SEMANTIC_ADDITION:.*{addition}",
    ):
        tool.validate_visual_factor_output(
            {
                "visual_description": description,
                "visual_query": query,
            }
        )


def test_r15_visual_nearby_is_not_treated_as_standalone_by() -> None:
    tool = load_tool()
    value = {
        "visual_description": (
            "A hand lifts a nearby metal bowl from a counter."
        ),
        "visual_query": (
            "Which nearby metal bowl is a hand lifting from the counter?"
        ),
    }
    assert tool.validate_visual_factor_output(value) == value


@pytest.mark.parametrize(
    "query,addition",
    [
        ("Which ceramic metal bowl is being lifted from the counter?", "ceramic"),
        ("Which metal cup is being lifted from the counter?", "cup"),
        ("Which metal bowl is being dropped from the counter?", "drop"),
        ("What is the person doing with the metal bowl?", "person"),
    ],
)
def test_r15_agent_free_alternatives_do_not_weaken_semantic_gates(
    query: str, addition: str
) -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match=rf"MODEL_VISUAL_QUERY_(?:SEMANTIC_ADDITION:.*{addition}|"
        r"GENERIC_CONTENT_INVALID)",
    ):
        tool.validate_visual_factor_output(
            {
                "visual_description": (
                    "A hand lifts a metal bowl from a counter."
                ),
                "visual_query": query,
            }
        )


@pytest.mark.parametrize(
    "value,code",
    [
        (
            {
                "ambient_description": "A crumpling sound is heard.",
                "ambient_query": "Which paper is crumpling?",
            },
            "MODEL_AMBIENT_QUERY_SEMANTIC_ADDITION",
        ),
        (
            {
                "ambient_description": "A door creaks.",
                "ambient_query": "Which door opens with a creak?",
            },
            "MODEL_AMBIENT_QUERY_SEMANTIC_ADDITION",
        ),
        (
            {
                "ambient_description": "A door creaks.",
                "ambient_query": "Which door is closing with a creak?",
            },
            "MODEL_AMBIENT_QUERY_SEMANTIC_ADDITION",
        ),
    ],
)
def test_r12_ambient_pair_rejects_new_material_or_action(
    value: dict[str, str], code: str
) -> None:
    tool = load_tool()
    with pytest.raises(tool.AuthoringError, match=code):
        tool.validate_legacy_ambient_factor_output(value)


def test_r12_visual_generic_action_query_is_rejected() -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_VISUAL_QUERY_GENERIC_CONTENT_INVALID",
    ):
        tool.validate_visual_factor_output(
            {
                "visual_description": (
                    "A metal bowl rests beside a wooden board."
                ),
                "visual_query": "What is the person doing with the bowl?",
            }
        )


def test_r12_context_bound_actions_do_not_pass_by_wordform_alone() -> None:
    tool = load_tool()
    for form in (
        "slam",
        "drop",
        "break",
        "shatter",
        "tear",
        "rip",
        "chop",
        "cut",
        "stir",
        "pour",
        "clap",
        "stomp",
        "open",
        "close",
        "slide",
    ):
        evidence = tool._acoustic_context_evidence(form)
        assert evidence["concepts"] == []
        assert evidence["rejected_ambiguous"]


def test_r13_postposed_auditory_marker_passes_end_to_end() -> None:
    tool = load_tool()
    evidence = tool._acoustic_context_evidence("A bell rings audibly.")
    assert evidence["rejected_ambiguous"] == []
    assert {"bell", "ring"} <= set(evidence["concepts"])
    value = {
        "ambient_description": "A bell rings audibly.",
        "ambient_query": "Which bell rings audibly?",
    }
    assert tool.validate_legacy_ambient_factor_output(value) == value


@pytest.mark.parametrize(
    "text",
    [
        "A bell rings near a label that is audibly scratched.",
        "A bell rings while a person audibly taps a button.",
        "A bell rings in a room with the sound of a button click.",
    ],
)
def test_r13_distant_auditory_marker_does_not_bind_unrelated_event(
    text: str,
) -> None:
    tool = load_tool()
    evidence = tool._acoustic_context_evidence(text)
    assert any(
        row["concept"] == "ring"
        for row in evidence["rejected_ambiguous"]
    )
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID:"
        "ambient_description",
    ):
        tool.validate_legacy_ambient_factor_output(
            {
                "ambient_description": text,
                "ambient_query": "Which bell rings audibly?",
            }
        )


@pytest.mark.parametrize(
    "text",
    [
        "sound quiet",
        "quiet sound",
        "generic room sound",
    ],
)
def test_r10_ambient_factor_rejects_generic_sound(text: str) -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_SPECIFIC_ACOUSTIC_EVENT_REQUIRED:"
        "ambient_description",
    ):
        tool.validate_legacy_ambient_factor_output(_ambient_factor(text))


@pytest.mark.parametrize(
    "speech_term",
    [
        "ask",
        "asks",
        "asked",
        "asking",
        "question",
        "questions",
        "questioning",
        "answer",
        "answers",
        "answered",
        "answering",
    ],
)
def test_r10_ambient_factor_rejects_lexical_speech_inflections(
    speech_term: str,
) -> None:
    tool = load_tool()
    text = f"a beep sounds during {speech_term}"
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_LEXICAL_SPEECH_FORBIDDEN:"
        "ambient_description",
    ):
        tool.validate_legacy_ambient_factor_output(_ambient_factor(text))


def test_r10_ambient_factor_rejects_exact_ask_question_sentence() -> None:
    tool = load_tool()
    text = "a beep sounds while a person asks a question"
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_LEXICAL_SPEECH_FORBIDDEN:"
        "ambient_description",
    ):
        tool.validate_legacy_ambient_factor_output(_ambient_factor(text))


@pytest.mark.parametrize(
    "text",
    [
        "single beep",
        "ready beep",
    ],
)
def test_r10_ambient_factor_does_not_prefix_match_non_speech_words(
    text: str,
) -> None:
    tool = load_tool()
    assert tool.validate_legacy_ambient_factor_output(
        _ambient_factor(text, f"which {text} is audible")
    )


def test_r10_visual_factor_still_requires_three_words() -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_FIELD_LENGTH_INVALID:visual_description",
    ):
        tool.validate_visual_factor_output(
            {
                "visual_description": "button moves",
                "visual_query": "a button moves",
            }
        )


@pytest.mark.parametrize(
    "text",
    [
        "Loud food preparation activity nearby.",
        "Sharp cooking activity occurs.",
        "Rhythmic hand activity continues.",
    ],
)
def test_acoustic_property_without_event_noun_fails(text: str) -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    next(row for row in queries if row["query_kind"] == "ambient")[
        "query_text"
    ] = text
    next(
        row for row in descriptions if row["description_kind"] == "ambient"
    )["description_text"] = text
    audit = tool.ambient_acoustic_grounding_audit(
        queries,
        descriptions,
        embed_ambient=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    assert audit["status"] == "FAIL"
    assert all(
        not result["specific_acoustic_terms"]
        for result in audit["field_results"].values()
    )


def test_cross_kind_paraphrase_and_unresolved_handle_reference_fail() -> None:
    tool = load_tool()
    _, (queries, _descriptions) = _semantic_fixture(tool)
    visual = next(row for row in queries if row["query_kind"] == "visual")
    ambient = next(row for row in queries if row["query_kind"] == "ambient")
    ambient["query_text"] = visual["query_text"]
    cross_kind = tool.cross_kind_component_audit(
        queries,
        embed_visual=lambda texts: [[1.0, 0.0] for _ in texts],
        embed_ambient=lambda texts: [[1.0, 0.0] for _ in texts],
    )
    assert cross_kind["status"] == "FAIL"

    visual["query_text"] = "The person then moves it into a pot."
    standalone = tool.standalone_reference_audit(queries)
    assert standalone["status"] == "FAIL"
    literals = standalone["findings"][0]["literals"]
    assert {"then", "it"} <= set(literals)


def test_far_family_contract_rejects_v15_continuity_and_missing_audio() -> None:
    tool = load_tool()
    structural, (queries, _descriptions) = _semantic_fixture(tool, far=True)
    family = next(
        row for row in queries if row["query_kind"] == "family_compositional"
    )
    family["query_text"] = (
        "The same person prepares food by chopping ingredients and placing "
        "them into a pot."
    )
    audit = tool.far_composition_audit(structural, queries)
    assert audit["status"] == "FAIL"
    finding = audit["findings"][0]
    assert finding["non_speech_relation_present"] is False
    assert finding["unsupported_patterns"]


def test_far_family_requires_visual_and_ambient_coverage_per_component() -> None:
    tool = load_tool()
    structural, (queries, descriptions) = _semantic_fixture(tool, far=True)
    family_query = next(
        row for row in queries if row["query_kind"] == "family_compositional"
    )
    family_description = next(
        row
        for row in descriptions
        if row["description_kind"] == "family_compositional"
    )
    first_only = (
        "vegetable slicing with steady sharp chopping impacts followed by "
        "transfer into a metal pot"
    )
    family_query["query_text"] = first_only
    family_description["description_text"] = first_only
    audit = tool.far_composition_audit(
        structural, queries, descriptions
    )
    assert audit["status"] == "FAIL"
    assert any(
        finding["coverage"][1]["ambient"]["covered"] is False
        for finding in audit["findings"]
    )


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "swapped_ordinals",
        "missing_clause",
        "visual_word",
        "wrong_ambient_event",
    ],
)
def test_r22a_composition_clauses_bind_exact_description_projection(
    tamper_kind: str,
) -> None:
    tool = load_tool()
    structural, (queries, descriptions) = _semantic_fixture(tool, far=True)
    family_query = next(
        row for row in queries if row["query_kind"] == "family_compositional"
    )
    clauses = json.loads(json.dumps(family_query["composition_clauses"]))
    if tamper_kind == "swapped_ordinals":
        clauses[0]["ordinal"], clauses[1]["ordinal"] = (
            clauses[1]["ordinal"],
            clauses[0]["ordinal"],
        )
    elif tamper_kind == "missing_clause":
        clauses.pop()
    elif tamper_kind == "visual_word":
        clauses[0]["visual_summary"] = clauses[0]["visual_summary"].replace(
            "wooden", "stone"
        )
    else:
        clauses[1]["ambient_summary"] = clauses[1][
            "ambient_summary"
        ].replace("clank", "bell")
    for row in [*queries, *descriptions]:
        if (
            row.get("query_kind") == "family_compositional"
            or row.get("description_kind") == "family_compositional"
        ):
            row["composition_clauses"] = clauses
    audit = tool.far_composition_audit(structural, queries, descriptions)
    assert audit["status"] == "FAIL"
    assert any(
        row["kind"] == "far_family_component_local_binding"
        for row in audit["findings"]
    )


def test_r22a_description_binding_and_query_coverage_are_independent() -> None:
    tool = load_tool()
    structural, (queries, descriptions) = _semantic_fixture(tool, far=True)
    family_query = next(
        row for row in queries if row["query_kind"] == "family_compositional"
    )
    family_query["query_text"] = "Find vegetables with a sharp repeated tap."
    audit = tool.far_composition_audit(structural, queries, descriptions)
    assert audit["status"] == "FAIL"
    local_results = {
        key: value
        for key, value in audit["field_results"].items()
        if key.endswith(":component_local_binding")
    }
    assert local_results
    assert all(value["status"] == "PASS" for value in local_results.values())
    assert audit["field_results"][family_query["query_key"]]["status"] == "FAIL"


def test_r23a_component_local_binding_coverage_and_reference_are_layered() -> None:
    tool = load_tool()
    visual = {
        "visual_description": (
            "A kitchen has a pot on the stove and a table with items on it."
        ),
        "visual_query": "Which pot is on the stove?",
    }
    ambient = tool._accepted_ambient_factor(
        {
            "event_kind": "ding",
            "acoustic_properties": {
                "timbre": "metallic",
                "loudness": "soft",
                "temporal_pattern": "brief",
            },
        }
    )
    family = {
        "family_key": "family-r23a-local",
        "shape": "one_component",
        "intervals": [{"clip_key": "clip-r23a-local"}],
    }
    assembled = tool.assemble_family_factors(
        family,
        [visual],
        [ambient],
        {"relation_kind": "local_cooccurrence"},
    )
    result = tool.validate_component_local_composition(
        family, assembled["components"], assembled
    )
    clause = result["component_clauses"][0]
    assert clause["binding"]["status"] == "PASS"
    assert clause["coverage"]["status"] == "PASS"
    assert clause["coverage"]["source_policy"] == (
        "accepted_descriptions_only"
    )
    assert clause["local_reference"]["status"] == "PASS"
    assert clause["continuity"]["local_visual_pronoun_coreference_exemptions"]
    assert clause["continuity"]["continuity_reference_terms"] == []


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("binding", "BINDING_MISMATCH"),
        ("coverage", "COVERAGE_INVALID"),
        ("reference", "LOCAL_REFERENCE_INVALID"),
    ],
)
def test_r23a_component_local_error_codes_are_distinct(
    mutation: str, error_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    visual_description = "A red bowl rests on a wooden table."
    visual_query = "Which red bowl rests on the wooden table?"
    if mutation == "reference":
        visual_description = "It rests on a wooden table."
        visual_query = "it resting on a wooden table"
    component = {
        "visual_description": visual_description,
        "visual_query": visual_query,
        **tool._accepted_ambient_factor(
            {
                "event_kind": "ding",
                "acoustic_properties": {
                    "timbre": "metallic",
                    "loudness": "soft",
                    "temporal_pattern": "brief",
                },
            }
        ),
    }
    family = {
        "family_key": "family-r23a-errors",
        "shape": "one_component",
        "intervals": [{"clip_key": "clip-r23a-errors"}],
    }
    mechanical = tool._mechanical_composition_texts(
        [component],
        {"relation_kind": "local_cooccurrence"},
        family_shape="one_component",
    )
    composition = {"relation_kind": "local_cooccurrence", **mechanical}
    if mutation == "binding":
        composition["component_clauses"][0]["visual_summary"] = (
            "A blue bowl rests on a wooden table."
        )
    elif mutation == "coverage":
        monkeypatch.setattr(
            tool,
            "_visual_component_coverage",
            lambda family_text, component_text: {
                "required_distinct_tokens": 1,
                "overlap_tokens": [],
                "covered": False,
            },
        )
    with pytest.raises(tool.AuthoringError, match=error_code):
        tool.validate_component_local_composition(
            family, [component], composition
        )


@pytest.mark.parametrize(
    "text",
    [
        "It rests on a table.",
        "This rests on a table.",
        "They rest on a table.",
        "A table holds items. They remain on it.",
        "A table holds items on it again.",
        "A table holds items on it as before.",
        "The same table holds items on it.",
        "A table continues holding items on it.",
    ],
)
def test_r23a_bare_or_bridge_pronouns_remain_rejected(text: str) -> None:
    tool = load_tool()
    evidence = tool._component_local_continuity_evidence(text)
    assert evidence["unsupported"] is True


def test_r23a_cross_component_pronoun_continuity_is_not_relaxed() -> None:
    tool = load_tool()
    evidence = tool._unsupported_continuity_evidence(
        (
            "Component 1 shows a table with items on it; then component 2 "
            "shows a pot beside it."
        ),
        reject_agent_terms=False,
        reject_reused_entities=False,
    )
    assert evidence["unsupported"] is True
    assert "it" in evidence["continuity_reference_terms"]


def _r21_family_regression(tool, family_key: str):
    capsule = (
        ROOT
        / "data/restricted/"
        "p23_102_query_authoring_v2_canary2_run_v1.failure-"
        'PUBLIC_REDACTED_IDENTIFIER'
    )
    subset = json.loads(
        (capsule / "canary2_subset_bundle.json").read_text(encoding="utf-8")
    )
    attempts = [
        json.loads(line)
        for line in (capsule / "raw_attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    family = next(
        row for row in subset["families"] if row["family_key"] == family_key
    )
    accepted_by_key = {}
    for row in attempts:
        if row["family_key"] != family_key or row["parser_error"] is not None:
            continue
        raw = json.loads(row["raw_output"])
        if row["factor_kind"] == "visual":
            accepted_by_key[row["factor_key"]] = (
                tool.validate_visual_factor_output(raw)
            )
        elif row["factor_kind"] == "ambient":
            accepted_by_key[row["factor_key"]] = (
                tool.validate_ambient_factor_output(raw)
            )
        else:
            accepted_by_key[row["factor_key"]] = (
                tool.validate_composition_factor_output(
                    raw,
                    component_count=len(family["intervals"]),
                    family_shape=family["shape"],
                )
            )
    components = []
    for ordinal in range(1, len(family["intervals"]) + 1):
        components.append(
            {
                "ordinal": ordinal,
                **accepted_by_key[
                    f"{family_key}:component:{ordinal}:visual"
                ],
                **accepted_by_key[
                    f"{family_key}:component:{ordinal}:ambient"
                ],
            }
        )
    composition = accepted_by_key[f"{family_key}:family_composition"]
    parsed = {
        "components": components,
        **composition,
        **tool._mechanical_composition_texts(
            components,
            composition,
            family_shape=family["shape"],
        ),
    }
    structural = {
        "families": [family],
        "counts": {
            "families": 1,
            "target_clips": len(family["intervals"]),
            "queries": len(family["intervals"]) * 2 + 1,
        },
    }
    original_families = tool.EXPECTED_FAMILIES
    original_queries = tool.EXPECTED_QUERY_COUNT
    tool.EXPECTED_FAMILIES = 1
    tool.EXPECTED_QUERY_COUNT = structural["counts"]["queries"]
    try:
        queries, descriptions = tool.materialize_query_records(
            structural, {family_key: parsed}
        )
    finally:
        tool.EXPECTED_FAMILIES = original_families
        tool.EXPECTED_QUERY_COUNT = original_queries
    return structural, queries, descriptions


@pytest.mark.parametrize("family_key", ["family-005", "family-003"])
def test_r22a_real_r21_far_description_binding_passes(
    family_key: str,
) -> None:
    tool = load_tool()
    structural, queries, descriptions = _r21_family_regression(
        tool, family_key
    )
    audit = tool.far_composition_audit(structural, queries, descriptions)
    assert not [
        row
        for row in audit["findings"]
        if row["kind"] == "far_family_component_local_binding"
    ]
    local_results = {
        key: value
        for key, value in audit["field_results"].items()
        if key.endswith(":component_local_binding")
    }
    assert len(local_results) == 2
    assert all(value["status"] == "PASS" for value in local_results.values())
    family_query = next(
        row for row in queries if row["query_kind"] == "family_compositional"
    )
    assert audit["field_results"][family_query["query_key"]]["status"] == "PASS"


def test_r22a_ambient_tuple_duplicate_audit_blocks_same_family() -> None:
    tool = load_tool()
    capsule = (
        ROOT
        / "data/restricted/"
        "p23_102_query_authoring_v2_canary2_run_v1.failure-"
        'PUBLIC_REDACTED_IDENTIFIER'
        "accepted_factor_manifest.json"
    )
    manifest = json.loads(capsule.read_text(encoding="utf-8"))
    queries = [
        {
            "query_key": (
                "query-010"
                if row["factor_key"] == "family-003:component:1:ambient"
                else (
                    "query-012"
                    if row["factor_key"]
                    == "family-003:component:2:ambient"
                    else f"query-for:{row['factor_key']}"
                )
            ),
            "query_kind": "ambient",
            "factor_binding": row,
        }
        for row in manifest["factors"]
        if row["factor_kind"] == "ambient"
    ]
    audit = tool.ambient_semantic_tuple_duplicate_audit(
        manifest, queries, scope="r21_canary"
    )
    assert audit["status"] == "FAIL_CLOSED"
    assert audit["blocking_duplicate_group_count"] >= 1
    finding = next(
        row
        for row in audit["blocking_findings"]
        if "family-003" in row["same_family_keys"]
    )
    assert finding["blocking_same_family_duplicate"] is True
    assert any(
        row["same_family"] is True
        and row["left_family_key"] == "family-003"
        and row["left_query_keys"] == ["query-010"]
        and row["right_query_keys"] == ["query-012"]
        for row in audit["collision_ledger"]
    )
    assert audit["automatic_rewrite_permitted"] is False
    assert audit["authoring_retry_permitted"] is False


def test_r22a_r21_query_010_012_duplicate_still_fails() -> None:
    tool = load_tool()
    capsule = (
        ROOT
        / "data/restricted/"
        "p23_102_query_authoring_v2_canary2_run_v1.failure-"
        'PUBLIC_REDACTED_IDENTIFIER'
        "accepted_factor_manifest.json"
    )
    manifest = json.loads(capsule.read_text(encoding="utf-8"))
    ambient = {
        (row["family_key"], row["component_ordinal"]): row["ambient_query"]
        for row in manifest["factors"]
        if row["factor_kind"] == "ambient"
    }
    rows = [
        {
            "query_key": "query-010",
            "query_kind": "ambient",
            "query_text": ambient[("family-003", 1)],
        },
        {
            "query_key": "query-012",
            "query_kind": "ambient",
            "query_text": ambient[("family-003", 2)],
        },
    ]
    exact = next(
        row
        for row in tool.lexical_collision_findings(rows)
        if row["kind"] == "exact_duplicate"
    )
    assert exact["query_keys"] == ["query-010", "query-012"]
    embedding = tool.embedding_collision_findings(
        rows,
        embed_visual=tool._synthetic_embed,
        embed_ambient=tool._synthetic_embed,
    )
    assert embedding["findings"] == [
        {
            "kind": "embedding_near_collision",
            "encoder": "ambient_encoder",
            "query_kind": "ambient",
            "left_query_key": "query-010",
            "right_query_key": "query-012",
            "cosine": 1.0,
        }
    ]
    assert tool.LEXICAL_COLLISION_THRESHOLD == 0.92
    assert tool.EMBEDDING_COLLISION_THRESHOLD == 0.995


def test_far_family_rejects_explicit_actor_or_object_continuity() -> None:
    tool = load_tool()
    structural, (queries, descriptions) = _semantic_fixture(tool, far=True)
    for row in queries:
            if row["query_kind"] == "family_compositional":
                row["query_text"] = (
                "the same person slicing vegetables with chopping impacts "
                "followed by the same person transferring vegetables with "
                "a metallic clank"
            )
    for row in descriptions:
        if row["description_kind"] == "family_compositional":
            row["description_text"] = (
                "Vegetable slicing with chopping impacts precedes vegetable "
                "transfer with a metallic clank."
            )
    audit = tool.far_composition_audit(
        structural, queries, descriptions
    )
    assert audit["status"] == "FAIL"
    assert any(
        finding["unsupported_continuity"]["pattern_matches"]
        for finding in audit["findings"]
        if finding["kind"] == "far_family_semantic_contract"
    )


def test_valid_local_semantic_gates_pass_and_mark_machine_only() -> None:
    tool = load_tool()
    structural, (queries, descriptions) = _semantic_fixture(tool)
    original_families = tool.EXPECTED_FAMILIES
    original_queries = tool.EXPECTED_QUERY_COUNT
    tool.EXPECTED_FAMILIES = 1
    tool.EXPECTED_QUERY_COUNT = 3
    try:
        audits = tool.audit_authored_content(
            structural,
            queries,
            descriptions,
            transcripts_by_clip={"clip-001": ""},
            embed_visual=_semantic_embed,
            embed_ambient=_semantic_embed,
        )
    finally:
        tool.EXPECTED_FAMILIES = original_families
        tool.EXPECTED_QUERY_COUNT = original_queries
    assert audits["status"] == "PASS"
    assert all(
        row["machine_observation_status"] == "MACHINE_GATES_PASSED"
        and row["human_grounded"] is False
        for row in [*queries, *descriptions]
    )
    assert all("content_grounded" not in row for row in queries)


def test_failure_runtime_counts_recovered_from_retained_evidence(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    staging = tmp_path / "staging"
    staging.mkdir()
    tool.atomic_jsonl(
        staging / "raw_attempts.jsonl",
        [
            {"attempt_kind": "initial"},
            {"attempt_kind": "schema_only_repair"},
        ],
    )
    tool.atomic_json(
        staging / "target_manifest.json",
        {"target_count": 3, "targets": [{}, {}, {}]},
    )
    tool.atomic_json(
        staging / "asr_audit_inventory.json",
        {"rows": [{"clip_key": "a"}, {"clip_key": "b"}]},
    )
    counts = tool.retained_runtime_counts(
        staging, {"authoring_model_calls": 0}
    )
    assert counts == {
        "authoring_model_calls": 2,
        "initial_authoring_calls": 1,
        "visual_initial_authoring_calls": 0,
        "ambient_initial_authoring_calls": 0,
        "composition_initial_authoring_calls": 0,
        "schema_only_repair_calls": 1,
        "asr_model_calls": 2,
        "target_clip_decodes": 3,
    }


def _valid_model_value() -> dict:
    return {
        "visual_description": "A hand lifts the metal bowl.",
        "visual_query": "hand lifting the metal bowl",
        "ambient_description": "A brief metal scrape accompanies the lift.",
        "ambient_query": "brief metal scrape during the lift",
    }


def _valid_composition_value() -> dict:
    return {"relation_kind": "local_cooccurrence"}


def test_r5_redteam_component_cross_reference_fixture_fails_closed() -> None:
    tool = load_tool()
    fixture = {
        **_valid_model_value(),
        "visual_description": (
            "A hand aligns a bracket beside another component."
        ),
    }
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_COMPONENT_CROSS_REFERENCE_FORBIDDEN:"
        "visual_description",
    ):
        tool.validate_legacy_component_factor_output(fixture)

    two_component_local = {
        **_valid_model_value(),
        "visual_query": "aligning the bracket after the first component",
    }
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_COMPONENT_CROSS_REFERENCE_FORBIDDEN:visual_query",
    ):
        tool.validate_legacy_component_factor_output(two_component_local)


def test_r5_redteam_expanded_causality_fixture_fails_closed() -> None:
    tool = load_tool()
    fixture = {
        **_valid_model_value(),
        "ambient_description": (
            "The bowl movement leads to a brief metallic scrape."
        ),
    }
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_CAUSAL_LANGUAGE_FORBIDDEN:ambient_description",
    ):
        tool.validate_legacy_component_factor_output(fixture)

    with pytest.raises(
        tool.AuthoringError,
        match="MECHANICAL_CAUSAL_LANGUAGE_FORBIDDEN:relation_description",
    ):
        tool._validate_mechanical_family_text(
            (
                "Component 1: A bowl movement leads to a metallic scrape. "
                "The accepted observations co-occur locally within component 1."
            ),
            "A bowl movement leads to a metallic scrape.",
            field="relation_description",
        )


@pytest.mark.parametrize(
    "value",
    [
        {
            **_valid_model_value(),
            "visual_description": "A hand places another bowl on the counter.",
            "visual_query": "hand placing another bowl on the counter",
        },
        {
            **_valid_model_value(),
            "visual_description": (
                "The inspection result is a bracket resting flat."
            ),
            "visual_query": "bracket resting flat as the inspection result",
        },
    ],
)
def test_r5_normal_object_and_result_noun_content_passes(value: dict) -> None:
    tool = load_tool()
    assert tool.validate_legacy_component_factor_output(value) == value


@pytest.mark.parametrize(
    "causal_text",
    [
        "The lift is leading to a metallic scrape.",
        "The lift led to a metallic scrape.",
        "The lift results in a metallic scrape.",
        "The lift is resulting in a metallic scrape.",
        "The lift resulted in a metallic scrape.",
        "The lift produces a metallic scrape.",
        "The lift is producing a metallic scrape.",
        "The lift triggers a metallic scrape.",
        "The lift is triggering a metallic scrape.",
        "The lift makes a metallic scrape happen.",
        "The lift is making a metallic scrape happen.",
    ],
)
def test_r5_expanded_causality_phrase_family_fails_closed(
    causal_text: str,
) -> None:
    tool = load_tool()
    fixture = {**_valid_model_value(), "ambient_description": causal_text}
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_CAUSAL_LANGUAGE_FORBIDDEN:ambient_description",
    ):
        tool.validate_legacy_component_factor_output(fixture)


def test_composition_schema_is_relation_only_and_clauses_are_mechanical() -> None:
    tool = load_tool()
    assert set(tool.COMPOSITION_OUTPUT_SCHEMA) == {
        "relation_kind",
    }
    components = [
        _valid_model_value(),
        {
            "visual_description": "A hand places a lid on a ceramic jar.",
            "visual_query": "hand placing a lid on a ceramic jar",
            "ambient_description": (
                "A short ceramic tap marks the lid placement."
            ),
            "ambient_query": "short ceramic tap during lid placement",
        },
    ]
    assembled = tool._mechanical_composition_texts(
        components,
        {"relation_kind": "ordered_1_then_2"},
        family_shape="two_component_ordered",
    )
    assert assembled["component_clauses"] == [
        {
            "ordinal": 1,
            "visual_summary": components[0]["visual_description"],
            "ambient_summary": components[0]["ambient_description"],
        },
        {
            "ordinal": 2,
            "visual_summary": components[1]["visual_description"],
            "ambient_summary": components[1]["ambient_description"],
        },
    ]
    assert assembled["family_compositional_description"] == (
        "Component 1: A hand lifts the metal bowl. Accompanying local sound: "
        "A brief metal scrape accompanies the lift. Component 2: A hand "
        "places a lid on a ceramic jar. Accompanying local sound: A short "
        "ceramic tap marks the lid placement. Frozen order: component 1 "
        "before component 2."
    )
    assert assembled["family_compositional_query"] == (
        "Find component 1 matching hand lifting the metal bowl with brief "
        "metal scrape during the lift; then find component 2 matching hand "
        "placing a lid on a ceramic jar with short ceramic tap during lid "
        "placement; keep the frozen 1 to 2 order."
    )
    assert tool.query_description_identity_audit(
        [
            {
                "query_key": "query",
                "family_key": "family",
                "clip_key": None,
                "query_kind": "family_compositional",
                "query_text": assembled["family_compositional_query"],
            }
        ],
        [
            {
                "description_key": "description",
                "family_key": "family",
                "clip_key": None,
                "description_kind": "family_compositional",
                "description_text": assembled[
                    "family_compositional_description"
                ],
            }
        ],
    )["status"] == "PASS"
    one = tool._mechanical_composition_texts(
        [components[0]],
        {"relation_kind": "local_cooccurrence"},
        family_shape="one_component",
    )
    assert one["family_compositional_description"] == (
        "Component 1: A hand lifts the metal bowl. Accompanying local sound: "
        "A brief metal scrape accompanies the lift. The accepted observations "
        "co-occur locally within component 1."
    )
    assert one["family_compositional_query"] == (
        "Find one component matching hand lifting the metal bowl together "
        "with brief metal scrape during the lift as a local co-occurrence."
    )


@pytest.mark.parametrize(
    ("value", "component_count", "family_shape"),
    [
        (
            {"relation_kind": "ordered_1_then_2"},
            1,
            "one_component",
        ),
        (
            {"relation_kind": "local_cooccurrence"},
            2,
            "two_component_ordered",
        ),
    ],
)
def test_composition_shape_and_direction_regressions_fail_closed(
    value: dict,
    component_count: int,
    family_shape: str,
) -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="COMPOSITION_RELATION_KIND_SHAPE_MISMATCH",
    ):
        tool.validate_composition_factor_output(
            value,
            component_count=component_count,
            family_shape=family_shape,
        )


def test_composition_normal_one_and_two_component_values_pass() -> None:
    tool = load_tool()
    one = tool.validate_composition_factor_output(
        _valid_composition_value(),
        component_count=1,
        family_shape="one_component",
    )
    two = tool.validate_composition_factor_output(
        {"relation_kind": "ordered_1_then_2"},
        component_count=2,
        family_shape="two_component_ordered",
    )
    assert one["relation_kind"] == "local_cooccurrence"
    assert two["relation_kind"] == "ordered_1_then_2"


def test_r7_exact_r6_throat_clearing_factor_passes_local_coverage() -> None:
    tool = load_tool()
    legacy_component = {
        "visual_description": (
            "A person places a pot lid on the counter."
        ),
        "visual_query": "person placing a pot lid on the counter",
        "ambient_description": (
            "A person clears their throat before placing a pot lid."
        ),
        "ambient_query": "throat clearing before a pot lid is placed",
    }
    assert tool.validate_legacy_ambient_factor_output(
        {
            "ambient_description": legacy_component[
                "ambient_description"
            ],
            "ambient_query": legacy_component["ambient_query"],
        }
    )
    component = {
        "visual_description": legacy_component["visual_description"],
        "visual_query": legacy_component["visual_query"],
        **tool._accepted_ambient_factor(
            {
                "event_kind": "throat_clear",
                "acoustic_properties": {
                    "timbre": None,
                    "loudness": None,
                    "temporal_pattern": "brief",
                },
            }
        ),
    }
    family = {
        "family_key": "family-r7-local",
        "shape": "one_component",
        "intervals": [{"clip_key": "clip-r7-local"}],
    }
    assembled = tool.assemble_family_factors(
        family,
        [{key: component[key] for key in tool.VISUAL_OUTPUT_SCHEMA}],
        [
            {
                key: component[key]
                for key in tool.AMBIENT_ACCEPTED_FIELDS
            }
        ],
        {"relation_kind": "local_cooccurrence"},
    )
    assert assembled["component_clauses"] == [
        {
            "ordinal": 1,
            "visual_summary": component["visual_description"],
            "ambient_summary": component["ambient_description"],
        }
    ]
    validation = tool.validate_component_local_composition(
        family, assembled["components"], assembled
    )
    assert validation["status"] == "PASS"
    assert validation["component_clauses"][0]["continuity"][
        "agent_terms"
    ] == ["person"]
    assert validation["component_clauses"][0]["continuity"][
        "unsupported_agent_bridge"
    ] is False
    assert validation["component_clauses"][0]["continuity"][
        "local_possessive_coreference_exemptions"
    ] == []
    ambient = tool.ambient_acoustic_grounding_audit(
        [
            {
                "query_key": "ambient-r7",
                "query_kind": "ambient",
                "query_scope": "handle",
                "family_key": "family-r7-local",
                "clip_key": "clip-r7-local",
                "query_text": legacy_component["ambient_query"],
            }
        ],
        [
            {
                "description_key": "ambient-description-r7",
                "description_kind": "ambient",
                "family_key": "family-r7-local",
                "clip_key": "clip-r7-local",
                "description_text": legacy_component[
                    "ambient_description"
                ],
            }
        ],
        embed_ambient=tool._synthetic_embed,
    )
    assert ambient["status"] == "PASS"
    assert ambient["field_results"]["ambient-description-r7"][
        "specific_acoustic_terms"
    ] == ["throat-clearing"]
    assert ambient["field_results"]["ambient-r7"][
        "specific_acoustic_terms"
    ] == ["throat-clearing"]
    assert ambient["field_results"]["ambient-r7"]["status"] == "PASS"


@pytest.mark.parametrize(
    "local_text",
    [
        "Their throat clearing is audible.",
        "The same person clears their throat again.",
        "The same person continues crumpling plastic.",
        "A person crumples the plastic bag again.",
        "The bag moves because the person crumples it.",
    ],
)
def test_r6_local_clause_explicit_bridge_or_causality_still_rejects(
    local_text: str,
) -> None:
    tool = load_tool()
    evidence = tool._component_local_continuity_evidence(local_text)
    assert evidence["unsupported"] is True
    assert (
        evidence["pattern_matches"]
        or evidence["continuity_reference_terms"]
    )


def test_r6_two_component_same_agent_bridge_remains_rejected() -> None:
    tool = load_tool()
    evidence = tool._unsupported_continuity_evidence(
        (
            "The same person slices vegetables with chopping impacts, then "
            "transfers them into a pot with a metallic clank."
        ),
        [
            "A person slices vegetables on a board.",
            "A person transfers vegetables into a pot.",
        ],
        reject_agent_terms=False,
        reject_reused_entities=False,
    )
    assert evidence["unsupported"] is True
    assert evidence["pattern_matches"]


def test_r7_two_component_their_bridge_remains_rejected() -> None:
    tool = load_tool()
    evidence = tool._unsupported_continuity_evidence(
        (
            "A person clears their throat with a dry sound, then their hand "
            "places a pot lid on the counter with a metallic clank."
        ),
        reject_agent_terms=False,
        reject_reused_entities=False,
    )
    assert evidence["unsupported"] is True
    assert evidence["continuity_reference_terms"] == ["their"]


@pytest.mark.parametrize(
    "text",
    [
        "A person clears their throat.",
        "A person clear his throat.",
        "A person is clearing her throat.",
        "A person cleared the throat.",
        "A brief throat clearing is audible.",
    ],
)
def test_r7_throat_clear_variants_normalize_to_specific_acoustic_concept(
    text: str,
) -> None:
    tool = load_tool()
    assert tool._acoustic_concepts(text) == {"throat-clearing"}
    assert tool._specific_acoustic_terms(text) == ["throat-clearing"]


def test_r7_throat_clearing_remains_nonlexical_but_speech_still_rejects() -> None:
    tool = load_tool()
    nonlexical = tool._human_vocalization_policy(
        "A person clears their throat."
    )
    assert nonlexical["clearly_nonlexical_non_speech"] is True
    assert nonlexical["lexical_speech_terms"] == []
    lexical = tool._human_vocalization_policy(
        "A person clears their throat and then speaks several words."
    )
    assert lexical["clearly_nonlexical_non_speech"] is False
    assert {"speaks", "words"} <= set(lexical["lexical_speech_terms"])


def test_composition_validator_requires_frozen_shape_binding() -> None:
    tool = load_tool()
    with pytest.raises(
        tool.AuthoringError,
        match="COMPOSITION_FROZEN_SHAPE_BINDING_REQUIRED",
    ):
        tool.validate_composition_factor_output(_valid_composition_value())


def test_r2_and_r3_extra_semantic_scalars_fail_closed() -> None:
    tool = load_tool()
    r2_raw = {
        "component_clauses": [
            {
                "visual_summary": (
                    "A person is crumpling a plastic bag on a table."
                ),
                "ambient_summary": (
                    "The sound of crumpling plastic is heard."
                ),
            },
            {
                "visual_summary": (
                    "The person continues to crumple the plastic bag."
                ),
                "ambient_summary": "The crumpling sound continues.",
            },
        ],
        "relation_kind": "local_cooccurrence",
        "relation_description": (
            "The person crumples the plastic bag, and the sound of "
            "crumpling plastic is heard."
        ),
        "relation_query": (
            "The person crumples the plastic bag, and the sound of "
            "crumpling plastic is heard."
        ),
    }
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_COMPOSITION_FACTOR_FIELD_SET_MISMATCH",
    ):
        tool.validate_composition_factor_output(
            r2_raw,
            component_count=1,
            family_shape="one_component",
        )
    candidate = tool._schema_repair_candidate(
        json.dumps(r2_raw),
        "MODEL_COMPOSITION_FACTOR_FIELD_SET_MISMATCH",
        semantic_fields=frozenset(tool.COMPOSITION_OUTPUT_SCHEMA),
    )
    assert candidate == r2_raw
    relation_only = {
        key: r2_raw[key] for key in tool.COMPOSITION_OUTPUT_SCHEMA
    }
    assert tool._semantic_scalar_multiset(candidate) != (
        tool._semantic_scalar_multiset(relation_only)
    )
    r3_raw_text = (
        '{ "relation_kind": "local_cooccurrence", '
        '"relation_description": "The component is present in the same '
        'context as another component.", "relation_query": "The component '
        'is co-occurring with another component in the same context." }'
    )
    r3_raw = tool._strict_json_output(r3_raw_text)
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_COMPOSITION_FACTOR_FIELD_SET_MISMATCH",
    ):
        tool.validate_composition_factor_output(
            r3_raw,
            component_count=1,
            family_shape="one_component",
        )
    candidate = tool._schema_repair_candidate(
        r3_raw_text,
        "MODEL_COMPOSITION_FACTOR_FIELD_SET_MISMATCH",
        semantic_fields=frozenset(tool.COMPOSITION_OUTPUT_SCHEMA),
    )
    assert candidate == r3_raw
    assert tool._semantic_scalar_multiset(candidate) != (
        tool._semantic_scalar_multiset(
            {"relation_kind": "local_cooccurrence"}
        )
    )


def _accepted_provenance_fixture(tool):
    structural = {
        "families": [
            {
                "family_key": "family-provenance",
                "shape": "two_component_ordered",
                "slot_names": [],
                "intervals": [
                    {"clip_key": "clip-a"},
                    {"clip_key": "clip-b"},
                ],
            }
        ]
    }
    legacy_component_a = _valid_model_value()
    legacy_component_b = {
        "visual_description": "A hand places a lid on a ceramic jar.",
        "visual_query": "hand placing a lid on a ceramic jar",
        "ambient_description": "A short ceramic tap marks the lid placement.",
        "ambient_query": "short ceramic tap during lid placement",
    }
    component_a = {
        **{
            key: legacy_component_a[key]
            for key in tool.VISUAL_OUTPUT_SCHEMA
        },
        **tool._accepted_ambient_factor(
            {
                "event_kind": "scrape",
                "acoustic_properties": {
                    "timbre": "metallic",
                    "loudness": None,
                    "temporal_pattern": "brief",
                },
            }
        ),
    }
    component_b = {
        **{
            key: legacy_component_b[key]
            for key in tool.VISUAL_OUTPUT_SCHEMA
        },
        **tool._accepted_ambient_factor(
            {
                "event_kind": "tap",
                "acoustic_properties": {
                    "timbre": "crisp",
                    "loudness": "soft",
                    "temporal_pattern": "brief",
                },
            }
        ),
    }
    composition = {"relation_kind": "ordered_1_then_2"}
    components = [
        {"ordinal": 1, **component_a},
        {"ordinal": 2, **component_b},
    ]
    parsed = {
        "family-provenance": {
            "components": components,
            **composition,
            **tool._mechanical_composition_texts(
                components,
                composition,
                family_shape="two_component_ordered",
            ),
        }
    }
    factors = [
        (
            "family-provenance:component:1:visual",
            "visual",
            1,
            {key: component_a[key] for key in tool.VISUAL_OUTPUT_SCHEMA},
            "clip-a",
        ),
        (
            "family-provenance:component:1:ambient",
            "ambient",
            1,
            component_a["ambient_semantics"],
            "clip-a",
        ),
        (
            "family-provenance:component:2:visual",
            "visual",
            2,
            {key: component_b[key] for key in tool.VISUAL_OUTPUT_SCHEMA},
            "clip-b",
        ),
        (
            "family-provenance:component:2:ambient",
            "ambient",
            2,
            component_b["ambient_semantics"],
            "clip-b",
        ),
        (
            "family-provenance:family_composition",
            "family_composition",
            None,
            composition,
            None,
        ),
    ]
    attempts = []
    for factor_key, factor_kind, ordinal, value, clip_key in factors:
        raw = json.dumps(value, sort_keys=True)
        hash_key = (
            "video_sha256" if factor_kind == "visual" else "audio_sha256"
        )
        attempts.append(
            {
                "family_key": "family-provenance",
                "factor_key": factor_key,
                "factor_kind": factor_kind,
                "component_ordinal": ordinal,
                "attempt": 1,
                "attempt_kind": "initial",
                "raw_output": raw,
                "raw_output_sha256": (
                    "sha256:" + __import__("hashlib").sha256(
                        raw.encode("utf-8")
                    ).hexdigest()
                ),
                "parsed_output_sha256": tool.semantic_hash(value),
                "parser_error": None,
                "media_modality": (
                    factor_kind
                    if factor_kind in {"visual", "ambient"}
                    else None
                ),
                "clip_keys": [clip_key] if clip_key else [],
                "clip_manifest_hashes": (
                    [
                        {
                            "clip_key": clip_key,
                            "start_us": 0,
                            "end_us": 1,
                            "duration_us": 1,
                            hash_key: f"sha256:{factor_kind}:{clip_key}",
                        }
                    ]
                    if clip_key
                    else []
                ),
                **_constraint_metadata(tool, factor_kind),
            }
        )
    manifest = tool.build_accepted_factor_manifest(
        structural, parsed, attempts
    )
    original_queries = tool.EXPECTED_QUERY_COUNT
    tool.EXPECTED_QUERY_COUNT = 5
    try:
        queries, descriptions = tool.materialize_query_records(
            structural, parsed, manifest
        )
    finally:
        tool.EXPECTED_QUERY_COUNT = original_queries
    return manifest, attempts, queries, descriptions


def test_accepted_factor_provenance_normal_synthetic_fixture_passes() -> None:
    tool = load_tool()
    manifest, attempts, queries, descriptions = (
        _accepted_provenance_fixture(tool)
    )
    result = tool.validate_accepted_factor_provenance(
        manifest, attempts, queries, descriptions
    )
    assert result == {
        "status": "PASS",
        "accepted_factor_count": 5,
        "bound_final_row_count": 10,
        "cross_factor_fill_or_substitution_detected": False,
    }
    assert all(row["factor_binding"] for row in queries + descriptions)


def test_accepted_factor_provenance_tamper_and_missing_fail_closed() -> None:
    tool = load_tool()
    manifest, attempts, queries, descriptions = (
        _accepted_provenance_fixture(tool)
    )
    tampered_attempts = [dict(row) for row in attempts]
    tampered_attempts[0]["raw_output"] += " "
    with pytest.raises(
        tool.AuthoringError, match="PROVENANCE_RAW_OUTPUT_TAMPERED"
    ):
        tool.validate_accepted_factor_provenance(
            manifest, tampered_attempts, queries, descriptions
        )

    missing = {
        **manifest,
        "factors": manifest["factors"][:-1],
        "accepted_factor_count": 4,
        "composition_factor_count": 0,
    }
    missing["manifest_payload_sha256"] = tool.semantic_hash(
        {
            key: value
            for key, value in missing.items()
            if key != "manifest_payload_sha256"
        }
    )
    with pytest.raises(
        tool.AuthoringError, match="PROVENANCE_ATTEMPT_FACTOR_UNEXPECTED"
    ):
        tool.validate_accepted_factor_provenance(
            missing, attempts, queries, descriptions
        )


def test_accepted_factor_provenance_cross_factor_mismatch_fails_closed() -> None:
    tool = load_tool()
    manifest, attempts, queries, descriptions = (
        _accepted_provenance_fixture(tool)
    )
    mismatched_queries = [dict(row) for row in queries]
    first_visual = next(
        row
        for row in mismatched_queries
        if row["query_kind"] == "visual"
        and row["component_ordinal"] == 1
    )
    second_binding = next(
        row
        for row in manifest["factors"]
        if row["factor_key"] == "family-provenance:component:2:visual"
    )
    first_visual["factor_binding"] = second_binding
    with pytest.raises(
        tool.AuthoringError, match="PROVENANCE_ROW_BINDING_MISMATCH"
    ):
        tool.validate_accepted_factor_provenance(
            manifest, attempts, mismatched_queries, descriptions
        )


def test_provenance_rebuild_rejects_ordinal_attempt_and_factor_adversaries() -> None:
    tool = load_tool()
    manifest, attempts, queries, descriptions = (
        _accepted_provenance_fixture(tool)
    )
    structural = {
        "families": [
            {
                "family_key": "family-provenance",
                "shape": "two_component_ordered",
                "slot_names": [],
                "intervals": [
                    {"clip_key": "clip-a"},
                    {"clip_key": "clip-b"},
                ],
            }
        ]
    }
    prompt_manifest = tool.build_prompt_manifest(structural)
    assert tool.validate_accepted_factor_provenance(
        manifest,
        attempts,
        queries,
        descriptions,
        structural=structural,
        prompt_manifest=prompt_manifest,
    )["status"] == "PASS"

    variants = []
    ordinal_99 = [dict(row) for row in attempts]
    ordinal_99[0]["component_ordinal"] = 99
    variants.append(ordinal_99)
    duplicate_success = [dict(row) for row in attempts]
    duplicate_success.append(dict(duplicate_success[0]))
    variants.append(duplicate_success)
    three_attempts = [dict(row) for row in attempts]
    extra = dict(three_attempts[0])
    extra["attempt"] = 2
    extra["attempt_kind"] = "schema_only_repair"
    three_attempts.append(extra)
    extra2 = dict(extra)
    extra2["attempt"] = 3
    three_attempts.append(extra2)
    variants.append(three_attempts)
    variants.append(attempts[:-1])
    extra_factor = [dict(row) for row in attempts]
    extra_factor.append(
        {
            **dict(attempts[0]),
            "factor_key": "family-provenance:component:99:visual",
            "component_ordinal": 99,
        }
    )
    variants.append(extra_factor)
    for value in variants:
        with pytest.raises(tool.AuthoringError):
            tool.validate_accepted_factor_provenance(
                manifest,
                value,
                queries,
                descriptions,
                structural=structural,
                prompt_manifest=prompt_manifest,
            )


def test_short_query_description_token_identity_fails() -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    visual_query = next(
        row for row in queries if row["query_kind"] == "visual"
    )
    visual_description = next(
        row for row in descriptions if row["description_kind"] == "visual"
    )
    visual_query["query_text"] = "metal bowl lift"
    visual_description["description_text"] = "lift bowl metal"
    audit = tool.query_description_identity_audit(queries, descriptions)
    assert audit["status"] == "FAIL"
    assert audit["findings"][0]["token_sets_equal"] is True


def test_real_processor_media_contract_for_initial_and_repair_prompts(
    local_omni_processor,
) -> None:
    import numpy as np

    tool = load_tool()
    processor = local_omni_processor
    structural = tool._synthetic_structural()
    sample_video = np.zeros((2, 56, 56, 3), dtype=np.uint8)
    family = structural["families"][-1]
    manifest = tool.build_prompt_manifest(
        {"families": [family], "targets": [], "counts": {}}
    )
    visual_prompt = manifest["visual_prompts"][0]
    visual_conversation = tool._model_conversation(visual_prompt)
    _, visual_inputs, visual_contract = tool._prepare_generation_inputs(
        processor,
        conversation=visual_conversation,
        media_present=True,
        videos=[sample_video],
    )
    assert visual_contract["media_mode"] == "video_only"
    assert visual_contract["video_placeholders"] == 1
    assert visual_contract["audio_placeholders"] == 0
    assert visual_contract["video_tensors"] == 1
    assert visual_contract["audio_tensors"] == 0
    assert visual_contract["video_placeholder_tokens"] > 0
    assert visual_contract["audio_placeholder_tokens"] == 0
    assert {"pixel_values_videos", "video_grid_thw"} <= set(
        visual_contract["media_feature_keys"]
    )
    assert not {
        "input_features",
        "feature_attention_mask",
    } & set(visual_contract["media_feature_keys"])
    assert visual_inputs["video_grid_thw"].shape[0] == 1

    sample_audio = np.zeros(1_600, dtype=np.float32)
    ambient_prompt = manifest["ambient_prompts"][0]
    ambient_conversation = tool._model_conversation(ambient_prompt)
    _, ambient_inputs, ambient_contract = tool._prepare_generation_inputs(
        processor,
        conversation=ambient_conversation,
        media_present=True,
        audios=[sample_audio],
    )
    assert ambient_contract["media_mode"] == "audio_only"
    assert ambient_contract["video_placeholders"] == 0
    assert ambient_contract["audio_placeholders"] == 1
    assert ambient_contract["video_tensors"] == 0
    assert ambient_contract["audio_tensors"] == 1
    assert ambient_contract["video_placeholder_tokens"] == 0
    assert ambient_contract["audio_placeholder_tokens"] > 0
    assert {"input_features", "feature_attention_mask"} <= set(
        ambient_contract["media_feature_keys"]
    )
    assert not {
        "pixel_values_videos",
        "video_grid_thw",
    } & set(ambient_contract["media_feature_keys"])
    assert ambient_inputs["input_features"].shape[0] == 1

    repair = tool._schema_repair_conversation(
        visual_prompt,
        prior_raw=json.dumps(
            {
                key: _valid_model_value()[key]
                for key in tool.VISUAL_OUTPUT_SCHEMA
            }
        ),
        validation_error="MODEL_OUTPUT_NOT_STRICT_JSON",
    )
    _, repair_inputs, repair_contract = tool._prepare_generation_inputs(
        processor,
        conversation=repair,
        media_present=False,
    )
    assert repair_contract == {
        "media_present": False,
        "media_mode": "text_only",
        "video_placeholders": 0,
        "audio_placeholders": 0,
        "video_tensors": 0,
        "audio_tensors": 0,
        "video_placeholder_tokens": 0,
        "audio_placeholder_tokens": 0,
        "media_feature_keys": [],
        "use_audio_in_video": None,
        "assistant_prefill": "",
        "assistant_prefill_tokens": 0,
    }
    assert not {
        "pixel_values_videos",
        "video_grid_thw",
        "video_second_per_grid",
        "input_features",
        "feature_attention_mask",
    } & set(repair_inputs)


def test_media_contract_rejects_placeholder_tensor_mismatches(
    local_omni_processor,
) -> None:
    import numpy as np

    tool = load_tool()
    processor = local_omni_processor
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    prompt = tool.build_prompt_manifest(
        {"families": [family], "targets": [], "counts": {}}
    )["visual_prompts"][0]
    initial = tool._model_conversation(prompt, 1)
    repair = tool._schema_repair_conversation(
        prompt,
        prior_raw=json.dumps(_valid_model_value()),
        validation_error="MODEL_OUTPUT_NOT_STRICT_JSON",
    )
    video = np.zeros((2, 56, 56, 3), dtype=np.uint8)
    audio = np.zeros(1_600, dtype=np.float32)
    with pytest.raises(
        tool.AuthoringError,
        match="VIDEO_PLACEHOLDERS_WITHOUT_MEDIA_TENSORS",
    ):
        tool._prepare_generation_inputs(
            processor,
            conversation=initial,
            media_present=False,
        )
    with pytest.raises(
        tool.AuthoringError,
        match="MEDIA_TENSORS_WITHOUT_PLACEHOLDERS",
    ):
        tool._prepare_generation_inputs(
            processor,
            conversation=repair,
            media_present=False,
            videos=[video],
            audios=[audio],
        )
    with pytest.raises(
        tool.AuthoringError,
        match="VIDEO_ONLY_AUDIO_TENSORS_FORBIDDEN",
    ):
        tool._prepare_generation_inputs(
            processor,
            conversation=initial,
            media_present=True,
            videos=[video],
            audios=[audio],
        )


def test_incremental_json_state_machine_nested_and_escaped_content() -> None:
    tool = load_tool()
    state = tool.IncrementalJSONObjectState()
    for chunk in (
        '{"outer":[',
        '{"text":"escaped quote: \\" and brace } and slash \\\\"},',
        '{"unicode":"\\u007bnot structural\\u007d"}',
        '],"ok":true}',
    ):
        state.feed(chunk)
    assert state.complete is True
    assert state.invalid is False
    assert state.completion_offset == len(state.text)
    assert json.loads(state.text)["outer"][0]["text"].endswith("slash \\")


@pytest.mark.parametrize(
    ("raw", "complete", "invalid"),
    [
        ('{"a":1}', True, False),
        ('{"a":1}   ', True, False),
        ('{"a":1}{"b":2}', True, True),
        ('{"a":1} trailing prose', True, True),
        ('{"a":[1,2}', False, True),
        ('{"a":"unfinished', False, False),
    ],
)
def test_incremental_json_state_machine_boundaries(
    raw: str, complete: bool, invalid: bool
) -> None:
    tool = load_tool()
    state = tool.IncrementalJSONObjectState().feed(raw)
    assert state.complete is complete
    assert state.invalid is invalid


def test_fences_prose_multiple_objects_and_unfinished_json_are_rejected() -> None:
    tool = load_tool()
    payload = json.dumps(_valid_model_value(), ensure_ascii=False)
    for raw in (
        f"```json\n{payload}\n```",
        f"Here is the result:\n{payload}",
        f"{payload}{payload}",
        f"{payload} trailing prose",
        payload[:-1],
    ):
        assert (
            tool._schema_repair_candidate(
                raw, "MODEL_OUTPUT_NOT_STRICT_JSON"
            )
            is None
        )
        with pytest.raises(
            tool.AuthoringError, match="MODEL_OUTPUT_NOT_STRICT_JSON"
        ):
            tool._strict_json_output(raw)


def test_prefill_compatibility_and_accounting(local_omni_processor) -> None:
    tool = load_tool()

    class DecoderConfig:
        is_encoder_decoder = False

    class DecoderModel:
        config = DecoderConfig()

    prefill, token_ids, reason = tool._compatible_json_assistant_prefill(
        local_omni_processor.tokenizer, DecoderModel()
    )
    assert prefill == "{"
    assert token_ids == [90]
    assert reason == "enabled_exact_roundtrip"

    structural = tool._synthetic_structural()
    family = structural["families"][0]
    prompt = tool.build_prompt_manifest(
        {"families": [family], "targets": [], "counts": {}}
    )["visual_prompts"][0]
    conversation = tool._schema_repair_conversation(
        prompt,
        prior_raw=json.dumps(_valid_model_value()),
        validation_error="MODEL_OUTPUT_FIELD_SET_MISMATCH",
    )
    rendered, inputs, contract = tool._prepare_generation_inputs(
        local_omni_processor,
        conversation=conversation,
        media_present=False,
        assistant_prefill=prefill,
    )
    assert rendered.endswith("{")
    assert int(inputs["input_ids"][0, -1]) == 90
    assert contract["assistant_prefill"] == "{"
    assert contract["assistant_prefill_tokens"] == 1


def test_fake_generation_stops_before_trailing_prose() -> None:
    import torch

    tool = load_tool()

    class FakeTokenizer:
        eos_token_id = 0
        pad_token_id = 0
        video_token_id = 1
        audio_token_id = 2
        all_special_ids = (0,)

        @staticmethod
        def encode(text, add_special_tokens=False):
            del add_special_tokens
            return [ord(character) for character in text]

        @staticmethod
        def decode(
            token_ids,
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        ):
            del skip_special_tokens, clean_up_tokenization_spaces
            return "".join(
                chr(token_id) for token_id in token_ids if token_id != 0
            )

    class FakeProcessor:
        tokenizer = FakeTokenizer()

        @staticmethod
        def apply_chat_template(
            conversation, add_generation_prompt, tokenize
        ):
            del conversation, add_generation_prompt, tokenize
            return "PROMPT:"

        def __call__(self, **kwargs):
            text = kwargs["text"]
            return {
                "input_ids": torch.tensor(
                    [self.tokenizer.encode(text)], dtype=torch.long
                ),
                "attention_mask": torch.ones(
                    (1, len(text)), dtype=torch.long
                ),
            }

        def batch_decode(self, rows, **kwargs):
            return [self.tokenizer.decode(row.tolist(), **kwargs) for row in rows]

    class Config:
        is_encoder_decoder = False

    class FakeModel:
        config = Config()

        @staticmethod
        def generate(**kwargs):
            input_ids = kwargs["input_ids"]
            logits_processors = kwargs["logits_processor"]
            stopping_criteria = kwargs["stopping_criteria"]
            scripted = '"a":{"escaped":"}"},"b":[1,2]} trailing prose'
            for character in scripted:
                scores = torch.full((1, 128), -1000.0)
                scores[0, ord(character)] = 10.0
                for processor in logits_processors:
                    scores = processor(input_ids, scores)
                next_token = scores.argmax(dim=-1, keepdim=True)
                input_ids = torch.cat((input_ids, next_token), dim=-1)
                if any(
                    bool(criterion(input_ids, scores).all())
                    for criterion in stopping_criteria
                ):
                    break
            return input_ids

    class FakeInferenceMode:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

    class FakeTorch:
        @staticmethod
        def inference_mode():
            return FakeInferenceMode()

    raw, metadata = tool._generate_one(
        FakeProcessor(),
        FakeModel(),
        FakeTorch(),
        conversation=[],
        media_present=False,
    )
    assert raw == '{"a":{"escaped":"}"},"b":[1,2]}'
    assert "trailing prose" not in raw
    assert metadata["assistant_prefill"] == "{"
    assert metadata["assistant_prefill_tokens"] == 1
    assert metadata["model_generated_tokens"] == len(raw) - 1
    assert metadata["constrained_output_tokens"] == len(raw)
    assert (
        metadata["stop_reason"]
        == "first_complete_top_level_json_object"
    )


def test_schema_repair_rejects_semantic_change_and_retains_both_raws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    initial_value = {
        key: _valid_model_value()[key]
        for key in tool.VISUAL_OUTPUT_SCHEMA
    }
    initial_structural_value = {"result": initial_value}
    repaired_value = dict(initial_value)
    repaired_value["visual_query"] = "hand lowering the metal bowl"
    raw_outputs = iter(
        [
            json.dumps(initial_structural_value),
            json.dumps(repaired_value),
        ]
    )
    generation_calls = []

    def fake_generate(*args, **kwargs):
        del args
        generation_calls.append(kwargs)
        raw = next(raw_outputs)
        return raw, {
            "rendered_prompt": "exact prompt",
            "rendered_prompt_sha256": tool.semantic_hash("exact prompt"),
            "rendered_prompt_bytes": 12,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "generation_seconds": 0.1,
            "network_attempts": 0,
            **_constraint_metadata(tool, kwargs["factor_kind"]),
        }

    monkeypatch.setattr(tool, "_generate_one", fake_generate)
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    prompt = tool.build_prompt_manifest(
        {
            "families": [family],
            "targets": structural["targets"][:1],
            "counts": {},
        }
    )["visual_prompts"][0]
    attempts: list[dict] = []
    attempts_path = tmp_path / "raw_attempts.jsonl"
    with pytest.raises(
        tool.AuthoringError,
        match="SCHEMA_REPAIR_CHANGED_SEMANTIC_CONTENT",
    ):
        tool.author_factor(
            object(),
            object(),
            object(),
            family_key=family["family_key"],
            factor_key=f"{family['family_key']}:component:1:visual",
            factor_kind="visual",
            component_ordinal=1,
            prompt=prompt,
            validator=tool.validate_visual_factor_output,
            semantic_fields=frozenset(tool.VISUAL_OUTPUT_SCHEMA),
            videos=[object()],
            audios=None,
            clip_records=[
                {
                    "clip_key": family["intervals"][0]["clip_key"],
                    "video_sha256": "sha256:video",
                }
            ],
            model_identity={"repo_id": "mock"},
            attempts=attempts,
            attempts_path=attempts_path,
        )
    rows = [
        json.loads(line)
        for line in attempts_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert rows[0]["raw_output"] == json.dumps(initial_structural_value)
    assert rows[0]["parser_error"] == (
        "MODEL_VISUAL_FACTOR_FIELD_SET_MISMATCH"
    )
    assert rows[1]["raw_output"] == json.dumps(repaired_value)
    assert rows[1]["parser_error"] == (
        "SCHEMA_REPAIR_CHANGED_SEMANTIC_CONTENT"
    )
    assert rows[1]["content_preserving_guard_passed"] is False
    assert generation_calls[0]["media_present"] is True
    assert generation_calls[0]["videos"]
    assert generation_calls[0]["audios"] is None
    assert generation_calls[1]["media_present"] is False
    assert "videos" not in generation_calls[1]
    assert "audios" not in generation_calls[1]


@pytest.mark.parametrize(
    ("factor_kind", "value", "validator", "error_code"),
    [
        (
            "visual",
            {
                "visual_description": "A hand lifts a metal bowl.",
                "visual_query": "metal bowl a hand lifts",
            },
            "validate_visual_factor_output",
            "MODEL_VISUAL_QUERY_DESCRIPTION_IDENTITY",
        ),
        (
            "ambient",
            {
                "ambient_description": "A door creaks open.",
                "ambient_query": "open a door creaks",
            },
            "validate_legacy_ambient_factor_output",
            "MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY",
        ),
    ],
)
def test_r12_identity_is_schema_repair_ineligible_and_makes_one_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factor_kind: str,
    value: dict[str, str],
    validator: str,
    error_code: str,
) -> None:
    tool = load_tool()
    generation_calls = []

    def fake_generate(*args, **kwargs):
        del args
        generation_calls.append(kwargs)
        return json.dumps(value), {
            "rendered_prompt": "exact prompt",
            "rendered_prompt_sha256": tool.semantic_hash("exact prompt"),
            "rendered_prompt_bytes": 12,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "generation_seconds": 0.1,
            "network_attempts": 0,
            **_constraint_metadata(tool, kwargs["factor_kind"]),
        }

    monkeypatch.setattr(tool, "_generate_one", fake_generate)
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    manifest = tool.build_prompt_manifest(
        {
            "families": [family],
            "targets": structural["targets"][:1],
            "counts": {},
        }
    )
    prompt = (
        manifest["visual_prompts"][0]
        if factor_kind == "visual"
        else manifest["ambient_prompts"][0]
    )
    attempts_path = tmp_path / f"{factor_kind}-attempts.jsonl"
    media_hash_key = (
        "video_sha256" if factor_kind == "visual" else "audio_sha256"
    )
    with pytest.raises(tool.AuthoringError, match=error_code):
        tool.author_factor(
            object(),
            object(),
            object(),
            family_key=family["family_key"],
            factor_key=f"{family['family_key']}:component:1:{factor_kind}",
            factor_kind=factor_kind,
            component_ordinal=1,
            prompt=prompt,
            validator=getattr(tool, validator),
            semantic_fields=frozenset(
                tool.VISUAL_OUTPUT_SCHEMA
                if factor_kind == "visual"
                else {"ambient_description", "ambient_query"}
            ),
            videos=[object()] if factor_kind == "visual" else None,
            audios=[object()] if factor_kind == "ambient" else None,
            clip_records=[
                {
                    "clip_key": family["intervals"][0]["clip_key"],
                    media_hash_key: "sha256:media",
                }
            ],
            model_identity={"repo_id": "mock"},
            attempts=[],
            attempts_path=attempts_path,
        )
    rows = [
        json.loads(line)
        for line in attempts_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(generation_calls) == 1
    assert len(rows) == 1
    assert rows[0]["parser_error"].startswith(error_code)
    assert rows[0]["schema_only_repair_eligible"] is False


def test_r12_near_identity_remains_a_later_audit_gate() -> None:
    tool = load_tool()
    _, (queries, descriptions) = _semantic_fixture(tool)
    visual_query = next(
        row for row in queries if row["query_kind"] == "visual"
    )
    visual_description = next(
        row for row in descriptions if row["description_kind"] == "visual"
    )
    visual_query["query_text"] = (
        "operator slices fresh green vegetables carefully on a wooden "
        "cutting board"
    )
    visual_description["description_text"] = (
        "An operator slices fresh green vegetables carefully on a wooden "
        "cutting board."
    )
    audit = tool.query_description_identity_audit(queries, descriptions)
    assert audit["status"] == "FAIL"
    finding = next(
        row
        for row in audit["findings"]
        if row["query_key"] == visual_query["query_key"]
    )
    assert finding["normalized_equal"] is False
    assert finding["token_sets_equal"] is False
    assert finding["jaccard"] >= tool.QUERY_DESCRIPTION_IDENTITY_THRESHOLD


def test_cardinality_mismatch_is_nonretryable_legacy_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    component = {
        key: _valid_model_value()[key]
        for key in tool.VISUAL_OUTPUT_SCHEMA
    }
    value = {
        "components": [
            {"ordinal": 1, **component},
            {"ordinal": 2, **component},
        ],
        **_valid_composition_value(),
    }
    calls = 0

    def fake_generate(*args, **kwargs):
        nonlocal calls
        del args
        calls += 1
        return json.dumps(value), {
            "rendered_prompt": "prompt",
            "rendered_prompt_sha256": tool.semantic_hash("prompt"),
            "rendered_prompt_bytes": 6,
            **_constraint_metadata(tool, kwargs["factor_kind"]),
        }

    monkeypatch.setattr(tool, "_generate_one", fake_generate)
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    prompt = tool.build_prompt_manifest(
        {"families": [family], "targets": [], "counts": {}}
    )["visual_prompts"][0]
    with pytest.raises(
        tool.AuthoringError, match="MODEL_COMPONENT_COUNT_MISMATCH"
    ):
        tool.author_factor(
            object(),
            object(),
            object(),
            family_key=family["family_key"],
            factor_key=f"{family['family_key']}:component:1:visual",
            factor_kind="visual",
            component_ordinal=1,
            prompt=prompt,
            validator=tool.validate_visual_factor_output,
            semantic_fields=frozenset(tool.VISUAL_OUTPUT_SCHEMA),
            videos=[object()],
            audios=None,
            clip_records=[
                {
                    "clip_key": family["intervals"][0]["clip_key"],
                    "video_sha256": "sha256:video",
                }
            ],
            model_identity={"repo_id": "mock"},
            attempts=[],
            attempts_path=tmp_path / "attempts.jsonl",
        )
    assert calls == 1


def test_unclosed_json_at_token_cap_fails_and_records_stop_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()

    def fake_generate(*args, **kwargs):
        del args
        return '{"components":[', {
            "rendered_prompt": "prompt{",
            "rendered_prompt_sha256": tool.semantic_hash("prompt{"),
            "rendered_prompt_bytes": 7,
            "prompt_tokens": 11,
            "prompt_tokens_excluding_prefill": 10,
            "completion_tokens": tool.MAX_NEW_TOKENS,
            "model_generated_tokens": tool.MAX_NEW_TOKENS,
            "assistant_prefill": "{",
            "assistant_prefill_tokens": 1,
            "constrained_output_tokens": tool.MAX_NEW_TOKENS + 1,
            "generation_token_cap": tool.MAX_NEW_TOKENS,
            "stop_reason": "json_object_unclosed_at_token_cap",
            **_constraint_metadata(tool, kwargs["factor_kind"]),
        }

    monkeypatch.setattr(tool, "_generate_one", fake_generate)
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    prompt = tool.build_prompt_manifest(
        {"families": [family], "targets": [], "counts": {}}
    )["visual_prompts"][0]
    attempts_path = tmp_path / "attempts.jsonl"
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_OUTPUT_JSON_UNCLOSED_AT_TOKEN_CAP",
    ):
        tool.author_factor(
            object(),
            object(),
            object(),
            family_key=family["family_key"],
            factor_key=f"{family['family_key']}:component:1:visual",
            factor_kind="visual",
            component_ordinal=1,
            prompt=prompt,
            validator=tool.validate_visual_factor_output,
            semantic_fields=frozenset(tool.VISUAL_OUTPUT_SCHEMA),
            videos=[object()],
            audios=None,
            clip_records=[
                {
                    "clip_key": family["intervals"][0]["clip_key"],
                    "video_sha256": "sha256:video",
                }
            ],
            model_identity={"repo_id": "mock"},
            attempts=[],
            attempts_path=attempts_path,
        )
    row = json.loads(attempts_path.read_text(encoding="utf-8"))
    assert row["parser_error"] == (
        "MODEL_OUTPUT_JSON_UNCLOSED_AT_TOKEN_CAP"
    )
    assert row["stop_reason"] == "json_object_unclosed_at_token_cap"
    assert row["assistant_prefill_tokens"] == 1
    assert row["model_generated_tokens"] == tool.MAX_NEW_TOKENS


def test_failure_capsule_survives_staging_cleanup(tmp_path: Path) -> None:
    tool = load_tool()
    staging = tmp_path / ".out.staging-test"
    (staging / "clips/clip-001").mkdir(parents=True)
    (staging / "clips/clip-001/video.npy").write_bytes(b"ephemeral")
    tool.atomic_json(staging / "prompt_manifest.json", {"exact": "prompt"})
    tool.atomic_jsonl(
        staging / "raw_attempts.jsonl",
        [{"raw_output": "not strict json", "parser_error": "parse"}],
    )
    output = tmp_path / "out"
    capsule = tool.install_failure_capsule(
        staging,
        output_path=output,
        authorization_id='PUBLIC_REDACTED_IDENTIFIER',
        exc=tool.AuthoringError("MODEL_OUTPUT_NOT_STRICT_JSON"),
        wall_started=0.0,
        stage_times={"omni_authoring_seconds": 1.0},
        failed_stage="omni_authoring",
    )
    assert not staging.exists()
    assert capsule.is_dir()
    assert not (capsule / "clips").exists()
    assert "not strict json" in (
        capsule / "raw_attempts.jsonl"
    ).read_text(encoding="utf-8")
    failure = json.loads(
        (capsule / "failure_capsule.json").read_text(encoding="utf-8")
    )
    assert failure["raw_model_evidence_retained"] is True
    assert failure["ephemeral_clip_arrays_removed"] is True


def test_explicit_template_baseline_is_separate_and_ineligible() -> None:
    tool = load_tool()
    baseline = tool.explicit_template_baseline(
        tool._synthetic_structural()
    )
    assert baseline["baseline_id"] == "EXPLICIT_TEMPLATE_ONLY_BASELINE"
    assert baseline["excluded_from_primary_queries"] is True
    assert all(
        row["template_only_control"] is True
        and row["content_grounded"] is False
        and row["eligible_for_primary_query_set"] is False
        and row["eligible_for_scientific_scoring"] is False
        for row in baseline["rows"]
    )


def test_execute_requires_external_authorization_before_any_run(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--execute",
            "--repo-root",
            str(ROOT),
            "--output",
            str(tmp_path / "out"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION_RECEIPT" in (
        completed.stderr
    )
    assert not (tmp_path / "out").exists()


def test_public_full_pipeline_validator_never_claims_execution_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = load_tool()
    monkeypatch.setattr(
        tool,
        "validate_output_integrity_only",
        lambda root, output=tool.DEFAULT_OUTPUT: {
            "passed": True,
            "validation_level": "INTEGRITY_ONLY_NOT_EXECUTION_ATTESTED",
            "input_authorization_verified": False,
            "execution_attested": False,
            "externally_attested": False,
        },
    )
    with pytest.raises(
        tool.AuthoringError,
        match="OUTPUT_EXECUTION_ATTESTATION_UNAVAILABLE",
    ):
        tool.validate_output(ROOT)


def test_plan_is_sealed_and_records_no_real_execution() -> None:
    tool = load_tool()
    plan = tool.validate_plan(ROOT)
    assert plan["decision"] == tool.READY
    assert plan["scope"]["real_execution_performed"] is False
    assert plan["scope"]["authorization_receipt_created"] is False
    assert plan["scope"]["retrieval_scoring_performed"] is False
    assert plan["target_scope"]["unique_exact_target_clips"] == 28
    assert plan["target_scope"]["primary_query_count"] == 76
    assert plan["resource_estimate"]["network_requests"] == 0
    assert "accepted_factor_manifest.json" in plan[
        "artifacts_for_future_authorized_run"
    ]
    assert plan["schema_version"].endswith("/23.0")
    assert plan["plan_payload_sha256"] == tool.semantic_hash(
        {k: v for k, v in plan.items() if k != "plan_payload_sha256"}
    )
    status = tool.plan_status(ROOT)
    assert status["current"] is True
    assert status["plan_pipeline_hash_current"] is True
    assert status["old_authorization_receipts_valid"] is False


def test_cli_plan_and_synthetic_self_test_are_model_free() -> None:
    tool = load_tool()
    for mode in ("--plan", "--synthetic-self-test"):
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                mode,
                "--repo-root",
                str(ROOT),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(completed.stdout)
        assert result["status"] == tool.READY
        assert result["repair_status"] == (
            "P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY"
        )
        assert result["constrained_json_status"] == (
            "P23_102_QUERY_AUTHORING_CONSTRAINED_JSON_READY"
        )
        assert result["model_calls"] == 0
        assert result["media_decodes"] == 0


def test_english_only_whisper_audit_omits_language_and_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = load_tool()
    import numpy as np
    import transformers

    audio_path = tmp_path / "audio.npy"
    np.save(audio_path, np.zeros(1600, dtype=np.float32), allow_pickle=False)
    observed: list[dict[str, object]] = []

    class FakeTranscriber:
        def __call__(self, inputs: object, **kwargs: object) -> dict[str, str]:
            observed.append(dict(kwargs))
            return {"text": ""}

    monkeypatch.setattr(
        transformers,
        "pipeline",
        lambda *args, **kwargs: FakeTranscriber(),
    )
    monkeypatch.setattr(
        tool,
        "deny_network",
        lambda: nullcontext({"count": 0}),
    )

    tool._run_asr(ROOT, {"clip-001": {"audio": audio_path}})
    assert observed == [{}]


def test_text_embedder_unwraps_pooler_output(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool()

    class FakeTensor:
        def norm(self, dim: int, keepdim: bool):
            assert dim == -1 and keepdim is True
            return self

        def __truediv__(self, other):
            assert other is self
            return self

        def float(self):
            return self

        def cpu(self):
            return self

        def tolist(self):
            return [[1.0, 0.0]]

    class FakeOutput:
        pooler_output = FakeTensor()

    class FakeModel:
        def eval(self):
            return self

        def get_text_features(self, **kwargs):
            return FakeOutput()

    class FakeProcessor:
        def __call__(self, **kwargs):
            return {"input_ids": [[1]], "attention_mask": [[1]]}

    class FakeAutoProcessor:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return FakeProcessor()

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return FakeModel()

    import transformers
    monkeypatch.setattr(transformers, "AutoProcessor", FakeAutoProcessor)
    monkeypatch.setattr(transformers, "AutoModel", FakeAutoModel)
    monkeypatch.setattr(tool, "deny_network", lambda: nullcontext({"count": 0}))

    embed = tool._text_embedder(ROOT, tool.SIGLIP_SNAPSHOT)
    assert embed(["query"]) == [[1.0, 0.0]]


def _structured_ambient(
    event_kind: str = "tap",
    *,
    timbre="metallic",
    loudness="soft",
    temporal_pattern="brief",
):
    return {
        "event_kind": event_kind,
        "acoustic_properties": {
            "timbre": timbre,
            "loudness": loudness,
            "temporal_pattern": temporal_pattern,
        },
    }


def test_r18_structured_tap_metallic_passes_and_is_mechanical() -> None:
    tool = load_tool()
    accepted = tool.validate_ambient_factor_output(
        _structured_ambient()
    )
    assert accepted["ambient_semantics"]["event_kind"] == "tap"
    assert "metallic" in accepted["ambient_description"]
    assert "metallic" in accepted["ambient_query"]
    assert "metal object" not in (
        accepted["ambient_description"] + accepted["ambient_query"]
    ).casefold()
    assert accepted["ambient_registry_sha256"] == (
        tool.STRUCTURED_AMBIENT_REGISTRY_SHA256
    )
    assert accepted["ambient_generator_sha256"] == (
        tool.AMBIENT_GENERATOR_SHA256
    )
    assert accepted["ambient_template_sha256"] == (
        tool.AMBIENT_TEMPLATE_SHA256
    )


def test_r18_actual_tuple_example_has_exact_frozen_strings_and_parse_back() -> None:
    tool = load_tool()
    semantic = _structured_ambient(
        "creak",
        timbre="hollow",
        loudness="soft",
        temporal_pattern="repeated",
    )
    accepted = tool.validate_ambient_factor_output(semantic)
    assert accepted["ambient_description"] == (
        "A soft repeated hollow creak is audible."
    )
    assert accepted["ambient_query"] == (
        "Find the audible creak event matching "
        "hollow, repeated, soft."
    )
    assert tool.parse_ambient_description(
        accepted["ambient_description"]
    ) == tool.validate_ambient_semantic_tuple(semantic)
    assert tool.parse_ambient_query(
        accepted["ambient_query"]
    ) == tool.validate_ambient_semantic_tuple(semantic)


def test_r18_template_spec_drives_manifest_hash_and_generator_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = load_tool()
    changed = json.loads(json.dumps(tool.AMBIENT_TEMPLATE_SPEC))
    changed["query"]["property_separator"] = " | "
    original = tool.ambient_derivation_hashes(tool.AMBIENT_TEMPLATE_SPEC)
    updated = tool.ambient_derivation_hashes(changed)
    assert updated["template_sha256"] != original["template_sha256"]
    assert updated["generator_sha256"] != original["generator_sha256"]
    assert updated["generator_manifest"]["template_sha256"] == (
        updated["template_sha256"]
    )
    assert updated["template_manifest"]["template_spec"] == changed
    monkeypatch.setattr(tool, "AMBIENT_TEMPLATE_SPEC", changed)
    monkeypatch.setattr(
        tool, "AMBIENT_TEMPLATE_MANIFEST", updated["template_manifest"]
    )
    monkeypatch.setattr(
        tool, "AMBIENT_TEMPLATE_SHA256", updated["template_sha256"]
    )
    monkeypatch.setattr(
        tool, "AMBIENT_GENERATOR_MANIFEST", updated["generator_manifest"]
    )
    monkeypatch.setattr(
        tool, "AMBIENT_GENERATOR_SHA256", updated["generator_sha256"]
    )
    derived = tool.derive_ambient_texts(_structured_ambient())
    assert derived["ambient_query"] == (
        "Find the audible tap event matching metallic | brief | soft."
    )
    assert tool.parse_ambient_query(
        derived["ambient_query"], spec=changed
    ) == tool.validate_ambient_semantic_tuple(_structured_ambient())


def test_r18_template_manifest_implementation_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = load_tool()
    monkeypatch.setattr(
        tool,
        "AMBIENT_TEMPLATE_MANIFEST",
        {
            **tool.AMBIENT_TEMPLATE_MANIFEST,
            "template_spec": {
                **tool.AMBIENT_TEMPLATE_SPEC,
                "null_rendering": "tampered",
            },
        },
    )
    with pytest.raises(
        tool.AuthoringError,
        match="AMBIENT_TEMPLATE_MANIFEST_IMPLEMENTATION_MISMATCH",
    ):
        tool.derive_ambient_texts(_structured_ambient())


def test_r18_query_property_omission_makes_self_audit_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = load_tool()
    original = tool.derive_ambient_texts

    def omit_one_query_property(value):
        derived = original(value)
        semantic = tool.validate_ambient_semantic_tuple(value)
        if (
            semantic["event_kind"] == "alarm"
            and semantic["acoustic_properties"]["timbre"] == "metallic"
        ):
            derived["ambient_query"] = derived["ambient_query"].replace(
                "metallic, ", "", 1
            ).replace("matching metallic.", "matching .", 1)
        return derived

    monkeypatch.setattr(tool, "derive_ambient_texts", omit_one_query_property)
    with pytest.raises(
        tool.AuthoringError,
        match="AMBIENT_SELF_AUDIT_PARSE_BACK_FAILED",
    ):
        tool.structured_ambient_generator_self_audit()


@pytest.mark.parametrize(
    ("semantic", "description_fragment", "query_fragment"),
    [
        (_structured_ambient(), "metallic ", "metallic, "),
        (_structured_ambient(), "soft ", ", soft"),
        (_structured_ambient(), "brief ", "brief, "),
    ],
)
def test_r18_omitting_any_derived_property_fails_validator(
    semantic: dict,
    description_fragment: str,
    query_fragment: str,
) -> None:
    tool = load_tool()
    for field, fragment in (
        ("ambient_description", description_fragment),
        ("ambient_query", query_fragment),
    ):
        accepted = tool._accepted_ambient_factor(semantic)
        accepted[field] = accepted[field].replace(fragment, "", 1)
        with pytest.raises(tool.AuthoringError, match="ACCEPTED_AMBIENT"):
            tool.validate_accepted_ambient_factor(accepted)


@pytest.mark.parametrize(
    "value,error",
    [
        (
            {
                "ambient_description": "A metal object is tapped.",
                "ambient_query": "metal object is tapped",
            },
            "MODEL_AMBIENT_FACTOR_FIELD_SET_MISMATCH",
        ),
        (
            _structured_ambient("open"),
            "MODEL_AMBIENT_EVENT_KIND_ENUM_INVALID",
        ),
        (
            _structured_ambient("place"),
            "MODEL_AMBIENT_EVENT_KIND_ENUM_INVALID",
        ),
        (
            {
                **_structured_ambient(),
                "source_hint": "metal_object",
            },
            "MODEL_AMBIENT_SOURCE_HINT_FIELD_FORBIDDEN",
        ),
    ],
)
def test_r18_free_text_fact_source_and_action_enums_fail_closed(
    value, error
) -> None:
    tool = load_tool()
    with pytest.raises(tool.AuthoringError, match=error):
        tool.validate_ambient_factor_output(value)


@pytest.mark.parametrize(
    "event_kind",
    ["tap", "click", "scrape", "knock", "clank", "hiss", "throat_clear"],
)
def test_r18_audit_event_registry_examples_pass(event_kind: str) -> None:
    tool = load_tool()
    accepted = tool.validate_ambient_factor_output(
        _structured_ambient(event_kind, timbre=None)
    )
    assert accepted["ambient_semantics"]["event_kind"] == event_kind


@pytest.mark.parametrize("source_hint", ["paper", "bell_like", None])
def test_r18_source_hint_is_forbidden_at_any_value(source_hint) -> None:
    tool = load_tool()
    value = {
        **_structured_ambient("crinkle", timbre="crisp",
                              loudness="soft",
                              temporal_pattern="repeated"),
        "source_hint": source_hint,
    }
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_SOURCE_HINT_FIELD_FORBIDDEN",
    ):
        tool.validate_ambient_factor_output(value)


def test_r18_raw_paper_regression_rejected_but_pure_acoustic_tuple_passes() -> None:
    tool = load_tool()
    raw_r17 = {
        **_structured_ambient(
            "crinkle",
            timbre="crisp",
            loudness="soft",
            temporal_pattern="repeated",
        ),
        "source_hint": "paper",
    }
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_SOURCE_HINT_FIELD_FORBIDDEN",
    ):
        tool.validate_ambient_factor_output(raw_r17)
    accepted = tool.validate_ambient_factor_output(
        _structured_ambient(
            "crinkle",
            timbre="crisp",
            loudness="soft",
            temporal_pattern="repeated",
        )
    )
    assert accepted["ambient_description"] == (
        "A soft repeated crisp crinkle is audible."
    )
    assert accepted["ambient_query"] == (
        "Find the audible crinkle event matching crisp, repeated, soft."
    )
    assert tool.ambient_semantic_content_atoms(
        accepted["ambient_semantics"]
    ) == (
        "event_kind:crinkle",
        "timbre:crisp",
        "loudness:soft",
        "temporal_pattern:repeated",
    )


def test_r19_raw_and_accepted_ambient_boundaries_fail_closed() -> None:
    tool = load_tool()
    raw = _structured_ambient(
        "crinkle",
        timbre="crisp",
        loudness="soft",
        temporal_pattern="repeated",
    )
    accepted = tool.validate_ambient_factor_output(raw)
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_FACTOR_FIELD_SET_MISMATCH",
    ):
        tool.validate_ambient_factor_output(accepted)
    with pytest.raises(
        tool.AuthoringError,
        match="ACCEPTED_AMBIENT_FACTOR_FIELD_SET_MISMATCH",
    ):
        tool.validate_accepted_ambient_factor(raw)


def test_r19_assembly_preserves_complete_accepted_ambient_factor() -> None:
    tool = load_tool()
    family = {
        "family_key": "family-r19-local",
        "shape": "one_component",
        "intervals": [{"clip_key": "clip-r19-local"}],
    }
    visual = {
        "visual_description": "A hand folds a flexible sheet.",
        "visual_query": "hand folding a flexible sheet",
    }
    accepted = tool.validate_ambient_factor_output(
        _structured_ambient(
            "crinkle",
            timbre="crisp",
            loudness="soft",
            temporal_pattern="repeated",
        )
    )
    assembled = tool.assemble_family_factors(
        family,
        [visual],
        [accepted],
        {"relation_kind": "local_cooccurrence"},
    )
    component = assembled["components"][0]
    assert {
        key: component[key] for key in tool.AMBIENT_ACCEPTED_FIELDS
    } == accepted
    assert component["ambient_semantics"] == accepted["ambient_semantics"]
    assert component["ambient_derived_text_sha256"] == (
        accepted["ambient_derived_text_sha256"]
    )


def test_r19_composition_projection_accepts_only_complete_accepted_factors() -> None:
    tool = load_tool()
    accepted = tool.validate_ambient_factor_output(
        _structured_ambient(
            "crinkle",
            timbre="crisp",
            loudness="soft",
            temporal_pattern="repeated",
        )
    )
    component = {
        "visual_description": "A hand folds a flexible sheet.",
        "visual_query": "hand folding a flexible sheet",
        **accepted,
    }
    payload = tool.composition_model_visible_prompt(
        "one_component", [component]
    )
    assert payload["constraints"]["accepted_component_factor_count"] == 1
    assert "ambient_semantics" not in tool.canonical_bytes(payload).decode(
        "utf-8"
    )
    with pytest.raises(
        tool.AuthoringError,
        match="ACCEPTED_COMPONENT_FACTOR_FIELD_SET_MISMATCH",
    ):
        tool.composition_model_visible_prompt(
            "one_component",
            [
                {
                    **component,
                    "ambient_semantics": component["ambient_semantics"],
                    "extra": "unvalidated",
                }
            ],
        )


def test_r19_parsed_output_hash_binds_accepted_ambient_semantics() -> None:
    tool = load_tool()
    raw = _structured_ambient(
        "crinkle",
        timbre="crisp",
        loudness="soft",
        temporal_pattern="repeated",
    )
    accepted = tool.validate_ambient_factor_output(raw)
    assert tool._parsed_output_binding_hash("ambient", accepted) == (
        tool.semantic_hash(accepted["ambient_semantics"])
    )
    tampered = dict(accepted)
    tampered["ambient_query_sha256"] = "sha256:tampered"
    with pytest.raises(tool.AuthoringError, match="ACCEPTED_AMBIENT"):
        tool._parsed_output_binding_hash("ambient", tampered)


def test_r19_author_one_family_exact_r18_tuple_assembles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    target = structural["targets"][0]
    manifest = tool.build_prompt_manifest(
        {
            "families": [family],
            "targets": [target],
            "counts": {},
        }
    )
    raw_outputs = iter(
        [
            json.dumps(
                {
                    "visual_description": "A hand folds a flexible sheet.",
                    "visual_query": "hand folding a flexible sheet",
                }
            ),
            json.dumps(
                _structured_ambient(
                    "crinkle",
                    timbre="crisp",
                    loudness="soft",
                    temporal_pattern="repeated",
                )
            ),
            json.dumps({"relation_kind": "local_cooccurrence"}),
        ]
    )

    def fake_generate(*args, **kwargs):
        del args
        raw = next(raw_outputs)
        factor_kind = kwargs["factor_kind"]
        return raw, {
            "rendered_prompt": "synthetic-r19-prompt",
            "rendered_prompt_sha256": tool.semantic_hash(
                "synthetic-r19-prompt"
            ),
            "rendered_prompt_bytes": len("synthetic-r19-prompt"),
            "stop_reason": (
                "ambient_constraint_leaf_stop"
                if factor_kind == "ambient"
                else "first_complete_top_level_json_object"
            ),
            **_constraint_metadata(tool, factor_kind),
        }

    monkeypatch.setattr(tool, "_generate_one", fake_generate)
    attempts: list[dict] = []
    parsed, calls = tool.author_one_family(
        object(),
        object(),
        object(),
        family=family,
        visual_prompts=manifest["visual_prompts"],
        ambient_prompts=manifest["ambient_prompts"],
        videos=[object()],
        audios=[object()],
        clip_records=[
            {
                **target,
                "video_sha256": "sha256:video",
                "audio_sha256": "sha256:audio",
            }
        ],
        model_identity={"repo_id": "synthetic"},
        attempts=attempts,
        attempts_path=tmp_path / "attempts.jsonl",
    )
    assert calls == 3
    assert parsed["components"][0]["ambient_semantics"] == (
        _structured_ambient(
            "crinkle",
            timbre="crisp",
            loudness="soft",
            temporal_pattern="repeated",
        )
    )
    assert parsed["components"][0]["ambient_description"] == (
        "A soft repeated crisp crinkle is audible."
    )
    ambient_attempt = next(
        row for row in attempts if row["factor_kind"] == "ambient"
    )
    assert ambient_attempt["parsed_output_sha256"] == tool.semantic_hash(
        parsed["components"][0]["ambient_semantics"]
    )


def test_r18_schema_registry_template_and_prompt_are_source_free() -> None:
    tool = load_tool()
    assert set(tool.AMBIENT_OUTPUT_SCHEMA) == {
        "event_kind",
        "acoustic_properties",
    }
    assert set(tool.AMBIENT_OUTPUT_SCHEMA["acoustic_properties"]) == {
        "timbre",
        "loudness",
        "temporal_pattern",
    }
    assert "source_hint" not in tool.STRUCTURED_AMBIENT_REGISTRY_MANIFEST
    assert "source_hint_compatibility" not in (
        tool.STRUCTURED_AMBIENT_REGISTRY_MANIFEST
    )
    serialized_template = json.dumps(
        tool.AMBIENT_TEMPLATE_SPEC, sort_keys=True
    )
    assert "source_hint" not in serialized_template
    prompt = tool.ambient_model_visible_prompt()
    assert set(prompt["required_output_schema"]) == {
        "event_kind",
        "acoustic_properties",
    }
    constraints = prompt["constraints"]
    assert constraints[
        "source_material_object_agent_location_direction_forbidden"
    ] is True
    assert constraints["source_hint_field_forbidden_even_when_null"] is True
    for forbidden in (
        "source",
        "material",
        "object",
        "agent",
        "location",
        "direction",
    ):
        assert forbidden in tool.AMBIENT_SYSTEM_PROMPT.casefold()


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("ambient_query", "Find the paper tap."),
        ("ambient_query", "Find the button click."),
        ("ambient_query", "Find the person making a tap."),
        ("ambient_query", "Find the opening creak."),
        ("ambient_description", "A metallic tap is audible to the left."),
    ],
)
def test_r18_derived_text_semantic_tamper_fails(
    field: str, tampered: str
) -> None:
    tool = load_tool()
    accepted = tool._accepted_ambient_factor(_structured_ambient())
    accepted[field] = tampered
    with pytest.raises(tool.AuthoringError, match="ACCEPTED_AMBIENT"):
        tool.validate_accepted_ambient_factor(accepted)


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "swap",
        "copy",
        "registry_hash",
        "generator_hash",
        "template_hash",
        "tuple_hash",
    ],
)
def test_r18_swap_copy_and_hash_tamper_fail_closed(
    tamper_kind: str,
) -> None:
    tool = load_tool()
    accepted = tool._accepted_ambient_factor(_structured_ambient())
    if tamper_kind == "swap":
        accepted["ambient_description"], accepted["ambient_query"] = (
            accepted["ambient_query"],
            accepted["ambient_description"],
        )
    elif tamper_kind == "copy":
        accepted["ambient_query"] = accepted["ambient_description"]
    elif tamper_kind == "registry_hash":
        accepted["ambient_registry_sha256"] = "sha256:tampered"
    elif tamper_kind == "generator_hash":
        accepted["ambient_generator_sha256"] = "sha256:tampered"
    elif tamper_kind == "template_hash":
        accepted["ambient_template_sha256"] = "sha256:tampered"
    else:
        accepted["ambient_semantic_tuple_sha256"] = "sha256:tampered"
    with pytest.raises(tool.AuthoringError, match="ACCEPTED_AMBIENT"):
        tool.validate_accepted_ambient_factor(accepted)


def test_r18_schema_repair_requires_exact_semantic_scalars() -> None:
    tool = load_tool()
    semantic = _structured_ambient()
    wrapped = {"result": semantic}
    candidate = tool._schema_repair_candidate(
        json.dumps(wrapped),
        "MODEL_AMBIENT_FACTOR_FIELD_SET_MISMATCH",
        semantic_fields=tool.AMBIENT_SEMANTIC_SCALAR_FIELDS,
    )
    assert candidate == wrapped
    changed = _structured_ambient(timbre="hollow")
    assert tool._semantic_scalar_multiset(candidate) != (
        tool._semantic_scalar_multiset(changed)
    )
    assert (
        tool._schema_repair_candidate(
            json.dumps(_structured_ambient("open")),
            "MODEL_AMBIENT_EVENT_KIND_ENUM_INVALID",
            semantic_fields=tool.AMBIENT_SEMANTIC_SCALAR_FIELDS,
        )
        is None
    )
    source_hint_raw = {
        **semantic,
        "source_hint": "paper",
    }
    assert (
        tool._schema_repair_candidate(
            json.dumps(source_hint_raw),
            "MODEL_AMBIENT_SOURCE_HINT_FIELD_FORBIDDEN",
            semantic_fields=tool.AMBIENT_SEMANTIC_SCALAR_FIELDS,
        )
        is None
    )
    assert (
        tool._schema_repair_candidate(
            json.dumps(source_hint_raw),
            "MODEL_AMBIENT_FACTOR_FIELD_SET_MISMATCH",
            semantic_fields=tool.AMBIENT_SEMANTIC_SCALAR_FIELDS,
        )
        is None
    )


def test_r18_exhaustive_generator_allowlist_and_round_trip() -> None:
    tool = load_tool()
    audit = tool.structured_ambient_generator_self_audit()
    assert audit["status"] == "PASS"
    assert audit["event_kind_count"] == 64
    assert audit["combination_count"] == 7680
    assert audit["unique_pair_count"] == 7680
    assert audit["independent_description_parse_back_count"] == 7680
    assert audit["independent_query_parse_back_count"] == 7680
    assert audit["constraint_leaf_count"] == 7680
    assert audit["constraint_reachable_count"] == 7680


def _local_ambient_constraint(tool, local_omni_processor):
    class Config:
        is_encoder_decoder = False
        eos_token_id = local_omni_processor.tokenizer.eos_token_id

    class Model:
        config = Config()

    return tool.ambient_token_prefix_constraint(
        local_omni_processor.tokenizer,
        Model(),
        assistant_prefill="{",
    )


def test_r20_qwen_token_trie_exhaustively_reaches_all_7680_leaves(
    local_omni_processor,
) -> None:
    tool = load_tool()
    constraint = _local_ambient_constraint(tool, local_omni_processor)
    assert len(constraint.leaf_nodes) == 7680
    assert constraint.reachable_count == 7680
    assert len(constraint.token_paths) == 7680
    assert constraint.metadata()["constraint_kind"] == (
        tool.AMBIENT_CONSTRAINT_KIND
    )
    for canonical, token_ids in constraint.token_paths.items():
        assert canonical.startswith("{")
        assert constraint.path_reachable(token_ids)
        assert (
            "{"
            + local_omni_processor.tokenizer.decode(
                list(token_ids),
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            == canonical
        )
        assert constraint.allowed_token_ids(token_ids) == (
            constraint.stop_token_ids
        )


@pytest.mark.parametrize("event_kind", ["pour", "open", "chop", "stir", "drop"])
def test_r20_illegal_action_canonical_strings_are_unreachable(
    local_omni_processor, event_kind: str
) -> None:
    tool = load_tool()
    constraint = _local_ambient_constraint(tool, local_omni_processor)
    illegal = tool.canonical_bytes(
        {
            "event_kind": event_kind,
            "acoustic_properties": {
                "timbre": None,
                "loudness": None,
                "temporal_pattern": None,
            },
        }
    ).decode("utf-8")
    assert not constraint.canonical_string_reachable(illegal)


def test_r20_token_preference_for_illegal_actions_cannot_leave_trie(
    local_omni_processor,
) -> None:
    import torch

    tool = load_tool()
    constraint = _local_ambient_constraint(tool, local_omni_processor)
    processor = tool._AmbientTupleTrieLogitsProcessor(
        constraint=constraint,
        generated_start=0,
    )
    legal = tool.canonical_ambient_tuple_json(
        {
            "event_kind": "continuous_liquid_flow",
            "acoustic_properties": {
                "timbre": None,
                "loudness": None,
                "temporal_pattern": None,
            },
        }
    )
    illegal = tool.canonical_bytes(
        {
            "event_kind": "pour",
            "acoustic_properties": {
                "timbre": None,
                "loudness": None,
                "temporal_pattern": None,
            },
        }
    ).decode("utf-8")
    legal_ids = constraint.token_paths[legal]
    illegal_ids = local_omni_processor.tokenizer.encode(
        illegal[1:], add_special_tokens=False
    )
    shared = 0
    for legal_id, illegal_id in zip(legal_ids, illegal_ids, strict=False):
        if legal_id != illegal_id:
            break
        shared += 1
    assert shared < len(legal_ids)
    input_ids = torch.tensor([legal_ids[:shared]], dtype=torch.long)
    scores = torch.zeros(
        (1, local_omni_processor.tokenizer.vocab_size), dtype=torch.float32
    )
    scores[0, illegal_ids[shared]] = 1000.0
    bounded = processor(input_ids, scores)
    assert torch.isneginf(bounded[0, illegal_ids[shared]])
    assert int(bounded.argmax(dim=-1).item()) in (
        constraint.allowed_token_ids(legal_ids[:shared])
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: json.dumps(value, separators=(",", ":")),
        lambda value: tool_json_with_reordered_properties(value),
        lambda value: tool_json_with_extra_key(value),
    ],
)
def test_r20_field_order_enum_and_schema_are_token_constrained(
    local_omni_processor, mutator
) -> None:
    tool = load_tool()
    constraint = _local_ambient_constraint(tool, local_omni_processor)
    value = {
        "event_kind": "click",
        "acoustic_properties": {
            "timbre": "crisp",
            "loudness": "soft",
            "temporal_pattern": "brief",
        },
    }
    candidate = mutator(value)
    assert candidate != tool.canonical_ambient_tuple_json(value)
    assert not constraint.canonical_string_reachable(candidate)


def tool_json_with_reordered_properties(value: dict) -> str:
    properties = value["acoustic_properties"]
    return (
        '{"acoustic_properties":{'
        f'"timbre":{json.dumps(properties["timbre"])},'
        f'"loudness":{json.dumps(properties["loudness"])},'
        '"temporal_pattern":'
        f'{json.dumps(properties["temporal_pattern"])}'
        f'}},"event_kind":{json.dumps(value["event_kind"])}}}'
    )


def tool_json_with_extra_key(value: dict) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return canonical[:-1] + ',"extra":null}'


def test_r20_continuous_liquid_flow_ontology_and_confusion_suite() -> None:
    tool = load_tool()
    assert len(tool.STRUCTURED_AMBIENT_EVENT_KINDS) == 64
    assert "continuous_liquid_flow" in tool.STRUCTURED_AMBIENT_EVENT_KINDS
    assert "pour" not in tool.STRUCTURED_AMBIENT_EVENT_KINDS
    registry = tool.STRUCTURED_AMBIENT_REGISTRY_MANIFEST
    assert registry["event_definitions"]["continuous_liquid_flow"]
    assert set(
        registry["event_confusions"]["continuous_liquid_flow"]
    ) == {"drip", "trickle", "slosh", "splash", "gurgle", "bubble"}
    prompt = tool.ambient_model_visible_prompt()
    assert "continuous_liquid_flow" in prompt["event_kind_definition"]
    audit = tool.liquid_confusion_synthetic_suite()
    assert audit["status"] == "PASS"
    assert audit["clip_ids_used"] is False
    assert {row["event_kind"] for row in audit["rows"]} == {
        "drip",
        "trickle",
        "continuous_liquid_flow",
        "slosh",
        "splash",
        "gurgle",
        "bubble",
    }


@pytest.mark.parametrize("event_kind", ["crinkle", "click", "bang"])
def test_r20_r19_acoustic_paths_remain_reachable(
    local_omni_processor, event_kind: str
) -> None:
    tool = load_tool()
    constraint = _local_ambient_constraint(tool, local_omni_processor)
    canonical = tool.canonical_ambient_tuple_json(
        {
            "event_kind": event_kind,
            "acoustic_properties": {
                "timbre": None,
                "loudness": None,
                "temporal_pattern": None,
            },
        }
    )
    assert constraint.canonical_string_reachable(canonical)


def test_r20_ambient_semantic_error_is_one_call_without_schema_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    calls = []
    invalid = _structured_ambient("pour")

    def fake_generate(*args, **kwargs):
        del args
        calls.append(kwargs)
        return json.dumps(invalid, sort_keys=True), {
            "rendered_prompt": "ambient prompt",
            "rendered_prompt_sha256": tool.semantic_hash("ambient prompt"),
            "rendered_prompt_bytes": 14,
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "generation_seconds": 0.01,
            "network_attempts": 0,
            **_constraint_metadata(tool, "ambient"),
        }

    monkeypatch.setattr(tool, "_generate_one", fake_generate)
    structural = tool._synthetic_structural()
    family = structural["families"][0]
    prompt = tool.build_prompt_manifest(
        {
            "families": [family],
            "targets": structural["targets"][:1],
            "counts": {},
        }
    )["ambient_prompts"][0]
    attempts = []
    with pytest.raises(
        tool.AuthoringError,
        match="MODEL_AMBIENT_EVENT_KIND_ENUM_INVALID",
    ):
        tool.author_factor(
            object(),
            object(),
            object(),
            family_key=family["family_key"],
            factor_key=f"{family['family_key']}:component:1:ambient",
            factor_kind="ambient",
            component_ordinal=1,
            prompt=prompt,
            validator=tool.validate_ambient_factor_output,
            semantic_fields=tool.AMBIENT_SEMANTIC_SCALAR_FIELDS,
            videos=None,
            audios=[object()],
            clip_records=[
                {
                    "clip_key": family["intervals"][0]["clip_key"],
                    "audio_sha256": "sha256:audio",
                }
            ],
            model_identity={"repo_id": "mock"},
            attempts=attempts,
            attempts_path=tmp_path / "ambient-attempts.jsonl",
        )
    assert len(calls) == 1
    assert len(attempts) == 1
    assert attempts[0]["schema_only_repair_eligible"] is False
    assert attempts[0]["constraint_manifest"] == (
        tool.AMBIENT_CONSTRAINT_MANIFEST
    )


def test_r20_historical_r19_manifests_fail_closed() -> None:
    tool = load_tool()
    structural = tool._synthetic_structural()
    prompt = tool.build_prompt_manifest(structural)
    prompt["schema_version"] = (
        "av-trace.p23-102-query-prompt-manifest/10.0"
    )
    with pytest.raises(
        tool.AuthoringError, match="PROMPT_MANIFEST_R20_CONTRACT_INVALID"
    ):
        tool.derive_expected_factor_specs(structural, prompt)

    accepted = {
        "schema_version": (
            "av-trace.p23-102-query-accepted-factor-manifest/10.0"
        ),
        "pipeline_id": tool.PIPELINE_ID,
        "ambient_constraint": tool.ambient_constraint_contract(),
        "accepted_factor_count": 0,
        "visual_factor_count": 0,
        "ambient_factor_count": 0,
        "composition_factor_count": 0,
        "factors": [],
        "cross_factor_fill_or_substitution_permitted": False,
    }
    accepted["manifest_payload_sha256"] = tool.semantic_hash(accepted)
    with pytest.raises(
        tool.AuthoringError,
        match="ACCEPTED_FACTOR_MANIFEST_R20_CONTRACT_INVALID",
    ):
        tool._factor_bindings_by_key(accepted)


@pytest.mark.parametrize(
    ("factor_kind", "mutation"),
    [
        ("ambient", "missing_runtime_field"),
        ("ambient", "extra_runtime_field"),
        ("ambient", "wrong_reachable_count"),
        ("visual", "ambient_tuple_field_present"),
        ("family_composition", "wrong_boundary_kind"),
    ],
)
def test_r21_raw_attempt_constraint_field_sets_fail_closed(
    factor_kind: str, mutation: str
) -> None:
    tool = load_tool()
    attempt = {
        "factor_kind": factor_kind,
        "attempt_kind": "initial",
        **_constraint_metadata(tool, factor_kind),
    }
    if mutation == "missing_runtime_field":
        attempt.pop("constraint_trie_sha256")
    elif mutation == "extra_runtime_field":
        attempt["constraint_runtime_extra"] = "forbidden"
    elif mutation == "wrong_reachable_count":
        attempt["constraint_reachable_count"] = 7679
    elif mutation == "ambient_tuple_field_present":
        attempt["constraint_manifest"] = tool.AMBIENT_CONSTRAINT_MANIFEST
    else:
        attempt["constraint_kind"] = tool.AMBIENT_CONSTRAINT_KIND
    with pytest.raises(tool.AuthoringError):
        tool._validate_attempt_constraint_binding(attempt)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("constraint_leaf_count", 7679),
        ("constraint_reachable_count", 7679),
        ("constraint_stop_token_ids", [151645, 151646]),
        ("constraint_assistant_prefill", ""),
        ("constraint_trie_sha256", "sha256:" + "1" * 64),
        (
            "constraint_tokenizer_fingerprint_sha256",
            "sha256:" + "2" * 64,
        ),
    ],
)
def test_r21_trusted_runtime_constraint_tamper_rejected(
    field: str, tampered
) -> None:
    tool = load_tool()
    attempt = {
        "factor_kind": "ambient",
        "attempt_kind": "initial",
        **_constraint_metadata(tool, "ambient"),
    }
    attempt[field] = tampered
    with pytest.raises(
        tool.AuthoringError,
        match="AMBIENT_ATTEMPT_CONSTRAINT_BINDING_INVALID",
    ):
        tool._validate_attempt_constraint_binding(attempt)


def test_r21_stop_id_reorder_and_extra_rejected() -> None:
    tool = load_tool()
    context = tool.trusted_ambient_constraint_context()
    trusted = context["attempt_constraint"]["constraint_stop_token_ids"]
    assert trusted == [151645]
    for stop_ids in ([151645, 151645], [151646, 151645]):
        attempt = {
            "factor_kind": "ambient",
            "attempt_kind": "initial",
            **_constraint_metadata(tool, "ambient"),
            "constraint_stop_token_ids": stop_ids,
        }
        with pytest.raises(tool.AuthoringError):
            tool._validate_attempt_constraint_binding(attempt)


def test_r21_trusted_constraint_valid_and_canonical_hash_bound() -> None:
    tool = load_tool()
    context = tool.trusted_ambient_constraint_context()
    attempt = {
        "factor_kind": "ambient",
        "attempt_kind": "initial",
        **_constraint_metadata(tool, "ambient"),
    }
    tool._validate_attempt_constraint_binding(attempt)
    assert context["canonical_strings_sha256"] == tool.semantic_hash(
        list(tool._CANONICAL_AMBIENT_TUPLE_STRINGS)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_constraint_hash",
        "extra_constraint_field",
        "wrong_constraint_kind",
        "wrong_constraint_count",
        "wrong_factor_count",
    ],
)
def test_r20_manifest_constraint_and_count_tamper_fail_closed(
    mutation: str,
) -> None:
    tool = load_tool()
    manifest, _, _, _ = _accepted_provenance_fixture(tool)
    tampered = json.loads(json.dumps(manifest))
    if mutation == "missing_constraint_hash":
        tampered["ambient_constraint"].pop(
            "constraint_manifest_sha256"
        )
    elif mutation == "extra_constraint_field":
        tampered["ambient_constraint"]["constraint_extra"] = True
    elif mutation == "wrong_constraint_kind":
        tampered["ambient_constraint"]["constraint_kind"] = "wrong"
    elif mutation == "wrong_constraint_count":
        tampered["ambient_constraint"]["constraint_leaf_count"] = 7679
    else:
        tampered["ambient_factor_count"] += 1
    tampered["manifest_payload_sha256"] = tool.semantic_hash(
        {
            key: value
            for key, value in tampered.items()
            if key != "manifest_payload_sha256"
        }
    )
    with pytest.raises(tool.AuthoringError):
        tool._factor_bindings_by_key(tampered)
