#!/usr/bin/env python3
"""Deterministic, local-only P23_102 query authoring.

This module prepares and (only with a separate authorization receipt) executes
content-grounded query authoring for the repaired P23 provisional bundle.
Authoring is deliberately sealed away from retrieval rankings, non-target
vectors, evaluator outcomes, and human semantic labels.

The normal authoring route uses the pinned local Qwen2.5-Omni-7B thinker on
only the 28 exact target clips.  Frozen local Whisper, SigLIP2, and CLAP
snapshots are used only for literal-ASR leakage and text-collision audits.
No model is loaded by ``--plan`` or ``--synthetic-self-test``.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import math
import os
import re
import resource
import shutil
import socket
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-23"
PIPELINE_ID = "AV-TRACE-P23-102-QUERY-AUTHORING-V2"
READY = "R23_A_IMPLEMENTATION_READY"
SCHEMA_REPAIR_READY = "P23_102_QUERY_AUTHORING_SCHEMA_REPAIR_READY"
MEDIA_CONTRACT_REPAIR_READY = (
    "P23_102_QUERY_AUTHORING_MEDIA_CONTRACT_REPAIR_READY"
)
CONSTRAINED_JSON_READY = "P23_102_QUERY_AUTHORING_CONSTRAINED_JSON_READY"
SEMANTIC_GATES_READY = "P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY"
FACTORIZED_V2_READY = "R23_A_IMPLEMENTATION_READY"
PIPELINE_TOOL = Path("tools/p23_102_query_authoring_v2.py")
PLAN_SCHEMA_VERSION = "av-trace.p23-102-query-authoring-plan/23.0"
PROMPT_MANIFEST_SCHEMA_VERSION = (
    "av-trace.p23-102-query-prompt-manifest/11.0"
)
ACCEPTED_FACTOR_MANIFEST_SCHEMA_VERSION = (
    "av-trace.p23-102-query-accepted-factor-manifest/11.0"
)
AUTHORING_CONTRACT_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-contract/12.0"
)
AUTHORED_QUERIES_SCHEMA_VERSION = (
    "av-trace.p23-102-authored-queries/6.0"
)
RUNTIME_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-runtime/6.0"
)
SEAL_SCHEMA_VERSION = "av-trace.p23-102-query-authoring-seal/9.0"

DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_query_authoring_v2_plan.json"
)
DEFAULT_BUNDLE = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
DEFAULT_MEDIA = Path(
    "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4"
)
DEFAULT_OUTPUT = Path("data/restricted/p23_102_query_authoring_v2")

OMNI_SNAPSHOT = Path(
    "data/restricted/strong_baselines/models/"
    "Qwen--Qwen2.5-Omni-7B--ae9e1690543f"
)
TRUSTED_AMBIENT_TOKENIZER_FILES = (
    "added_tokens.json",
    "chat_template.json",
    "config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
WHISPER_SNAPSHOT = Path(
    "data/restricted/noaa01/models/whisper-tiny.en-87c7102"
)
SIGLIP_SNAPSHOT = Path(
    "data/restricted/scale1b/models/"
    "google--siglip2-base-patch16-224--75de2d55ec2d"
)
CLAP_SNAPSHOT = Path(
    "data/restricted/scale1b/models/"
    "laion--clap-htsat-unfused--8fa0f1c6d043"
)

EXPECTED_FAMILIES = 20
EXPECTED_HANDLES = 56
EXPECTED_TARGET_CLIPS = 28
EXPECTED_NEAR_FAMILIES = 12
EXPECTED_FAR_FAMILIES = 8
EXPECTED_QUERY_COUNT = 76
EXPECTED_VISUAL_FACTORS = EXPECTED_TARGET_CLIPS
EXPECTED_AMBIENT_FACTORS = EXPECTED_TARGET_CLIPS
EXPECTED_COMPOSITION_FACTORS = EXPECTED_FAMILIES
EXPECTED_INITIAL_FACTORS = (
    EXPECTED_VISUAL_FACTORS
    + EXPECTED_AMBIENT_FACTORS
    + EXPECTED_COMPOSITION_FACTORS
)
EXPECTED_MAX_SCHEMA_ONLY_REPAIRS = (
    EXPECTED_VISUAL_FACTORS + EXPECTED_COMPOSITION_FACTORS
)

THREADS = 8
MAX_NEW_TOKENS = 640
MAX_CONTEXT_TOKENS = 32_768
JSON_ASSISTANT_PREFILL = "{"
EMBEDDING_COLLISION_THRESHOLD = 0.995
LEXICAL_COLLISION_THRESHOLD = 0.92
CROSS_KIND_LEXICAL_THRESHOLD = 0.72
CROSS_KIND_EMBEDDING_THRESHOLD = 0.94
CROSS_KIND_SINGLE_ENCODER_THRESHOLD = 0.985
QUERY_DESCRIPTION_IDENTITY_THRESHOLD = 0.90
ASR_LOW_UNIQUE_TOKEN_RATIO = 0.25
ASR_LOW_UNIQUE_TOKEN_MIN_TOKENS = 8
ASR_REPEATED_VOCALIZATION_MIN_COUNT = 4
ASR_REPEATED_VOCALIZATION_DOMINANCE = 0.70
CLAP_ACOUSTICNESS_MIN_POSITIVE_COSINE = 0.20
CLAP_ACOUSTICNESS_MIN_MARGIN = 0.08

ACOUSTIC_CONCEPT_REGISTRY = {
    "alarm": {
        "role": "unambiguous",
        "forms": ("alarm", "alarms"),
    },
    "applause": {
        "role": "unambiguous",
        "forms": ("applause",),
    },
    "bang": {
        "role": "unambiguous",
        "forms": ("bang", "banged", "banging", "bangs"),
    },
    "bark": {
        "role": "unambiguous",
        "forms": ("bark", "barked", "barking", "barks"),
    },
    "beep": {
        "role": "unambiguous",
        "forms": ("beep", "beeped", "beeping", "beeps"),
    },
    "bell": {
        "role": "unambiguous",
        "forms": ("bell", "bells"),
    },
    "bubble": {
        "role": "unambiguous",
        "forms": ("bubble", "bubbled", "bubbles", "bubbling"),
    },
    "buzz": {
        "role": "unambiguous",
        "forms": ("buzz", "buzzed", "buzzes", "buzzing"),
    },
    "chime": {
        "role": "unambiguous",
        "forms": ("chime", "chimed", "chimes", "chiming"),
    },
    "chirp": {
        "role": "unambiguous",
        "forms": ("chirp", "chirped", "chirping", "chirps"),
    },
    "clang": {
        "role": "unambiguous",
        "forms": ("clang", "clanged", "clanging", "clangs"),
    },
    "clank": {
        "role": "unambiguous",
        "forms": ("clank", "clanked", "clanking", "clanks"),
    },
    "clap": {
        "role": "ambiguous",
        "forms": ("clap", "clapped", "clapping", "claps"),
    },
    "clatter": {
        "role": "unambiguous",
        "forms": ("clatter", "clattered", "clattering", "clatters"),
    },
    "click": {
        "role": "ambiguous",
        "forms": ("click", "clicked", "clicking", "clicks"),
    },
    "clink": {
        "role": "unambiguous",
        "forms": ("clink", "clinked", "clinking", "clinks"),
    },
    "cough": {
        "role": "unambiguous",
        "forms": ("cough", "coughed", "coughing", "coughs"),
    },
    "break": {
        "role": "ambiguous",
        "forms": ("break", "breaking", "breaks", "broke", "broken"),
    },
    "chop": {
        "role": "ambiguous",
        "forms": ("chop", "chopped", "chopping", "chops"),
    },
    "close": {
        "role": "ambiguous",
        "forms": ("close", "closed", "closes", "closing"),
    },
    "continuous_liquid_flow": {
        "role": "unambiguous",
        "forms": ("flow", "flowing"),
        "definition": (
            "continuous or pulsed liquid-flow sound without asserting an "
            "action, source, container, location, or direction"
        ),
        "confusions": (
            "drip",
            "trickle",
            "slosh",
            "splash",
            "gurgle",
            "bubble",
        ),
    },
    "crackle": {
        "role": "unambiguous",
        "forms": ("crackle", "crackled", "crackles", "crackling"),
    },
    "creak": {
        "role": "unambiguous",
        "forms": ("creak", "creaked", "creaking", "creaks"),
    },
    "crinkle": {
        "role": "ambiguous",
        "forms": ("crinkle", "crinkled", "crinkles", "crinkling"),
    },
    "crumple": {
        "role": "ambiguous",
        "forms": ("crumple", "crumpled", "crumples", "crumpling"),
    },
    "crunch": {
        "role": "unambiguous",
        "forms": ("crunch", "crunched", "crunches", "crunching"),
    },
    "cut": {
        "role": "ambiguous",
        "forms": ("cut", "cuts", "cutting"),
    },
    "ding": {
        "role": "unambiguous",
        "forms": ("ding", "dinged", "dinging", "dings"),
    },
    "drip": {
        "role": "unambiguous",
        "forms": ("drip", "dripped", "dripping", "drips"),
    },
    "drop": {
        "role": "ambiguous",
        "forms": ("drop", "dropped", "dropping", "drops"),
    },
    "echo": {
        "role": "ambiguous",
        "forms": ("echo", "echoed", "echoes", "echoing"),
    },
    "footstep": {
        "role": "unambiguous",
        "forms": ("footstep", "footsteps"),
    },
    "gasp": {
        "role": "unambiguous",
        "forms": ("gasp", "gasped", "gasping", "gasps"),
    },
    "grind": {
        "role": "unambiguous",
        "forms": ("grind", "grinding", "grinds", "ground"),
    },
    "gurgle": {
        "role": "unambiguous",
        "forms": ("gurgle", "gurgled", "gurgles", "gurgling"),
    },
    "hiss": {
        "role": "unambiguous",
        "forms": ("hiss", "hissed", "hisses", "hissing"),
    },
    "horn": {
        "role": "unambiguous",
        "forms": ("horn", "horns"),
    },
    "hum": {
        "role": "unambiguous",
        "forms": ("hum", "hummed", "humming", "hums"),
    },
    "impact": {
        "role": "ambiguous",
        "forms": ("impact", "impacted", "impacting", "impacts"),
    },
    "jingle": {
        "role": "unambiguous",
        "forms": ("jingle", "jingled", "jingles", "jingling"),
    },
    "knock": {
        "role": "ambiguous",
        "forms": ("knock", "knocked", "knocking", "knocks"),
    },
    "meow": {
        "role": "unambiguous",
        "forms": ("meow", "meowed", "meowing", "meows"),
    },
    "ping": {
        "role": "unambiguous",
        "forms": ("ping", "pinged", "pinging", "pings"),
    },
    "open": {
        "role": "ambiguous",
        "forms": ("open", "opened", "opening", "opens"),
    },
    "pop": {
        "role": "unambiguous",
        "forms": ("pop", "popped", "popping", "pops"),
    },
    "pour": {
        "role": "ambiguous",
        "forms": ("pour", "poured", "pouring", "pours"),
    },
    "rattle": {
        "role": "ambiguous",
        "forms": ("rattle", "rattled", "rattles", "rattling"),
    },
    "ring": {
        "role": "ambiguous",
        "forms": ("rang", "ring", "ringing", "rings"),
    },
    "rip": {
        "role": "ambiguous",
        "forms": ("rip", "ripped", "ripping", "rips"),
    },
    "rumble": {
        "role": "unambiguous",
        "forms": ("rumble", "rumbled", "rumbles", "rumbling"),
    },
    "rustle": {
        "role": "unambiguous",
        "forms": ("rustle", "rustled", "rustles", "rustling"),
    },
    "scrape": {
        "role": "ambiguous",
        "forms": ("scrape", "scraped", "scrapes", "scraping"),
    },
    "scratch": {
        "role": "ambiguous",
        "forms": ("scratch", "scratched", "scratches", "scratching"),
    },
    "screech": {
        "role": "unambiguous",
        "forms": ("screech", "screeched", "screeches", "screeching"),
    },
    "sigh": {
        "role": "unambiguous",
        "forms": ("sigh", "sighed", "sighing", "sighs"),
    },
    "shatter": {
        "role": "ambiguous",
        "forms": ("shatter", "shattered", "shattering", "shatters"),
    },
    "siren": {
        "role": "unambiguous",
        "forms": ("siren", "sirens"),
    },
    "sizzle": {
        "role": "unambiguous",
        "forms": ("sizzle", "sizzled", "sizzles", "sizzling"),
    },
    "slosh": {
        "role": "unambiguous",
        "forms": ("slosh", "sloshed", "sloshes", "sloshing"),
    },
    "slam": {
        "role": "ambiguous",
        "forms": ("slam", "slammed", "slamming", "slams"),
    },
    "slide": {
        "role": "ambiguous",
        "forms": ("slide", "slid", "slides", "sliding"),
    },
    "snap": {
        "role": "ambiguous",
        "forms": ("snap", "snapped", "snapping", "snaps"),
    },
    "sneeze": {
        "role": "unambiguous",
        "forms": ("sneeze", "sneezed", "sneezes", "sneezing"),
    },
    "splash": {
        "role": "ambiguous",
        "forms": ("splash", "splashed", "splashes", "splashing"),
    },
    "squeak": {
        "role": "unambiguous",
        "forms": ("squeak", "squeaked", "squeaking", "squeaks"),
    },
    "squeal": {
        "role": "unambiguous",
        "forms": ("squeal", "squealed", "squealing", "squeals"),
    },
    "stomp": {
        "role": "ambiguous",
        "forms": ("stomp", "stomped", "stomping", "stomps"),
    },
    "stir": {
        "role": "ambiguous",
        "forms": ("stir", "stirred", "stirring", "stirs"),
    },
    "swish": {
        "role": "unambiguous",
        "forms": ("swish", "swished", "swishes", "swishing"),
    },
    "tap": {
        "role": "ambiguous",
        "forms": ("tap", "tapped", "tapping", "taps"),
    },
    "tear": {
        "role": "ambiguous",
        "forms": ("tear", "tearing", "tears", "tore", "torn"),
    },
    "thud": {
        "role": "unambiguous",
        "forms": ("thud", "thudded", "thudding", "thuds"),
    },
    "tick": {
        "role": "unambiguous",
        "forms": ("tick", "ticked", "ticking", "ticks"),
    },
    "tone": {
        "role": "unambiguous",
        "forms": ("tone", "tones"),
    },
    "trickle": {
        "role": "unambiguous",
        "forms": ("trickle", "trickled", "trickles", "trickling"),
    },
    "whir": {
        "role": "unambiguous",
        "forms": ("whir", "whirred", "whirring", "whirs"),
    },
    "whistle": {
        "role": "unambiguous",
        "forms": ("whistle", "whistled", "whistles", "whistling"),
    },
    "whoosh": {
        "role": "unambiguous",
        "forms": ("whoosh", "whooshed", "whooshes", "whooshing"),
    },
}
CONTEXT_BOUND_ACTION_CONCEPTS = frozenset(
    {
        "break",
        "chop",
        "clap",
        "close",
        "cut",
        "drop",
        "open",
        "pour",
        "rip",
        "shatter",
        "slam",
        "slide",
        "stir",
        "stomp",
        "tear",
    }
)
_ACOUSTIC_REGISTRY_ROLES = frozenset({"ambiguous", "unambiguous"})
if any(
    row["role"] not in _ACOUSTIC_REGISTRY_ROLES
    or not row["forms"]
    or any(not isinstance(form, str) or not form for form in row["forms"])
    for row in ACOUSTIC_CONCEPT_REGISTRY.values()
):
    raise RuntimeError("ACOUSTIC_CONCEPT_REGISTRY_INVALID")
_ACOUSTIC_FORM_ROWS = [
    (concept, str(row["role"]), form)
    for concept, row in sorted(ACOUSTIC_CONCEPT_REGISTRY.items())
    for form in row["forms"]
]
if len({form for _, _, form in _ACOUSTIC_FORM_ROWS}) != len(
    _ACOUSTIC_FORM_ROWS
):
    raise RuntimeError("ACOUSTIC_CONCEPT_REGISTRY_FORM_COLLISION")
UNAMBIGUOUS_ACOUSTIC_FORMS = {
    concept: frozenset(row["forms"])
    for concept, row in ACOUSTIC_CONCEPT_REGISTRY.items()
    if row["role"] == "unambiguous"
}
AMBIGUOUS_ACOUSTIC_FORMS = {
    concept: frozenset(row["forms"])
    for concept, row in ACOUSTIC_CONCEPT_REGISTRY.items()
    if row["role"] == "ambiguous"
}
CONTEXT_BOUND_ACTION_FORMS = frozenset(
    form
    for concept in CONTEXT_BOUND_ACTION_CONCEPTS
    for form in AMBIGUOUS_ACOUSTIC_FORMS[concept]
)
UNAMBIGUOUS_ACOUSTIC_CONCEPTS = frozenset(
    UNAMBIGUOUS_ACOUSTIC_FORMS
)
UNAMBIGUOUS_ACOUSTIC_FORM_TO_CONCEPT = {
    form: concept
    for concept, forms in UNAMBIGUOUS_ACOUSTIC_FORMS.items()
    for form in forms
}
AMBIGUOUS_ACOUSTIC_FORM_TO_CONCEPT = {
    form: concept
    for concept, forms in AMBIGUOUS_ACOUSTIC_FORMS.items()
    for form in forms
}
ACOUSTIC_FORM_TO_CONCEPT = {
    **UNAMBIGUOUS_ACOUSTIC_FORM_TO_CONCEPT,
    **AMBIGUOUS_ACOUSTIC_FORM_TO_CONCEPT,
}
ACOUSTIC_CONCEPT_REGISTRY_MANIFEST = {
    concept: {
        "role": row["role"],
        "forms": sorted(row["forms"]),
        **(
            {"definition": row["definition"]}
            if "definition" in row
            else {}
        ),
        **(
            {"confusions": sorted(row["confusions"])}
            if "confusions" in row
            else {}
        ),
    }
    for concept, row in sorted(ACOUSTIC_CONCEPT_REGISTRY.items())
}
ACOUSTIC_CONCEPT_REGISTRY_MANIFEST_SHA256 = "sha256:" + hashlib.sha256(
    json.dumps(
        ACOUSTIC_CONCEPT_REGISTRY_MANIFEST,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
).hexdigest()
ACOUSTIC_EVENT_OR_PROPERTY_LEXICON = frozenset(
    {
        *ACOUSTIC_FORM_TO_CONCEPT,
        "acoustic",
        "audible",
        "loud",
        "metallic",
        "muffled",
        "noise",
        "quiet",
        "rhythmic",
        "sharp",
        "sound",
        "throat-clearing",
    }
)
GENERIC_ACOUSTIC_TERMS = frozenset(
    {
        "acoustic",
        "audible",
        "noise",
        "quiet",
        "sound",
    }
)
GENERIC_ACOUSTIC_CONTEXT_TERMS = frozenset(
    {
        "a",
        "an",
        "area",
        "background",
        "brief",
        "environment",
        "is",
        "nearby",
        "room",
        "soft",
        "the",
        "there",
        "very",
    }
)
SPECIFIC_ACOUSTIC_EVENT_TERMS = frozenset(ACOUSTIC_FORM_TO_CONCEPT)
AUDITORY_NOUN_MARKERS = frozenset(
    {"noise", "noises", "sound", "sounds"}
)
AUDITORY_ADJECTIVE_MARKERS = frozenset(
    {"acoustic", "audible", "audibly", "sonic"}
)
AUDITORY_PERCEPTION_MARKERS = frozenset(
    {"hear", "heard", "hearing"}
)
AUDITORY_RESPONSE_MARKERS = frozenset(
    {
        "echo",
        "echoed",
        "echoes",
        "echoing",
        "resound",
        "resounded",
        "resounding",
        "resounds",
        "reverberate",
        "reverberated",
        "reverberates",
        "reverberating",
    }
)
ACOUSTIC_EVENT_MODIFIERS = frozenset(
    {
        "brief",
        "ceramic",
        "chopping",
        "crisp",
        "distinct",
        "faint",
        "heavy",
        "light",
        "loud",
        "low",
        "mechanical",
        "metal",
        "metallic",
        "muffled",
        "repeated",
        "rhythmic",
        "sharp",
        "short",
        "soft",
        "steady",
        "sudden",
    }
)
HUMAN_VOCALIZATION_TERMS = frozenset(
    {
        "cough",
        "gasp",
        "groan",
        "hum",
        "laugh",
        "moan",
        "murmur",
        "say",
        "shout",
        "sigh",
        "sing",
        "sneeze",
        "speak",
        "speaks",
        "speaking",
        "speech",
        "talk",
        "talked",
        "talking",
        "talks",
        "throat",
        "utter",
        "voice",
        "whisper",
        "yell",
    }
)
NONLEXICAL_HUMAN_VOCALIZATION_TERMS = frozenset(
    {
        "cough",
        "gasp",
        "groan",
        "laugh",
        "moan",
        "sigh",
        "sneeze",
        "throat",
    }
)
LEXICAL_SPEECH_TERMS = frozenset(
    {
        "answer",
        "answered",
        "answering",
        "answers",
        "ask",
        "asked",
        "asking",
        "asks",
        "chant",
        "chanted",
        "chanting",
        "chants",
        "chat",
        "chatted",
        "chatting",
        "chats",
        "conversation",
        "conversations",
        "converse",
        "conversed",
        "converses",
        "conversing",
        "dialog",
        "dialogs",
        "dialogue",
        "dialogues",
        "discuss",
        "discussed",
        "discusses",
        "discussing",
        "discussion",
        "discussions",
        "narrate",
        "narrated",
        "narrates",
        "narrating",
        "narration",
        "narrations",
        "narrator",
        "narrators",
        "question",
        "questioned",
        "questioning",
        "questions",
        "read",
        "reads",
        "reading",
        "recited",
        "recite",
        "recites",
        "reciting",
        "murmur",
        "murmured",
        "murmuring",
        "murmurs",
        "say",
        "says",
        "said",
        "sentence",
        "sentences",
        "shout",
        "shouted",
        "shouting",
        "shouts",
        "sing",
        "sang",
        "sings",
        "singing",
        "sung",
        "speak",
        "spoke",
        "spoken",
        "speaks",
        "speaking",
        "speech",
        "speeches",
        "talk",
        "talked",
        "talking",
        "talks",
        "utter",
        "uttered",
        "uttering",
        "utters",
        "voice",
        "voices",
        "voiced",
        "voicing",
        "whisper",
        "whispered",
        "whispering",
        "whispers",
        "word",
        "words",
        "yell",
        "yelled",
        "yelling",
        "yells",
    }
)
SHORT_VOCALIZATION_TOKENS = frozenset(
    {
        "ah",
        "eh",
        "ha",
        "hm",
        "hmm",
        "mm",
        "oh",
        "ooh",
        "uh",
        "ugh",
        "um",
        "yeah",
        "yep",
    }
)
UNRESOLVED_REFERENCE_TERMS = frozenset(
    {
        "former",
        "it",
        "its",
        "latter",
        "previously",
        "prior",
        "that",
        "them",
        "then",
        "thereafter",
        "these",
        "they",
        "this",
        "those",
    }
)
UNSUPPORTED_CONTINUITY_PATTERNS = (
    re.compile(
        r"\bthe same (?:person|object|item|container|tool)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:same|single) person\b", re.IGNORECASE),
    re.compile(r"\b(?:continues?|still|again)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:because|causes?|caused|therefore|so that)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:leads?|leading|led)\s+to\b", re.IGNORECASE),
    re.compile(
        r"\b(?:results?|resulting|resulted)\s+in\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:produces?|producing|produced)\b", re.IGNORECASE),
    re.compile(r"\b(?:triggers?|triggering|triggered)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:makes?|making|made)\b[^.!?;\n]{0,80}\b"
        r"happen(?:s|ed|ing)?\b",
        re.IGNORECASE,
    ),
)
COMPONENT_CROSS_REFERENCE_PATTERNS = (
    re.compile(r"\b(?:components|segments|stages|hops)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:another|other|first|second|both|previous|next|prior|"
        r"following|preceding|former|latter|same|each|either|two|multiple)"
        r"\s+(?:component|segment|stage|hop)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:component|segment|stage|hop)\s*(?:one|two|1|2)\b",
        re.IGNORECASE,
    ),
)
MECHANICAL_FAMILY_TEXT_TERMS = frozenset(
    {
        "1",
        "2",
        "a",
        "accepted",
        "accompanying",
        "as",
        "before",
        "component",
        "co",
        "cooccurrence",
        "cooccur",
        "evidence",
        "find",
        "frozen",
        "in",
        "keep",
        "local",
        "locally",
        "matching",
        "one",
        "observations",
        "occur",
        "occurrence",
        "order",
        "sound",
        "the",
        "then",
        "together",
        "to",
        "with",
        "within",
    }
)
CONTINUITY_REFERENCE_TERMS = frozenset(
    {
        "continues",
        "continuing",
        "former",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "it",
        "its",
        "latter",
        "remains",
        "same",
        "she",
        "still",
        "their",
        "theirs",
        "them",
        "they",
        "this",
        "those",
    }
)
LOCAL_POSSESSIVE_REFERENCE_TERMS = frozenset({"her", "his", "their"})
LOCAL_POSSESSIVE_DETERMINER_RE = re.compile(
    r"\b(?:her|his|their)\s+[a-z0-9]+(?:'[a-z0-9]+)?\b",
    re.IGNORECASE,
)
LOCAL_CLAUSE_SPLIT_RE = re.compile(r"[.!?;\n]+")
LOCAL_POSSESSIVE_EXEMPTION_BRIDGE_RE = re.compile(
    r"\b(?:same|again|continues?|continuing|still|previous(?:ly)?|"
    r"next|prior|following|preceding|former|latter)\b|\bas before\b",
    re.IGNORECASE,
)
LOCAL_NOUN_ANTECEDENT_RE = re.compile(
    r"\b(?:a|an|the)\s+"
    r"(?P<phrase>[a-z0-9]+(?:'[a-z0-9]+)?"
    r"(?:\s+[a-z0-9]+(?:'[a-z0-9]+)?){0,4})"
    r"(?=\s+(?:and|at|beside|in|inside|near|on|or|outside|over|under|with)"
    r"\b|[.!?;,\n]|$)",
    re.IGNORECASE,
)
LOCAL_LOCATIVE_PRONOUN_RE = re.compile(
    r"\b(?P<preposition>at|beside|in|inside|near|on|outside|over|under)\s+"
    r"(?P<term>it)\b",
    re.IGNORECASE,
)
AGENT_TERMS = frozenset(
    {
        "actor",
        "cook",
        "individual",
        "man",
        "operator",
        "person",
        "someone",
        "woman",
        "worker",
    }
)
LOCAL_AGENT_ANTECEDENT_RE = re.compile(
    r"\b(?:a|an|the)\s+(?:"
    + "|".join(sorted(AGENT_TERMS))
    + r")\b",
    re.IGNORECASE,
)
DEFINITE_HUMAN_START_RE = re.compile(
    r"^(?:the|this|that) (?:person|man|woman|cook|worker|individual)\b",
    re.IGNORECASE,
)
ACOUSTICNESS_POSITIVE_PROMPTS = (
    "a sharp metallic clank and brief ringing",
    "a soft rustling and crinkling sound",
    "a rhythmic series of taps and impacts",
    "a low mechanical hum with a faint hiss",
)
ACOUSTICNESS_NEGATIVE_PROMPTS = (
    "a person moves an object across a table",
    "hands place food into a container",
    "an item changes position in a kitchen",
    "a person performs an action with a tool",
)
SEMANTIC_GATE_NAMES = (
    "ambient_acoustic_grounding",
    "asr_vocalization_quarantine",
    "cross_kind_distinctness",
    "far_composition",
    "standalone_reference",
    "query_description_identity",
)

OUTPUT_FILES = (
    "authoring_contract.json",
    "target_manifest.json",
    "prompt_manifest.json",
    "raw_attempts.jsonl",
    "accepted_factor_manifest.json",
    "ambient_semantic_tuple_collisions.json",
    "asr_audit_inventory.json",
    "authored_queries.json",
    "audits.json",
    "resource_runtime.json",
)


def _audit_input_digest(
    structural: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
    asr_inventory: Mapping[str, Any],
) -> str:
    return semantic_hash(
        {
            "structural": structural,
            "queries": queries,
            "descriptions": descriptions,
            "asr_inventory": asr_inventory,
        }
    )


def _transcripts_from_asr_inventory(
    inventory: Mapping[str, Any],
) -> dict[str, str]:
    rows = inventory.get("rows")
    if not isinstance(rows, list):
        raise AuthoringError("SEALED_ASR_INVENTORY_INVALID")
    transcripts = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("clip_key"), str)
            or not isinstance(row.get("normalized_transcript"), str)
        ):
            raise AuthoringError("SEALED_ASR_ROW_INVALID")
        transcript = str(row["normalized_transcript"])
        if row.get("normalized_transcript_sha256") != semantic_hash(transcript):
            raise AuthoringError("SEALED_ASR_TRANSCRIPT_HASH_MISMATCH")
        transcripts[str(row["clip_key"])] = transcript
    return transcripts


def _queries_for_audit_replay(
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Restore the exact pre-audit machine-status state for deterministic replay."""

    query_rows = json.loads(json.dumps(list(queries)))
    description_rows = json.loads(json.dumps(list(descriptions)))
    for row in [*query_rows, *description_rows]:
        row["machine_observation_status"] = (
            "PENDING_MACHINE_SEMANTIC_GATES"
        )
        row["field_gate_status"] = {
            name: "PENDING" for name in SEMANTIC_GATE_NAMES
        }
        row["human_grounded"] = False
    return query_rows, description_rows


def _model_free_audit_projection(
    audits: Mapping[str, Any],
) -> dict[str, Any]:
    """Select gates that can be reproduced without SigLIP2 or CLAP."""

    semantic = audits.get("semantic_authoring_gates", {})
    if not isinstance(semantic, Mapping):
        raise AuthoringError("SEALED_SEMANTIC_AUDITS_INVALID")
    model_free_gates = (
        "ambient_acoustic_grounding",
        "asr_vocalization_quarantine",
        "far_composition",
        "standalone_reference",
        "query_description_identity",
    )
    return {
        "literal_leakage": audits.get("literal_leakage"),
        "duplicates_and_lexical_collisions": audits.get(
            "duplicates_and_lexical_collisions"
        ),
        "semantic_authoring_gates": {
            name: semantic.get(name) for name in model_free_gates
        },
        "family_query_uniqueness": audits.get("family_query_uniqueness"),
        "template_only_primary_queries": audits.get(
            "template_only_primary_queries"
        ),
    }

ALLOWED_BUNDLE_FILES = frozenset(
    {
        "family_registry.json",
        "evidence_registry.json",
        "source_split_manifest.json",
        "leakage_gate.json",
    }
)
FORBIDDEN_MODEL_VISIBLE_KEYS = frozenset(
    {
        "accepted_family",
        "accepted_ses",
        "answer_key",
        "answer_support_and_necessity_boundary",
        "evaluation",
        "gate_a_credit",
        "h_tier",
        "human_prescreen",
        "human_validated",
        "index_bindings",
        "modality_work_hypotheses",
        "necessity_validated",
        "rank",
        "record_id",
        "recurrence_checks",
        "retrieval_role",
        "route_group_id",
        "score",
        "semantic_content_asserted",
        "source_candidate_id",
        "structural_scores",
        "substitution_risks",
        "support_validated",
        "vector",
    }
)
FINAL_MODALITY_LABELS = frozenset(
    {
        "ambient",
        "audio",
        "clip",
        "footage",
        "frame",
        "image",
        "modality",
        "recording",
        "soundtrack",
        "video",
        "vision",
        "visual",
        "visually",
    }
)
SOURCE_LITERALS = (
    "P23",
    "P23_102",
    "P23_102.MP4",
    "EPIC",
    "EPIC-KITCHENS",
    "EPIC-KITCHENS-100",
)
PRIVATE_ID_RE = re.compile(
    r"\b(?:mpf|mpr|mpc|eh)\.[A-Za-z0-9._-]+\b"
    r"|\bP23_102\.[A-Za-z0-9._-]+\b"
    r"|\bEPIC-P23-102-[A-Za-z0-9._-]+\b",
    re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|s|sec|seconds?)\b",
    re.IGNORECASE,
)
MODEL_VISIBLE_IDENTIFIER_RE = re.compile(
    r"\b(?:clip|family|query|description|record|route|source)[-_]"
    r"[A-Za-z0-9._-]+\b",
    re.IGNORECASE,
)
RETRIEVAL_INFO_RE = re.compile(
    r"\b(?:retrieval|ranking|ranked|score|scoring|vector|embedding)\b",
    re.IGNORECASE,
)
SLOT_RE = re.compile(r"\[([A-Z][A-Z0-9_]*)\]")
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


class AuthoringError(RuntimeError):
    """Fail-closed query-authoring error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


STRUCTURED_AMBIENT_EVENT_KINDS = tuple(
    sorted(
        {
            concept
            for concept in ACOUSTIC_CONCEPT_REGISTRY
            if concept not in CONTEXT_BOUND_ACTION_CONCEPTS
        }
        | {"throat_clear"}
    )
)
STRUCTURED_AMBIENT_TIMBRES = (
    None,
    "metallic",
    "muffled",
    "crisp",
    "hollow",
    "sharp",
)
STRUCTURED_AMBIENT_LOUDNESS = (None, "faint", "soft", "loud")
STRUCTURED_AMBIENT_TEMPORAL_PATTERNS = (
    None,
    "brief",
    "repeated",
    "rhythmic",
    "steady",
)
STRUCTURED_AMBIENT_EVENT_TEXT = {
    event_kind: (
        "throat clearing"
        if event_kind == "throat_clear"
        else "continuous liquid flow"
        if event_kind == "continuous_liquid_flow"
        else event_kind.replace("_", " ")
    )
    for event_kind in STRUCTURED_AMBIENT_EVENT_KINDS
}
STRUCTURED_AMBIENT_EVENT_DEFINITIONS = {
    "continuous_liquid_flow": (
        "continuous or pulsed liquid-flow sound; do not assert pouring, a "
        "container, source, location, or direction"
    ),
}
STRUCTURED_AMBIENT_EVENT_CONFUSIONS = {
    "continuous_liquid_flow": [
        "drip",
        "trickle",
        "slosh",
        "splash",
        "gurgle",
        "bubble",
    ],
}
LIQUID_EVENT_BOUNDARIES = {
    "drip": "one or more discrete separated liquid drops",
    "trickle": "a weak narrow low-volume liquid stream",
    "continuous_liquid_flow": (
        "continuous or pulsed liquid-flow sound without action, container, "
        "source, location, or direction claims"
    ),
    "slosh": "liquid mass moving back and forth within a bounded space",
    "splash": "liquid impact or scattering at a surface",
    "gurgle": "resonant irregular liquid-and-air movement through a passage",
    "bubble": "discrete or clustered bubble formation or bursting",
}
STRUCTURED_AMBIENT_REGISTRY_MANIFEST = {
    "schema_version": "av-trace.structured-ambient-registry/3.0",
    "event_kind": list(STRUCTURED_AMBIENT_EVENT_KINDS),
    "event_definitions": dict(STRUCTURED_AMBIENT_EVENT_DEFINITIONS),
    "event_confusions": dict(STRUCTURED_AMBIENT_EVENT_CONFUSIONS),
    "acoustic_properties": {
        "timbre": list(STRUCTURED_AMBIENT_TIMBRES),
        "loudness": list(STRUCTURED_AMBIENT_LOUDNESS),
        "temporal_pattern": list(
            STRUCTURED_AMBIENT_TEMPORAL_PATTERNS
        ),
    },
    "excluded_action_event_kinds": sorted(
        CONTEXT_BOUND_ACTION_CONCEPTS
        | {"place"}
    ),
    "source_material_object_agent_location_direction_dimensions": "forbidden",
    "lexical_speech_event_kind_permitted": False,
}
STRUCTURED_AMBIENT_REGISTRY_SHA256 = semantic_hash(
    STRUCTURED_AMBIENT_REGISTRY_MANIFEST
)
AMBIENT_TEMPLATE_SPEC = {
    "schema_version": "av-trace.structured-ambient-template-spec/3.0",
    "description": {
        "prefix": "A ",
        "property_order": [
            "loudness",
            "temporal_pattern",
            "timbre",
        ],
        "property_separator": " ",
        "property_event_separator": " ",
        "suffix": " is audible.",
    },
    "query": {
        "prefix": "Find the audible ",
        "event_no_properties_suffix": " event.",
        "event_with_properties_separator": " event matching ",
        "property_order": [
            "timbre",
            "temporal_pattern",
            "loudness",
        ],
        "property_separator": ", ",
        "suffix": ".",
    },
    "property_rendering": {
        "timbre": "identity",
        "loudness": "identity",
        "temporal_pattern": "identity",
    },
    "event_rendering": "registry_event_text_exact",
    "null_rendering": "omitted",
    "grammar_matching": "full_string_exact",
}
EXPECTED_STRUCTURED_AMBIENT_EVENT_KIND_COUNT = 64
EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS = 7680
EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS = 7680
AMBIENT_CONSTRAINT_KIND = "canonical_ambient_tuple_token_prefix_trie"
AMBIENT_CONSTRAINT_SCHEMA_VERSION = (
    "av-trace.ambient-token-prefix-constraint/1.0"
)


def build_ambient_template_manifest(
    spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the committed template manifest from the sole template spec."""

    return {
        "schema_version": "av-trace.structured-ambient-template/3.0",
        "template_spec": json.loads(canonical_bytes(spec)),
    }


def build_ambient_generator_manifest(
    *,
    template_sha256: str,
) -> dict[str, Any]:
    """Bind the mechanical algorithm contract to the exact template spec."""

    return {
        "schema_version": "av-trace.structured-ambient-generator/3.0",
        "registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "template_sha256": template_sha256,
        "algorithm": (
            "validate closed tuple; render description/query directly from "
            "the declarative template spec; independently strict-parse each "
            "full derived string; require canonical tuple exact equality"
        ),
        "parser": "controlled_frozen_template_grammar_not_nlp",
        "unknown_combination_policy": "fail_closed",
        "mechanical_text_model_calls": 0,
    }


def ambient_derivation_hashes(
    spec: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return template/generator manifests and hashes for one exact spec."""

    selected = AMBIENT_TEMPLATE_SPEC if spec is None else spec
    template_manifest = build_ambient_template_manifest(selected)
    template_sha256 = semantic_hash(template_manifest)
    generator_manifest = build_ambient_generator_manifest(
        template_sha256=template_sha256
    )
    return {
        "template_manifest": template_manifest,
        "template_sha256": template_sha256,
        "generator_manifest": generator_manifest,
        "generator_sha256": semantic_hash(generator_manifest),
    }


_AMBIENT_DERIVATION_HASHES = ambient_derivation_hashes(
    AMBIENT_TEMPLATE_SPEC
)
AMBIENT_TEMPLATE_MANIFEST = _AMBIENT_DERIVATION_HASHES[
    "template_manifest"
]
AMBIENT_TEMPLATE_SHA256 = _AMBIENT_DERIVATION_HASHES["template_sha256"]
AMBIENT_GENERATOR_MANIFEST = _AMBIENT_DERIVATION_HASHES[
    "generator_manifest"
]
AMBIENT_GENERATOR_SHA256 = _AMBIENT_DERIVATION_HASHES[
    "generator_sha256"
]
AMBIENT_SEMANTIC_SCALAR_FIELDS = frozenset(
    {
        "event_kind",
        "timbre",
        "loudness",
        "temporal_pattern",
    }
)


def iter_structured_ambient_semantic_tuples() -> Iterator[dict[str, Any]]:
    """Yield the complete closed ambient tuple space in canonical order."""

    for event_kind in STRUCTURED_AMBIENT_EVENT_KINDS:
        for timbre in STRUCTURED_AMBIENT_TIMBRES:
            for loudness in STRUCTURED_AMBIENT_LOUDNESS:
                for temporal_pattern in (
                    STRUCTURED_AMBIENT_TEMPORAL_PATTERNS
                ):
                    yield {
                        "event_kind": event_kind,
                        "acoustic_properties": {
                            "timbre": timbre,
                            "loudness": loudness,
                            "temporal_pattern": temporal_pattern,
                        },
                    }


def canonical_ambient_tuple_json(value: Mapping[str, Any]) -> str:
    """Return the sole byte-canonical JSON representation of one tuple."""

    semantic = validate_ambient_semantic_tuple(value)
    return canonical_bytes(semantic).decode("utf-8")


def canonical_ambient_tuple_strings() -> tuple[str, ...]:
    """Return every legal canonical ambient JSON string exactly once."""

    strings = tuple(
        canonical_bytes(value).decode("utf-8")
        for value in iter_structured_ambient_semantic_tuples()
    )
    if len(strings) != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS:
        raise RuntimeError("AMBIENT_CANONICAL_STRING_COUNT_MISMATCH")
    if len(set(strings)) != len(strings):
        raise RuntimeError("AMBIENT_CANONICAL_STRING_COLLISION")
    return strings


_CANONICAL_AMBIENT_TUPLE_STRINGS = canonical_ambient_tuple_strings()
AMBIENT_CONSTRAINT_MANIFEST = {
    "schema_version": AMBIENT_CONSTRAINT_SCHEMA_VERSION,
    "constraint_kind": AMBIENT_CONSTRAINT_KIND,
    "canonical_json": {
        "sort_keys": True,
        "separators": [",", ":"],
        "ensure_ascii": False,
        "allow_nan": False,
        "top_level_key_order": [
            "acoustic_properties",
            "event_kind",
        ],
        "acoustic_property_key_order": [
            "loudness",
            "temporal_pattern",
            "timbre",
        ],
    },
    "assistant_prefill": JSON_ASSISTANT_PREFILL,
    "registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
    "canonical_strings_sha256": semantic_hash(
        list(_CANONICAL_AMBIENT_TUPLE_STRINGS)
    ),
    "leaf_count": EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS,
    "reachable_count": EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS,
    "leaf_policy": "only_eos_or_model_stop_tokens_allowed",
    "semantic_substitution_permitted": False,
    "schema_repair_permitted": False,
}
AMBIENT_CONSTRAINT_MANIFEST_SHA256 = semantic_hash(
    AMBIENT_CONSTRAINT_MANIFEST
)


def ambient_constraint_contract() -> dict[str, Any]:
    """Return the exact static decoder-constraint contract.

    The tokenizer-specific trie hash is recorded by each raw attempt.  This
    static contract is the tokenizer-independent commitment propagated through
    prompts, accepted factors, manifests, contracts, runtimes, and seals.
    """

    return {
        "constraint_kind": AMBIENT_CONSTRAINT_KIND,
        "constraint_manifest": json.loads(
            canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
        ),
        "constraint_manifest_sha256": (
            AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "constraint_leaf_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "constraint_reachable_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
    }


def ambient_derivation_contract() -> dict[str, Any]:
    """Return the exact ambient derivation/constraint binding fields."""

    return {
        "ambient_registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "ambient_generator_sha256": AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": AMBIENT_TEMPLATE_SHA256,
        "ambient_constraint_kind": AMBIENT_CONSTRAINT_KIND,
        "ambient_constraint_manifest": json.loads(
            canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
        ),
        "ambient_constraint_manifest_sha256": (
            AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "ambient_constraint_leaf_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_constraint_reachable_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
    }


def _validate_ambient_derivation_contract(
    value: Mapping[str, Any],
    *,
    error: str,
) -> None:
    """Fail closed on missing, extra, or altered ambient contract fields."""

    expected = ambient_derivation_contract()
    observed_keys = {
        key
        for key in value
        if key in expected or key.startswith("ambient_constraint_")
    }
    expected_keys = set(expected)
    if observed_keys != expected_keys or any(
        value.get(key) != item for key, item in expected.items()
    ):
        raise AuthoringError(error)


def _validate_static_ambient_contract() -> None:
    """Fail closed if registry, schema, tuple space, or constraint drift."""

    event_kinds = tuple(AMBIENT_OUTPUT_SCHEMA["event_kind"])
    registry_event_kinds = tuple(
        STRUCTURED_AMBIENT_REGISTRY_MANIFEST["event_kind"]
    )
    expected_combinations = (
        len(STRUCTURED_AMBIENT_EVENT_KINDS)
        * len(STRUCTURED_AMBIENT_TIMBRES)
        * len(STRUCTURED_AMBIENT_LOUDNESS)
        * len(STRUCTURED_AMBIENT_TEMPORAL_PATTERNS)
    )
    if (
        len(STRUCTURED_AMBIENT_EVENT_KINDS)
        != EXPECTED_STRUCTURED_AMBIENT_EVENT_KIND_COUNT
        or event_kinds != STRUCTURED_AMBIENT_EVENT_KINDS
        or registry_event_kinds != STRUCTURED_AMBIENT_EVENT_KINDS
        or expected_combinations
        != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        or len(_CANONICAL_AMBIENT_TUPLE_STRINGS)
        != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        or len(set(_CANONICAL_AMBIENT_TUPLE_STRINGS))
        != EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS
        or AMBIENT_CONSTRAINT_MANIFEST.get("leaf_count")
        != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        or AMBIENT_CONSTRAINT_MANIFEST.get("reachable_count")
        != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        or semantic_hash(AMBIENT_CONSTRAINT_MANIFEST)
        != AMBIENT_CONSTRAINT_MANIFEST_SHA256
        or "continuous_liquid_flow"
        not in STRUCTURED_AMBIENT_EVENT_KINDS
        or any(
            event_kind in STRUCTURED_AMBIENT_EVENT_KINDS
            for event_kind in ("pour", "open", "chop", "stir", "drop")
        )
    ):
        raise AuthoringError("STATIC_AMBIENT_CONTRACT_DRIFT")


AMBIENT_ACCEPTED_FIELDS = frozenset(
    {
        "ambient_semantics",
        "ambient_description",
        "ambient_query",
        "ambient_semantic_tuple_sha256",
        "ambient_description_sha256",
        "ambient_query_sha256",
        "ambient_derived_text_sha256",
        "ambient_registry_sha256",
        "ambient_generator_sha256",
        "ambient_template_sha256",
        "ambient_constraint_kind",
        "ambient_constraint_manifest",
        "ambient_constraint_manifest_sha256",
        "ambient_constraint_leaf_count",
        "ambient_constraint_reachable_count",
    }
)
AMBIENT_BINDING_PAYLOAD_FIELDS = (
    "ambient_semantics",
    "ambient_description",
    "ambient_query",
    "ambient_semantic_tuple_sha256",
    "ambient_description_sha256",
    "ambient_query_sha256",
    "ambient_derived_text_sha256",
    "ambient_registry_sha256",
    "ambient_generator_sha256",
    "ambient_template_sha256",
    "ambient_constraint_kind",
    "ambient_constraint_manifest",
    "ambient_constraint_manifest_sha256",
    "ambient_constraint_leaf_count",
    "ambient_constraint_reachable_count",
)


def legacy_bundle_hash(value: Any) -> str:
    """Hash the repaired v1 bundle's pretty-printed canonical representation."""

    payload = (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path, block_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def pipeline_tool_sha256(root: Path = ROOT) -> str:
    path = _repo_path(root, PIPELINE_TOOL)
    if not path.is_file():
        raise AuthoringError("PIPELINE_TOOL_MISSING")
    return "sha256:" + file_sha256(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(payload)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    atomic_bytes(
        path,
        (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        ).encode("utf-8"),
        mode=mode,
    )


def atomic_jsonl(
    path: Path, rows: Sequence[Mapping[str, Any]], *, mode: int = 0o600
) -> None:
    payload = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
        for row in rows
    )
    atomic_bytes(path, payload.encode("utf-8"), mode=mode)


def _verify_payload_hash(document: Mapping[str, Any], label: str) -> None:
    observed = document.get("payload_sha256")
    if not isinstance(observed, str):
        raise AuthoringError(f"{label}:PAYLOAD_HASH_MISSING")
    body = {k: v for k, v in document.items() if k != "payload_sha256"}
    if observed != legacy_bundle_hash(body):
        raise AuthoringError(f"{label}:PAYLOAD_HASH_MISMATCH")


def _repo_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _normalized_words(text: str) -> list[str]:
    return WORD_RE.findall(text.casefold())


def _normalized_text(text: str) -> str:
    return " ".join(_normalized_words(text))


def _normalized_token_set(text: str) -> frozenset[str]:
    return frozenset(_normalized_words(text))


def _factor_pair_identity(
    description: str,
    query: str,
) -> dict[str, bool]:
    normalized_equal = _normalized_text(description) == _normalized_text(query)
    description_tokens = _normalized_token_set(description)
    query_tokens = _normalized_token_set(query)
    return {
        "normalized_equal": normalized_equal,
        "token_sets_equal": bool(description_tokens)
        and description_tokens == query_tokens,
    }


PAIR_QUERY_SCAFFOLD_TOKENS = frozenset(
    {
        "a",
        "an",
        "are",
        "be",
        "being",
        "can",
        "could",
        "do",
        "does",
        "find",
        "heard",
        "how",
        "is",
        "locate",
        "matching",
        "of",
        "please",
        "retrieve",
        "show",
        "that",
        "the",
        "there",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whose",
        "with",
        "would",
    }
)
PAIR_RELATION_SCAFFOLD_TOKENS = frozenset(
    {
        "accompanies",
        "accompanying",
        "alongside",
        "as",
        "at",
        "beside",
        "during",
        "event",
        "events",
        "occurs",
        "occurring",
        "sound",
        "sounds",
        "while",
    }
)
AMBIENT_PAIR_SCAFFOLD_TOKENS = frozenset(
    {
        "acoustic",
        "audible",
        "audibly",
        "hear",
        "hearing",
        "noise",
        "noises",
        "sonic",
    }
)
VISUAL_GENERIC_QUERY_RE = re.compile(
    r"^(?:what|which)\s+(?:is|are|does|do)\s+"
    r"(?:a|an|the)?\s*(?:person|people|someone|operator|worker|hand)"
    r"\s+(?:do|does|doing|happen|happening)\b",
    re.IGNORECASE,
)
CONTENT_TOKEN_ALIASES = {
    "metallic": "metal",
    "softly": "soft",
    "loudly": "loud",
    "quietly": "quiet",
}
def _inflection_candidates(word: str) -> set[str]:
    candidates = {word}
    if word in CONTENT_TOKEN_ALIASES:
        candidates.add(CONTENT_TOKEN_ALIASES[word])
    if word.endswith("ies") and len(word) > 4:
        candidates.add(word[:-3] + "y")
    if word.endswith("ing") and len(word) > 5:
        stem = word[:-3]
        candidates.update({stem, stem + "e"})
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            candidates.add(stem[:-1])
    if word.endswith("ed") and len(word) > 4:
        stem = word[:-2]
        candidates.update({stem, stem + "e"})
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            candidates.add(stem[:-1])
    if word.endswith(("sses", "shes", "ches", "xes", "zes", "oes")):
        candidates.add(word[:-2])
    elif (
        word.endswith("es") and len(word) > 4
    ) or (
        word.endswith("s") and len(word) > 3
    ):
        candidates.add(word[:-1])
    return candidates


def _canonical_pair_token(
    word: str,
    *,
    description_words: set[str] | None = None,
) -> str:
    acoustic = ACOUSTIC_FORM_TO_CONCEPT.get(word)
    if acoustic is not None:
        return f"acoustic:{acoustic}"
    candidates = _inflection_candidates(word)
    if description_words:
        matching = sorted(candidates & description_words)
        if matching:
            return _canonical_pair_token(matching[0])
    aliased = CONTENT_TOKEN_ALIASES.get(word)
    if aliased is not None:
        return aliased
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ing") and len(word) > 5:
        stem = word[:-3]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        if stem.endswith(("c", "v")) or stem in {"mak", "plac", "slic", "tak"}:
            return stem + "e"
        return stem
    if word.endswith("ed") and len(word) > 4:
        stem = word[:-2]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        if stem.endswith(("c", "v")) or stem in {"mak", "plac", "slic"}:
            return stem + "e"
        return stem
    if word.endswith(("sses", "shes", "ches", "xes", "zes", "oes")):
        return word[:-2]
    if word.endswith("es") and len(word) > 4:
        return word[:-1]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _paired_content_tokens(
    text: str,
    *,
    factor_kind: str,
    description_words: set[str] | None = None,
) -> set[str]:
    ignored = set(PAIR_QUERY_SCAFFOLD_TOKENS) | set(
        PAIR_RELATION_SCAFFOLD_TOKENS
    )
    if factor_kind == "ambient":
        ignored.update(AMBIENT_PAIR_SCAFFOLD_TOKENS)
    words = _normalized_words(text)
    return {
        _canonical_pair_token(
            word,
            description_words=description_words,
        )
        for word in words
        if word not in ignored
    }


def _validate_paired_factor_semantics(
    description: str,
    query: str,
    *,
    factor_kind: str,
) -> dict[str, Any]:
    description_word_sequence = _normalized_words(description)
    description_words = set(description_word_sequence)
    query_word_sequence = _normalized_words(query)
    if factor_kind == "visual" and "by" in query_word_sequence:
        raise AuthoringError("MODEL_VISUAL_QUERY_SEMANTIC_ADDITION:by")
    description_content = _paired_content_tokens(
        description,
        factor_kind=factor_kind,
    )
    query_content = _paired_content_tokens(
        query,
        factor_kind=factor_kind,
        description_words=description_words,
    )
    unsupported = sorted(query_content - description_content)
    anchors = sorted(query_content & description_content)
    if factor_kind == "visual" and VISUAL_GENERIC_QUERY_RE.search(query):
        raise AuthoringError("MODEL_VISUAL_QUERY_GENERIC_CONTENT_INVALID")
    if not query_content or not anchors:
        raise AuthoringError(
            f"MODEL_{factor_kind.upper()}_QUERY_CONTENT_ANCHOR_REQUIRED"
        )
    if unsupported:
        raise AuthoringError(
            f"MODEL_{factor_kind.upper()}_QUERY_SEMANTIC_ADDITION:"
            + ",".join(unsupported)
        )
    return {
        "description_content": sorted(description_content),
        "query_content": sorted(query_content),
        "anchored_content": anchors,
        "unsupported_query_content": unsupported,
    }


def _slot_names(family: Mapping[str, Any]) -> list[str]:
    texts = [
        str(family.get("question_template", "")),
        str(family.get("answer_template", "")),
        *[
            str(row.get("template", ""))
            for row in family.get("atomic_claim_templates", [])
        ],
    ]
    return sorted({slot for text in texts for slot in SLOT_RE.findall(text)})


def _bundle_paths(root: Path, bundle: Path) -> dict[str, Path]:
    base = _repo_path(root, bundle)
    return {name: base / name for name in sorted(ALLOWED_BUNDLE_FILES)}


def load_structural_bundle(
    root: Path = ROOT, bundle: Path = DEFAULT_BUNDLE
) -> dict[str, Any]:
    """Load only the structural provisional files on the authoring allowlist."""

    paths = _bundle_paths(root, bundle)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise AuthoringError(f"BUNDLE_FILES_MISSING:{','.join(missing)}")
    documents = {name: load_json(path) for name, path in paths.items()}
    for name, document in documents.items():
        if not isinstance(document, Mapping):
            raise AuthoringError(f"{name}:NOT_OBJECT")
        _verify_payload_hash(document, name)

    families_doc = documents["family_registry.json"]
    evidence_doc = documents["evidence_registry.json"]
    split_doc = documents["source_split_manifest.json"]
    leakage_doc = documents["leakage_gate.json"]
    if families_doc.get("status") != "MACHINE_PROVISIONAL_FROZEN":
        raise AuthoringError("FAMILY_REGISTRY_NOT_FROZEN")
    if evidence_doc.get("status") != "MACHINE_PROVISIONAL_EVIDENCE_FROZEN":
        raise AuthoringError("EVIDENCE_REGISTRY_NOT_FROZEN")
    if leakage_doc.get("status") != "PASS":
        raise AuthoringError("PROVISIONAL_LEAKAGE_GATE_NOT_PASS")
    if split_doc.get("source_id") != "P23_102":
        raise AuthoringError("UNEXPECTED_SOURCE_SPLIT")
    split_text = canonical_bytes(split_doc).decode("utf-8")
    if '"evaluation_source_ids":[]' not in split_text:
        raise AuthoringError("SOURCE_SPLIT_NOT_DEVELOPMENT_ONLY")

    families = families_doc.get("families")
    evidence = evidence_doc.get("evidence")
    if not isinstance(families, list) or not isinstance(evidence, list):
        raise AuthoringError("REGISTRY_ROWS_NOT_LISTS")
    if len(families) != EXPECTED_FAMILIES:
        raise AuthoringError("FAMILY_COUNT_MISMATCH")
    if len(evidence) != EXPECTED_HANDLES:
        raise AuthoringError("EVIDENCE_COUNT_MISMATCH")

    evidence_by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in evidence:
        if not isinstance(row, Mapping):
            raise AuthoringError("EVIDENCE_ROW_NOT_OBJECT")
        evidence_by_family[str(row.get("family_id"))].append(row)

    target_by_interval: dict[tuple[int, int], dict[str, Any]] = {}
    family_specs: list[dict[str, Any]] = []
    near_count = 0
    far_count = 0
    for family_index, family in enumerate(families, 1):
        if not isinstance(family, Mapping):
            raise AuthoringError("FAMILY_ROW_NOT_OBJECT")
        private_family_id = str(family.get("family_id"))
        rows = evidence_by_family.get(private_family_id, [])
        if not rows:
            raise AuthoringError("FAMILY_WITHOUT_EVIDENCE")
        if family.get("profile_hypothesis") != "V+A":
            raise AuthoringError("NON_VA_FAMILY_ENTERED_AUTHORING")
        intervals: dict[tuple[int, int], set[str]] = defaultdict(set)
        handles_by_interval: dict[tuple[int, int], list[str]] = defaultdict(list)
        for row in rows:
            start_us = row.get("start_us")
            end_us = row.get("end_us")
            if (
                isinstance(start_us, bool)
                or not isinstance(start_us, int)
                or isinstance(end_us, bool)
                or not isinstance(end_us, int)
                or start_us < 0
                or end_us <= start_us
            ):
                raise AuthoringError("INVALID_TARGET_INTERVAL")
            interval = (start_us, end_us)
            modality = str(row.get("modality"))
            intervals[interval].add(modality)
            handles_by_interval[interval].append(
                str(row.get("evidence_handle_id"))
            )
        expected_modalities = {"vision", "ambient_audio"}
        if any(value != expected_modalities for value in intervals.values()):
            raise AuthoringError("TARGET_INTERVAL_MODALITY_PAIR_INCOMPLETE")
        ordered_intervals = sorted(intervals)
        kind = str(family.get("candidate_kind"))
        if kind == "near_local" and len(ordered_intervals) == 1:
            near_count += 1
            shape = "one_component"
        elif kind == "coherent_far_multi_hop" and len(ordered_intervals) == 2:
            far_count += 1
            shape = "two_component_ordered"
        else:
            raise AuthoringError("FAMILY_SHAPE_MISMATCH")
        family_specs.append(
            {
                "family_key": f"family-{family_index:03d}",
                "private_family_id": private_family_id,
                "shape": shape,
                "slot_names": _slot_names(family),
                "private_template_hashes": {
                    "question_template": semantic_hash(
                        family.get("question_template")
                    ),
                    "answer_template": semantic_hash(
                        family.get("answer_template")
                    ),
                    "atomic_claim_templates": semantic_hash(
                        [
                            row.get("template")
                            for row in family.get(
                                "atomic_claim_templates", []
                            )
                        ]
                    ),
                },
                "intervals": [
                    {
                        "start_us": start_us,
                        "end_us": end_us,
                        "private_evidence_handle_ids": sorted(
                            handles_by_interval[(start_us, end_us)]
                        ),
                    }
                    for start_us, end_us in ordered_intervals
                ],
            }
        )
        for start_us, end_us in ordered_intervals:
            target_by_interval.setdefault(
                (start_us, end_us),
                {
                    "start_us": start_us,
                    "end_us": end_us,
                    "family_keys": [],
                },
            )["family_keys"].append(f"family-{family_index:03d}")

    if near_count != EXPECTED_NEAR_FAMILIES:
        raise AuthoringError("NEAR_FAMILY_COUNT_MISMATCH")
    if far_count != EXPECTED_FAR_FAMILIES:
        raise AuthoringError("FAR_FAMILY_COUNT_MISMATCH")
    if len(target_by_interval) != EXPECTED_TARGET_CLIPS:
        raise AuthoringError("UNIQUE_TARGET_CLIP_COUNT_MISMATCH")

    target_specs = []
    interval_to_key: dict[tuple[int, int], str] = {}
    for clip_index, ((start_us, end_us), row) in enumerate(
        sorted(target_by_interval.items()), 1
    ):
        clip_key = f"clip-{clip_index:03d}"
        interval_to_key[(start_us, end_us)] = clip_key
        target_specs.append(
            {
                "clip_key": clip_key,
                "start_us": start_us,
                "end_us": end_us,
                "duration_us": end_us - start_us,
                "family_keys": sorted(row["family_keys"]),
            }
        )
    for family in family_specs:
        for interval in family["intervals"]:
            interval["clip_key"] = interval_to_key[
                (interval["start_us"], interval["end_us"])
            ]

    return {
        "documents": documents,
        "paths": {name: str(path) for name, path in paths.items()},
        "file_hashes": {
            name: "sha256:" + file_sha256(path)
            for name, path in paths.items()
        },
        "families": family_specs,
        "targets": target_specs,
        "counts": {
            "families": len(family_specs),
            "handles": len(evidence),
            "target_clips": len(target_specs),
            "near_families": near_count,
            "far_families": far_count,
            "queries": EXPECTED_QUERY_COUNT,
        },
    }


VISUAL_SYSTEM_PROMPT = """Author one neutral visual retrieval factor from exactly one supplied silent video component.

Only the video frames are available. Return exactly one strict JSON object with exactly these two keys: visual_description, visual_query. Field roles are different: visual_description is a declarative statement of concrete visible content; visual_query is a structurally different, specific retrieval question or noun phrase about only that same content. The query must not add a person, object, material, action, state, transition, direction, or agent-patient relation absent from the description. It must retain at least one or two concrete content anchors from the description and cannot be a generic scaffold such as “What is the person doing?” Positive active-question pattern: description “A hand lifts a metal bowl from a counter.” / query “Which metal bowl is a hand lifting from the counter?” Positive object/action retrieval pattern: the same description / query “metal bowl lifting from the counter”. A passive query without an agent is also allowed when it adds no semantics, for example “Which metal bowl is being lifted from the counter?” Do not use “by” to introduce an agent or any visual relation. Every standalone `by` token in visual_query fails closed, including a locative use; this conservative precision tradeoff is intentional. The ordinary word “nearby” is unaffected. Prefer active questions, agent-free passive questions, concrete object/action noun phrases, or specific object/action retrieval wording. Negative agentive-passive pattern: the description above / query “Which metal bowl is lifted by the hand from the counter?” Negative nearby-relation patterns: “A worker and a sealed box stand nearby.” cannot become “Which box is sealed by the worker?”, and “A covered bowl sits while a hand rests nearby.” cannot become “Which bowl is covered by the hand?” Negative identity pattern: description and query both “A hand lifts a metal bowl.” Negative added-semantics pattern: description “A metal bowl rests on a counter.” / query “What is the person doing with the bowl?” Describe concrete visible events, object states, and transitions. Do not infer sound, speech, identity, intent, correctness, causality, continuity, or facts outside the supplied component. Do not refer to another, other, first, second, previous, next, or multiple components, segments, stages, or hops. Do not mention datasets, sources, files, clips, timestamps, identifiers, slot names, answer keys, ordinals, component counts, or modality labels. The query must stand alone without unresolved pronouns, “then,” or prior-state deixis. Query and description must not be normalized copies, punctuation/case variants, token-reordered copies, or near-identical paraphrase copies. Use concise English noun phrases or questions. No markdown."""

AMBIENT_SYSTEM_PROMPT = """Classify one audio-only non-speech event into the supplied closed acoustic enums.

Only the audio waveform is available; no video frames are available. Return exactly one strict JSON object with exactly these keys and nesting: event_kind, acoustic_properties.timbre, acoustic_properties.loudness, acoustic_properties.temporal_pattern. Copy only enum values listed in required_output_schema. Do not write a description, query, sentence, explanation, markdown, or any additional key. Select only the heard event and its acoustic timbre, loudness, and temporal pattern. continuous_liquid_flow means continuous or pulsed liquid-flow sound without declaring pouring, a source, container, location, or direction. Distinguish it from discrete drip, weak narrow trickle, liquid moving within a container as slosh, impact as splash, resonant conduit-like gurgle, and discrete bubble events. Never output or infer a source, material, object, person, agent, location, direction, action state, or perceptual source similarity; source_hint and every equivalent field are forbidden even when null. event_kind names an acoustic event, never an inferred action: open, close, drop, chop, pour, place, cut, break, shatter, tear, rip, stir, clap, stomp, slide, and slam are forbidden as event_kind. metallic is a timbre property and never means a metal object. Do not transcribe, quote, summarize, classify, or invent lexical speech. Nonlexical vocalization may use only an allowed non-speech event enum such as throat_clear. Do not infer identity, intent, correctness, causality, continuity, visual state, opening/closing direction, or facts outside the supplied audio. No markdown."""

COMPOSITION_SYSTEM_PROMPT = """Select the supplied controlled relation kind for one frozen family shape.

Return exactly one strict JSON object with exactly one key: relation_kind. Copy relation_kind exactly from required_relation_kind. Do not generate any other field or any natural-language relation text. Do not author component clauses, summaries, observations, ordinals, cardinality, direction, identity, continuity, intent, correctness, or causality. No markdown."""

# Compatibility names retained for callers that inspect the public module.
COMPONENT_SYSTEM_PROMPT = VISUAL_SYSTEM_PROMPT
SYSTEM_PROMPT = VISUAL_SYSTEM_PROMPT

VISUAL_OUTPUT_SCHEMA = {
    "visual_description": "one neutral content-grounded sentence",
    "visual_query": "one distinct content-grounded query",
}
AMBIENT_OUTPUT_SCHEMA = {
    "event_kind": list(STRUCTURED_AMBIENT_EVENT_KINDS),
    "acoustic_properties": {
        "timbre": list(STRUCTURED_AMBIENT_TIMBRES),
        "loudness": list(STRUCTURED_AMBIENT_LOUDNESS),
        "temporal_pattern": list(
            STRUCTURED_AMBIENT_TEMPORAL_PATTERNS
        ),
    },
}
COMPONENT_OUTPUT_SCHEMA = {
    **VISUAL_OUTPUT_SCHEMA,
    **{key: "mechanically derived from ambient_semantics" for key in (
        "ambient_description",
        "ambient_query",
    )},
    "ambient_semantics": dict(AMBIENT_OUTPUT_SCHEMA),
    "ambient_semantic_tuple_sha256": "canonical tuple SHA-256",
    "ambient_description_sha256": "derived description SHA-256",
    "ambient_query_sha256": "derived query SHA-256",
    "ambient_derived_text_sha256": "joint derived text SHA-256",
    "ambient_registry_sha256": "closed ambient registry SHA-256",
    "ambient_generator_sha256": "mechanical generator SHA-256",
    "ambient_template_sha256": "mechanical template SHA-256",
    "ambient_constraint_kind": AMBIENT_CONSTRAINT_KIND,
    "ambient_constraint_manifest": (
        "canonical tuple token-prefix constraint manifest"
    ),
    "ambient_constraint_manifest_sha256": (
        "canonical tuple token-prefix constraint manifest SHA-256"
    ),
    "ambient_constraint_leaf_count": (
        EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
    ),
    "ambient_constraint_reachable_count": (
        EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
    ),
}
COMPOSITION_OUTPUT_SCHEMA = {
    "relation_kind": (
        "copy required_relation_kind exactly: local_cooccurrence or "
        "ordered_1_then_2"
    ),
}

RELATION_KIND_BY_SHAPE = {
    "one_component": "local_cooccurrence",
    "two_component_ordered": "ordered_1_then_2",
}


def _validate_model_visible_payload(payload: Mapping[str, Any]) -> None:
    serialized = canonical_bytes(payload).decode("utf-8")
    if any(key in serialized for key in FORBIDDEN_MODEL_VISIBLE_KEYS):
        raise AuthoringError("FORBIDDEN_FIELD_IN_MODEL_VISIBLE_PROMPT")
    if PRIVATE_ID_RE.search(serialized) or TIMESTAMP_RE.search(serialized):
        raise AuthoringError("PRIVATE_LITERAL_IN_MODEL_VISIBLE_PROMPT")
    if any(
        literal.casefold() in serialized.casefold()
        for literal in SOURCE_LITERALS
    ):
        raise AuthoringError("SOURCE_LITERAL_IN_MODEL_VISIBLE_PROMPT")


def visual_model_visible_prompt() -> dict[str, Any]:
    """Return the fixed payload for one video-only factor."""

    payload = {
        "task": "author_one_video_only_visual_factor",
        "required_output_schema": dict(VISUAL_OUTPUT_SCHEMA),
        "constraints": {
            "exactly_one_media_component_supplied": True,
            "video_only": True,
            "audio_supplied": False,
            "ordinal_model_authorship_forbidden": True,
            "queries_must_be_content_grounded": True,
            "sound_inference_forbidden": True,
            "ids_timestamps_source_names_forbidden": True,
            "modality_labels_in_final_text_forbidden": True,
            "handle_queries_must_resolve_all_references": True,
            "cross_component_or_cardinality_language_forbidden": True,
            "causal_language_forbidden": True,
            "query_description_copying_forbidden": True,
            "query_description_exact_or_token_set_identity_forbidden": True,
            "query_must_not_add_semantic_content": True,
            "generic_question_scaffold_forbidden": True,
            "description_role": "declarative_observation",
            "query_role": "specific_distinct_retrieval_request",
            "human_semantic_labels_supplied": False,
            "retrieval_information_supplied": False,
        },
    }
    _validate_model_visible_payload(payload)
    return payload


def ambient_model_visible_prompt() -> dict[str, Any]:
    """Return the fixed payload for one structured audio-only factor."""

    payload = {
        "task": "author_one_audio_only_ambient_factor",
        "required_output_schema": dict(AMBIENT_OUTPUT_SCHEMA),
        "event_kind_definition": dict(
            STRUCTURED_AMBIENT_EVENT_DEFINITIONS
        ),
        "event_kind_confusions": dict(
            STRUCTURED_AMBIENT_EVENT_CONFUSIONS
        ),
        "constraints": {
            "exactly_one_media_component_supplied": True,
            "audio_only": True,
            "video_frames_supplied": False,
            "ordinal_model_authorship_forbidden": True,
            "copy_or_invent_lexical_speech_forbidden": True,
            "ids_timestamps_source_names_forbidden": True,
            "closed_enum_output_only": True,
            "canonical_tuple_token_constraint": {
                "constraint_kind": AMBIENT_CONSTRAINT_KIND,
                "manifest_sha256": AMBIENT_CONSTRAINT_MANIFEST_SHA256,
                "leaf_count": EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS,
                "reachable_count": EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS,
            },
            "natural_language_model_output_forbidden": True,
            "description_model_authorship_forbidden": True,
            "query_model_authorship_forbidden": True,
            "event_kind_must_be_acoustic_event": True,
            "action_event_kind_forbidden": True,
            "source_material_object_agent_location_direction_forbidden": True,
            "source_hint_field_forbidden_even_when_null": True,
            "pure_acoustic_dimensions_only": [
                "event_kind",
                "timbre",
                "loudness",
                "temporal_pattern",
            ],
            "mechanical_text_calls": 0,
            "human_semantic_labels_supplied": False,
            "retrieval_information_supplied": False,
        },
    }
    _validate_model_visible_payload(payload)
    return payload


def component_model_visible_prompt() -> dict[str, Any]:
    """Compatibility helper returning the video-only visual payload."""

    return visual_model_visible_prompt()


def composition_model_visible_prompt(
    family_shape: str,
    component_factors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the text-only composition payload from accepted factors only."""

    if family_shape not in RELATION_KIND_BY_SHAPE:
        raise AuthoringError("FAMILY_SHAPE_ENUM_INVALID")
    expected_count = 1 if family_shape == "one_component" else 2
    if len(component_factors) != expected_count:
        raise AuthoringError("COMPOSITION_COMPONENT_COUNT_MISMATCH")
    accepted = []
    for factor in component_factors:
        model_visible_projection = accepted_component_model_projection(
            factor
        )
        serialized_factor = canonical_bytes(
            model_visible_projection
        ).decode("utf-8")
        if (
            PRIVATE_ID_RE.search(serialized_factor)
            or TIMESTAMP_RE.search(serialized_factor)
            or MODEL_VISIBLE_IDENTIFIER_RE.search(serialized_factor)
            or RETRIEVAL_INFO_RE.search(serialized_factor)
            or any(
                literal.casefold() in serialized_factor.casefold()
                for literal in SOURCE_LITERALS
            )
        ):
            raise AuthoringError("COMPOSITION_INPUT_FIREWALL_VIOLATION")
        accepted.append(model_visible_projection)
    payload = {
        "task": "select_controlled_family_relation_kind",
        "family_shape": family_shape,
        "component_count": expected_count,
        "required_relation_kind": RELATION_KIND_BY_SHAPE[family_shape],
        "required_output_schema": dict(COMPOSITION_OUTPUT_SCHEMA),
        "constraints": {
            "accepted_component_factor_count": len(accepted),
            "component_clauses_model_authorship_forbidden": True,
            "component_summaries_model_authorship_forbidden": True,
            "component_ordinals_assigned_mechanically": True,
            "component_content_assembled_mechanically": True,
            "new_observations_forbidden": True,
            "natural_language_relation_authorship_forbidden": True,
            "ids_timestamps_source_names_forbidden": True,
            "retrieval_information_supplied": False,
            "relation_kind_must_equal_required_relation_kind": True,
            "directional_wording_model_authorship_forbidden": True,
            "cardinality_wording_model_authorship_forbidden": True,
            "one_component_multi_component_wording_forbidden": True,
            "two_component_content_coverage_is_mechanical": True,
            "two_component_direction_is_mechanical_1_then_2": True,
            "unsupported_cross_component_continuity_forbidden": True,
            "identity_and_causality_forbidden": True,
        },
    }
    _validate_model_visible_payload(payload)
    return payload


def _prompt_record(
    *,
    factor_kind: str,
    user_payload: Mapping[str, Any],
    system_prompt: str,
    family_key: str | None = None,
    component_ordinal: int | None = None,
    clip_key: str | None = None,
    media_modality: str | None = None,
) -> dict[str, Any]:
    if factor_kind in {"visual", "ambient"}:
        if media_modality != factor_kind or clip_key is None:
            raise AuthoringError("PROMPT_MEDIA_MODALITY_BINDING_INVALID")
        media_modalities = [media_modality]
    elif factor_kind == "family_composition":
        if media_modality is not None or clip_key is not None:
            raise AuthoringError("PROMPT_COMPOSITION_MEDIA_FORBIDDEN")
        media_modalities = []
    else:
        raise AuthoringError("PROMPT_FACTOR_KIND_INVALID")
    record = {
        "factor_kind": factor_kind,
        "system_prompt": system_prompt,
        "user_payload": dict(user_payload),
        "system_prompt_sha256": semantic_hash(system_prompt),
        "user_payload_sha256": semantic_hash(user_payload),
        "combined_prompt_sha256": semantic_hash(
            {"system": system_prompt, "user": user_payload}
        ),
        "media_component_count": 1 if media_modalities else 0,
        "media_modalities": media_modalities,
        "media_component_clip_keys": (
            [clip_key] if media_modalities else []
        ),
    }
    if family_key is not None:
        record["family_key"] = family_key
    if component_ordinal is not None:
        record["component_ordinal"] = component_ordinal
    return record


def model_visible_prompt(family: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility helper returning the fixed one-component payload."""

    del family
    return component_model_visible_prompt()


def build_prompt_manifest(structural: Mapping[str, Any]) -> dict[str, Any]:
    _validate_static_ambient_contract()
    visual_prompts = []
    ambient_prompts = []
    composition_contracts = []
    for family in structural["families"]:
        for ordinal, interval in enumerate(family["intervals"], 1):
            visual_prompts.append(
                _prompt_record(
                    factor_kind="visual",
                    user_payload=visual_model_visible_prompt(),
                    system_prompt=VISUAL_SYSTEM_PROMPT,
                    family_key=family["family_key"],
                    component_ordinal=ordinal,
                    clip_key=interval["clip_key"],
                    media_modality="visual",
                )
            )
            ambient_prompts.append(
                _prompt_record(
                    factor_kind="ambient",
                    user_payload=ambient_model_visible_prompt(),
                    system_prompt=AMBIENT_SYSTEM_PROMPT,
                    family_key=family["family_key"],
                    component_ordinal=ordinal,
                    clip_key=interval["clip_key"],
                    media_modality="ambient",
                )
            )
        composition_contracts.append(
            {
                "family_key": family["family_key"],
                "factor_kind": "family_composition",
                "family_shape": family["shape"],
                "component_count": len(family["intervals"]),
                "required_relation_kind": RELATION_KIND_BY_SHAPE[
                    str(family["shape"])
                ],
                "system_prompt": COMPOSITION_SYSTEM_PROMPT,
                "system_prompt_sha256": semantic_hash(
                    COMPOSITION_SYSTEM_PROMPT
                ),
                "required_output_schema": dict(COMPOSITION_OUTPUT_SCHEMA),
                "media_component_count": 0,
                "composition_input": (
                    "frozen_shape_only_component_content_is_mechanical"
                ),
                "resolved": False,
            }
        )
    return {
        "schema_version": PROMPT_MANIFEST_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "ambient_constraint": ambient_constraint_contract(),
        "prompt_count": len(visual_prompts)
        + len(ambient_prompts)
        + len(composition_contracts),
        "visual_prompt_count": len(visual_prompts),
        "ambient_prompt_count": len(ambient_prompts),
        "composition_prompt_count": len(composition_contracts),
        "visual_prompts": visual_prompts,
        "ambient_prompts": ambient_prompts,
        "composition_contracts": composition_contracts,
        "resolved_composition_prompts": [],
        "model_visible_firewall": {
            "visual_target_media": "one exact target video; audio absent",
            "ambient_target_media": "one exact target audio; video absent",
            "ambient_model_output": "closed structured semantic tuple only",
            "ambient_description_query": (
                "mechanically derived after tuple validation"
            ),
            "ambient_registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
            "ambient_generator_sha256": AMBIENT_GENERATOR_SHA256,
            "ambient_template_sha256": AMBIENT_TEMPLATE_SHA256,
            "ambient_constraint_kind": AMBIENT_CONSTRAINT_KIND,
            "ambient_constraint_manifest": json.loads(
                canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
            ),
            "ambient_constraint_manifest_sha256": (
                AMBIENT_CONSTRAINT_MANIFEST_SHA256
            ),
            "ambient_constraint_leaf_count": (
                EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            ),
            "ambient_constraint_reachable_count": (
                EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            ),
            "composition_media": False,
            "composition_input": (
                "frozen shape, exact component count, and required relation "
                "kind; all relation text, clauses, and direction are mechanical"
            ),
            "retrieval_rankings": False,
            "non_target_vectors": False,
            "retrieval_outcomes": False,
            "answer_keys": False,
            "human_semantic_labels": False,
            "private_ids_or_timestamps": False,
            "model_authored_ordinals": False,
            "model_authored_cardinality_or_direction": False,
            "model_authored_relation_natural_language": False,
        },
    }


def _strict_text(
    value: Any,
    field: str,
    *,
    max_words: int,
    min_words: int = 3,
) -> str:
    if not isinstance(value, str):
        raise AuthoringError(f"MODEL_FIELD_NOT_STRING:{field}")
    text = " ".join(value.split())
    words = _normalized_words(text)
    if not text or len(words) < min_words or len(words) > max_words:
        raise AuthoringError(f"MODEL_FIELD_LENGTH_INVALID:{field}")
    if "\n" in text:
        raise AuthoringError(f"MODEL_FIELD_MULTILINE:{field}")
    return text


def _forbidden_factor_structure(value: Any) -> None:
    if not isinstance(value, Mapping):
        return
    if "components" in value:
        components = value["components"]
        if not isinstance(components, list) or len(components) != 1:
            raise AuthoringError("MODEL_COMPONENT_COUNT_MISMATCH")
        if (
            components
            and isinstance(components[0], Mapping)
            and components[0].get("ordinal") != 1
        ):
            raise AuthoringError("MODEL_COMPONENT_ORDINAL_MISMATCH")
        raise AuthoringError("MODEL_LEGACY_COMBINED_OUTPUT_FORBIDDEN")
    forbidden_keys = {
        "ordinal",
        "component_count",
        "clip_key",
        "family_key",
        "family_id",
        "record_id",
        "timestamp",
        "start_us",
        "end_us",
    }
    if "relation_kind" in value:
        forbidden_keys.remove("component_count")
    if forbidden_keys & {str(key) for key in value}:
        raise AuthoringError("MODEL_OUTPUT_IDENTIFIER_OR_ORDINAL_FORBIDDEN")


def _matching_patterns(
    text: str, patterns: Sequence[re.Pattern[str]]
) -> list[str]:
    return [pattern.pattern for pattern in patterns if pattern.search(text)]


def _validate_component_semantic_language(text: str, *, field: str) -> None:
    cross_references = _matching_patterns(
        text, COMPONENT_CROSS_REFERENCE_PATTERNS
    )
    if cross_references:
        raise AuthoringError(
            f"MODEL_COMPONENT_CROSS_REFERENCE_FORBIDDEN:{field}"
        )
    causal = _matching_patterns(text, UNSUPPORTED_CONTINUITY_PATTERNS[3:])
    if causal:
        raise AuthoringError(f"MODEL_CAUSAL_LANGUAGE_FORBIDDEN:{field}")


def validate_visual_factor_output(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AuthoringError("MODEL_OUTPUT_NOT_OBJECT")
    _forbidden_factor_structure(value)
    if set(value) != set(VISUAL_OUTPUT_SCHEMA):
        raise AuthoringError("MODEL_VISUAL_FACTOR_FIELD_SET_MISMATCH")
    parsed = {
        "visual_description": _strict_text(
            value["visual_description"],
            "visual_description",
            max_words=60,
        ),
        "visual_query": _strict_text(
            value["visual_query"], "visual_query", max_words=40
        ),
    }
    identity = _factor_pair_identity(
        parsed["visual_description"], parsed["visual_query"]
    )
    if identity["normalized_equal"] or identity["token_sets_equal"]:
        raise AuthoringError("MODEL_VISUAL_QUERY_DESCRIPTION_IDENTITY")
    for field, text in parsed.items():
        _validate_component_semantic_language(text, field=field)
    _validate_paired_factor_semantics(
        parsed["visual_description"],
        parsed["visual_query"],
        factor_kind="visual",
    )
    return parsed


def validate_ambient_semantic_tuple(value: Any) -> dict[str, Any]:
    """Validate the exact model-authored R18 acoustic semantic tuple."""

    if not isinstance(value, Mapping):
        raise AuthoringError("MODEL_OUTPUT_NOT_OBJECT")
    _forbidden_factor_structure(value)
    if "source_hint" in value:
        raise AuthoringError("MODEL_AMBIENT_SOURCE_HINT_FIELD_FORBIDDEN")
    if set(value) != set(AMBIENT_OUTPUT_SCHEMA):
        raise AuthoringError("MODEL_AMBIENT_FACTOR_FIELD_SET_MISMATCH")
    properties = value["acoustic_properties"]
    if not isinstance(properties, Mapping) or set(properties) != {
        "timbre",
        "loudness",
        "temporal_pattern",
    }:
        raise AuthoringError(
            "MODEL_AMBIENT_ACOUSTIC_PROPERTIES_FIELD_SET_MISMATCH"
        )
    event_kind = value["event_kind"]
    timbre = properties["timbre"]
    loudness = properties["loudness"]
    temporal_pattern = properties["temporal_pattern"]
    if (
        not isinstance(event_kind, str)
        or event_kind not in STRUCTURED_AMBIENT_EVENT_KINDS
    ):
        raise AuthoringError("MODEL_AMBIENT_EVENT_KIND_ENUM_INVALID")
    if timbre not in STRUCTURED_AMBIENT_TIMBRES:
        raise AuthoringError("MODEL_AMBIENT_TIMBRE_ENUM_INVALID")
    if loudness not in STRUCTURED_AMBIENT_LOUDNESS:
        raise AuthoringError("MODEL_AMBIENT_LOUDNESS_ENUM_INVALID")
    if temporal_pattern not in STRUCTURED_AMBIENT_TEMPORAL_PATTERNS:
        raise AuthoringError(
            "MODEL_AMBIENT_TEMPORAL_PATTERN_ENUM_INVALID"
        )
    return {
        "event_kind": event_kind,
        "acoustic_properties": {
            "timbre": timbre,
            "loudness": loudness,
            "temporal_pattern": temporal_pattern,
        },
    }


def ambient_semantic_content_atoms(
    value: Mapping[str, Any],
) -> tuple[str, ...]:
    semantic = validate_ambient_semantic_tuple(value)
    properties = semantic["acoustic_properties"]
    return tuple(
        atom
        for atom in (
            f"event_kind:{semantic['event_kind']}",
            (
                f"timbre:{properties['timbre']}"
                if properties["timbre"] is not None
                else None
            ),
            (
                f"loudness:{properties['loudness']}"
                if properties["loudness"] is not None
                else None
            ),
            (
                f"temporal_pattern:{properties['temporal_pattern']}"
                if properties["temporal_pattern"] is not None
                else None
            ),
        )
        if atom is not None
    )


def _ambient_scalar_values(
    semantic: Mapping[str, Any],
) -> dict[str, Any]:
    properties = semantic["acoustic_properties"]
    return {
        "timbre": properties["timbre"],
        "loudness": properties["loudness"],
        "temporal_pattern": properties["temporal_pattern"],
    }


def _ambient_render_property(
    property_name: str,
    value: str,
    *,
    spec: Mapping[str, Any],
) -> str:
    rendering = spec["property_rendering"][property_name]
    if rendering == "identity":
        return value
    if rendering == "replace_underscore_with_hyphen":
        return value.replace("_", "-")
    raise AuthoringError(
        f"AMBIENT_TEMPLATE_PROPERTY_RENDERING_INVALID:{property_name}"
    )


def _ambient_parse_property(
    property_name: str,
    rendered: str,
    *,
    spec: Mapping[str, Any],
) -> str:
    rendering = spec["property_rendering"][property_name]
    if rendering == "identity":
        return rendered
    if rendering == "replace_underscore_with_hyphen":
        return rendered.replace("-", "_")
    raise AuthoringError(
        f"AMBIENT_TEMPLATE_PROPERTY_RENDERING_INVALID:{property_name}"
    )


def _ambient_parser_expected_rendering(
    property_name: str,
    value: str,
    *,
    spec: Mapping[str, Any],
) -> str:
    """Parser-side rendering interpretation, independent of forward code."""

    rendering = spec["property_rendering"][property_name]
    if rendering == "identity":
        expected = value
    elif rendering == "replace_underscore_with_hyphen":
        expected = value.replace("_", "-")
    else:
        raise AuthoringError(
            f"AMBIENT_PARSE_PROPERTY_RENDERING_INVALID:{property_name}"
        )
    if not expected or expected.strip() != expected:
        raise AuthoringError(
            f"AMBIENT_PARSE_PROPERTY_RENDERING_INVALID:{property_name}"
        )
    return expected


def _ambient_rendered_properties(
    semantic: Mapping[str, Any],
    *,
    order: Sequence[str],
    spec: Mapping[str, Any],
) -> list[str]:
    values = _ambient_scalar_values(semantic)
    rendered = []
    for property_name in order:
        value = values[property_name]
        if value is not None:
            rendered.append(
                _ambient_render_property(
                    property_name, str(value), spec=spec
                )
            )
    return rendered


def _ambient_tuple_from_parsed_scalars(
    event_kind: str,
    parsed: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_ambient_semantic_tuple(
        {
            "event_kind": event_kind,
            "acoustic_properties": {
                "timbre": parsed["timbre"],
                "loudness": parsed["loudness"],
                "temporal_pattern": parsed["temporal_pattern"],
            },
        }
    )


def _parse_ordered_ambient_properties(
    rendered_values: Sequence[str],
    *,
    order: Sequence[str],
    spec: Mapping[str, Any],
    field: str,
) -> dict[str, Any]:
    """Strictly parse an optional ordered subsequence of template properties."""

    if len(rendered_values) > len(order):
        raise AuthoringError(f"AMBIENT_PARSE_PROPERTY_COUNT_INVALID:{field}")
    parsed: dict[str, Any] = {
        "timbre": None,
        "loudness": None,
        "temporal_pattern": None,
    }
    allowed = {
        "timbre": {
            _ambient_parser_expected_rendering("timbre", value, spec=spec)
            for value in STRUCTURED_AMBIENT_TIMBRES
            if value is not None
        },
        "loudness": {
            _ambient_parser_expected_rendering(
                "loudness", value, spec=spec
            )
            for value in STRUCTURED_AMBIENT_LOUDNESS
            if value is not None
        },
        "temporal_pattern": {
            _ambient_parser_expected_rendering(
                "temporal_pattern", value, spec=spec
            )
            for value in STRUCTURED_AMBIENT_TEMPORAL_PATTERNS
            if value is not None
        },
    }
    order_index = 0
    for rendered in rendered_values:
        matches = [
            index
            for index in range(order_index, len(order))
            if rendered in allowed[order[index]]
        ]
        if len(matches) != 1:
            raise AuthoringError(
                f"AMBIENT_PARSE_PROPERTY_ORDER_OR_VALUE_INVALID:{field}:"
                f"{rendered}"
            )
        index = matches[0]
        property_name = order[index]
        parsed[property_name] = _ambient_parse_property(
            property_name, rendered, spec=spec
        )
        order_index = index + 1
    return parsed


def _ambient_event_kind_from_text(event_text: str, *, field: str) -> str:
    matches = [
        event_kind
        for event_kind, rendered in STRUCTURED_AMBIENT_EVENT_TEXT.items()
        if rendered == event_text
    ]
    if len(matches) != 1:
        raise AuthoringError(f"AMBIENT_PARSE_EVENT_INVALID:{field}")
    return matches[0]


def parse_ambient_description(
    text: Any,
    *,
    spec: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse only the exact frozen description grammar, never free-form NLP."""

    selected = AMBIENT_TEMPLATE_SPEC if spec is None else spec
    grammar = selected["description"]
    if not isinstance(text, str):
        raise AuthoringError("AMBIENT_DESCRIPTION_PARSE_NOT_STRING")
    prefix = grammar["prefix"]
    suffix = grammar["suffix"]
    if (
        not text.startswith(prefix)
        or not text.endswith(suffix)
        or len(text) <= len(prefix) + len(suffix)
    ):
        raise AuthoringError("AMBIENT_DESCRIPTION_PARSE_GRAMMAR_MISMATCH")
    body = text[len(prefix) : -len(suffix)]
    candidates = sorted(
        STRUCTURED_AMBIENT_EVENT_TEXT.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    matches = []
    for event_kind, event_text in candidates:
        if body == event_text:
            matches.append((event_kind, []))
            continue
        separator = grammar["property_event_separator"]
        ending = separator + event_text
        if not body.endswith(ending):
            continue
        properties_text = body[: -len(ending)]
        rendered = properties_text.split(grammar["property_separator"])
        parsed = _parse_ordered_ambient_properties(
            rendered,
            order=grammar["property_order"],
            spec=selected,
            field="description",
        )
        matches.append((event_kind, parsed))
    if len(matches) != 1:
        raise AuthoringError("AMBIENT_DESCRIPTION_PARSE_AMBIGUOUS_OR_INVALID")
    event_kind, parsed_properties = matches[0]
    if parsed_properties == []:
        parsed_properties = {
            "timbre": None,
            "loudness": None,
            "temporal_pattern": None,
        }
    return _ambient_tuple_from_parsed_scalars(
        event_kind, parsed_properties
    )


def parse_ambient_query(
    text: Any,
    *,
    spec: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse only the exact frozen query grammar, never free-form NLP."""

    selected = AMBIENT_TEMPLATE_SPEC if spec is None else spec
    grammar = selected["query"]
    if not isinstance(text, str) or not text.startswith(grammar["prefix"]):
        raise AuthoringError("AMBIENT_QUERY_PARSE_GRAMMAR_MISMATCH")
    body = text[len(grammar["prefix"]) :]
    no_properties_suffix = grammar["event_no_properties_suffix"]
    with_properties_separator = grammar[
        "event_with_properties_separator"
    ]
    if body.endswith(no_properties_suffix):
        event_text = body[: -len(no_properties_suffix)]
        parsed = {
            "timbre": None,
            "loudness": None,
            "temporal_pattern": None,
        }
    elif body.endswith(grammar["suffix"]) and with_properties_separator in body:
        inner = body[: -len(grammar["suffix"])]
        event_text, properties_text = inner.split(
            with_properties_separator, 1
        )
        if not event_text or not properties_text:
            raise AuthoringError("AMBIENT_QUERY_PARSE_GRAMMAR_MISMATCH")
        parsed = _parse_ordered_ambient_properties(
            properties_text.split(grammar["property_separator"]),
            order=grammar["property_order"],
            spec=selected,
            field="query",
        )
    else:
        raise AuthoringError("AMBIENT_QUERY_PARSE_GRAMMAR_MISMATCH")
    event_kind = _ambient_event_kind_from_text(event_text, field="query")
    return _ambient_tuple_from_parsed_scalars(event_kind, parsed)


def _ambient_derivation_hashes_match_runtime_spec() -> None:
    current = ambient_derivation_hashes(AMBIENT_TEMPLATE_SPEC)
    if current["template_manifest"] != AMBIENT_TEMPLATE_MANIFEST:
        raise AuthoringError("AMBIENT_TEMPLATE_MANIFEST_IMPLEMENTATION_MISMATCH")
    if current["template_sha256"] != AMBIENT_TEMPLATE_SHA256:
        raise AuthoringError("AMBIENT_TEMPLATE_HASH_IMPLEMENTATION_MISMATCH")
    if current["generator_manifest"] != AMBIENT_GENERATOR_MANIFEST:
        raise AuthoringError(
            "AMBIENT_GENERATOR_MANIFEST_IMPLEMENTATION_MISMATCH"
        )
    if current["generator_sha256"] != AMBIENT_GENERATOR_SHA256:
        raise AuthoringError("AMBIENT_GENERATOR_HASH_IMPLEMENTATION_MISMATCH")


def derive_ambient_texts(value: Mapping[str, Any]) -> dict[str, Any]:
    """Mechanically derive two distinct texts from one validated tuple."""

    _ambient_derivation_hashes_match_runtime_spec()
    semantic = validate_ambient_semantic_tuple(value)
    description_grammar = AMBIENT_TEMPLATE_SPEC["description"]
    query_grammar = AMBIENT_TEMPLATE_SPEC["query"]
    event_text = STRUCTURED_AMBIENT_EVENT_TEXT[semantic["event_kind"]]
    description_modifiers = _ambient_rendered_properties(
        semantic,
        order=description_grammar["property_order"],
        spec=AMBIENT_TEMPLATE_SPEC,
    )
    query_modifiers = _ambient_rendered_properties(
        semantic,
        order=query_grammar["property_order"],
        spec=AMBIENT_TEMPLATE_SPEC,
    )
    description_prefix = (
        description_grammar["property_separator"].join(
            description_modifiers
        )
        + description_grammar["property_event_separator"]
        if description_modifiers
        else ""
    )
    ambient_description = (
        f"{description_grammar['prefix']}{description_prefix}{event_text}"
        f"{description_grammar['suffix']}"
    )
    if query_modifiers:
        ambient_query = (
            f"{query_grammar['prefix']}{event_text}"
            f"{query_grammar['event_with_properties_separator']}"
            f"{query_grammar['property_separator'].join(query_modifiers)}"
            f"{query_grammar['suffix']}"
        )
    else:
        ambient_query = (
            f"{query_grammar['prefix']}{event_text}"
            f"{query_grammar['event_no_properties_suffix']}"
        )
    if ambient_description == ambient_query:
        raise AuthoringError("AMBIENT_DERIVED_TEXT_IDENTITY")
    parsed_description = parse_ambient_description(ambient_description)
    parsed_query = parse_ambient_query(ambient_query)
    if parsed_description != semantic:
        raise AuthoringError(
            "AMBIENT_DESCRIPTION_PARSE_BACK_TUPLE_MISMATCH:"
            f"expected={semantic_hash(semantic)}:"
            f"observed={semantic_hash(parsed_description)}"
        )
    if parsed_query != semantic:
        raise AuthoringError(
            "AMBIENT_QUERY_PARSE_BACK_TUPLE_MISMATCH:"
            f"expected={semantic_hash(semantic)}:"
            f"observed={semantic_hash(parsed_query)}"
        )
    if parsed_description != parsed_query:
        raise AuthoringError("AMBIENT_DERIVED_PARSE_BACK_DISAGREEMENT")
    expected_atoms = ambient_semantic_content_atoms(semantic)
    description_atoms = ambient_semantic_content_atoms(parsed_description)
    query_atoms = ambient_semantic_content_atoms(parsed_query)
    if (
        description_atoms != expected_atoms
        or query_atoms != expected_atoms
    ):
        raise AuthoringError("AMBIENT_DERIVED_CONTENT_ATOM_MISMATCH")
    forbidden_assertions = {
        "metal object",
        "paper",
        "person",
        "button",
        "opening",
        "closing",
        "left",
        "right",
        "nearby",
        "behind",
        "ahead",
    }
    joined = f"{ambient_description} {ambient_query}".casefold()
    if any(term in joined for term in forbidden_assertions):
        raise AuthoringError("AMBIENT_DERIVED_FACTUAL_ASSERTION_FORBIDDEN")
    return {
        "ambient_description": ambient_description,
        "ambient_query": ambient_query,
        "content_atoms": list(expected_atoms),
        "description_parse_back": parsed_description,
        "query_parse_back": parsed_query,
    }


def _accepted_ambient_factor(
    semantic_value: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_static_ambient_contract()
    semantic = validate_ambient_semantic_tuple(semantic_value)
    derived = derive_ambient_texts(semantic)
    return {
        "ambient_semantics": semantic,
        "ambient_description": derived["ambient_description"],
        "ambient_query": derived["ambient_query"],
        "ambient_semantic_tuple_sha256": semantic_hash(semantic),
        "ambient_description_sha256": semantic_hash(
            derived["ambient_description"]
        ),
        "ambient_query_sha256": semantic_hash(derived["ambient_query"]),
        "ambient_derived_text_sha256": semantic_hash(
            {
                "ambient_description": derived["ambient_description"],
                "ambient_query": derived["ambient_query"],
            }
        ),
        "ambient_registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "ambient_generator_sha256": AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": AMBIENT_TEMPLATE_SHA256,
        "ambient_constraint_kind": AMBIENT_CONSTRAINT_KIND,
        "ambient_constraint_manifest": json.loads(
            canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
        ),
        "ambient_constraint_manifest_sha256": (
            AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "ambient_constraint_leaf_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_constraint_reachable_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
    }


def validate_ambient_derived_pair_parse_back(
    semantic_value: Mapping[str, Any],
    ambient_description: Any,
    ambient_query: Any,
    *,
    error_prefix: str = "AMBIENT_DERIVED",
) -> dict[str, Any]:
    """Independently parse both real strings back to the canonical tuple."""

    semantic = validate_ambient_semantic_tuple(semantic_value)
    try:
        description_semantic = parse_ambient_description(
            ambient_description
        )
    except AuthoringError as exc:
        raise AuthoringError(
            f"{error_prefix}_DESCRIPTION_PARSE_BACK_FAILED:{exc}"
        ) from exc
    try:
        query_semantic = parse_ambient_query(ambient_query)
    except AuthoringError as exc:
        raise AuthoringError(
            f"{error_prefix}_QUERY_PARSE_BACK_FAILED:{exc}"
        ) from exc
    if description_semantic != semantic:
        raise AuthoringError(
            f"{error_prefix}_DESCRIPTION_PARSE_BACK_TUPLE_MISMATCH:"
            f"expected={semantic_hash(semantic)}:"
            f"observed={semantic_hash(description_semantic)}"
        )
    if query_semantic != semantic:
        raise AuthoringError(
            f"{error_prefix}_QUERY_PARSE_BACK_TUPLE_MISMATCH:"
            f"expected={semantic_hash(semantic)}:"
            f"observed={semantic_hash(query_semantic)}"
        )
    if description_semantic != query_semantic:
        raise AuthoringError(
            f"{error_prefix}_INDEPENDENT_PARSE_BACK_DISAGREEMENT"
        )
    return semantic


def validate_ambient_factor_output(value: Any) -> dict[str, Any]:
    """Cross the raw-model-tuple boundary into one accepted ambient factor."""

    semantic = validate_ambient_semantic_tuple(value)
    accepted = _accepted_ambient_factor(semantic)
    for field in ("ambient_description", "ambient_query"):
        text = accepted[field]
        _validate_component_semantic_language(text, field=field)
        acoustic_context = _acoustic_context_evidence(text)
        if acoustic_context["rejected_ambiguous"]:
            raise AuthoringError(
                f"MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID:{field}"
            )
        if not acoustic_context["concepts"]:
            raise AuthoringError(
                f"MODEL_AMBIENT_SPECIFIC_ACOUSTIC_EVENT_REQUIRED:{field}"
            )
        vocalization = _human_vocalization_policy(text)
        if vocalization["lexical_speech_terms"]:
            raise AuthoringError(
                f"MODEL_AMBIENT_LEXICAL_SPEECH_FORBIDDEN:{field}"
            )
    return accepted


def validate_accepted_ambient_factor(value: Any) -> dict[str, Any]:
    """Validate an already accepted ambient factor without re-reading it raw."""

    if not isinstance(value, Mapping) or set(value) != AMBIENT_ACCEPTED_FIELDS:
        raise AuthoringError("ACCEPTED_AMBIENT_FACTOR_FIELD_SET_MISMATCH")
    validate_ambient_derived_pair_parse_back(
        value["ambient_semantics"],
        value["ambient_description"],
        value["ambient_query"],
        error_prefix="ACCEPTED_AMBIENT",
    )
    expected = _accepted_ambient_factor(value["ambient_semantics"])
    if dict(value) != expected:
        raise AuthoringError("ACCEPTED_AMBIENT_DERIVATION_MISMATCH")
    return expected


def _legacy_ambient_text_factor(
    description: str, query: str
) -> dict[str, str]:
    """Retained for historical R9-R15 tests; never a model semantic entry."""

    parsed = {
        "ambient_description": _strict_text(
            description,
            "ambient_description",
            max_words=60,
            min_words=2,
        ),
        "ambient_query": _strict_text(
            query,
            "ambient_query",
            max_words=40,
            min_words=2,
        ),
    }
    identity = _factor_pair_identity(
        parsed["ambient_description"], parsed["ambient_query"]
    )
    if identity["normalized_equal"] or identity["token_sets_equal"]:
        raise AuthoringError("MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY")
    def validate_text(field: str, text: str) -> None:
        _validate_component_semantic_language(text, field=field)
        acoustic_context = _acoustic_context_evidence(text)
        if acoustic_context["rejected_ambiguous"]:
            raise AuthoringError(
                f"MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID:{field}"
            )
        if not acoustic_context["concepts"]:
            raise AuthoringError(
                f"MODEL_AMBIENT_SPECIFIC_ACOUSTIC_EVENT_REQUIRED:{field}"
            )
        vocalization = _human_vocalization_policy(text)
        if vocalization["lexical_speech_terms"]:
            raise AuthoringError(
                f"MODEL_AMBIENT_LEXICAL_SPEECH_FORBIDDEN:{field}"
            )

    validate_text("ambient_description", parsed["ambient_description"])
    _validate_paired_factor_semantics(
        parsed["ambient_description"],
        parsed["ambient_query"],
        factor_kind="ambient",
    )
    validate_text("ambient_query", parsed["ambient_query"])
    return parsed


def validate_legacy_ambient_factor_output(value: Any) -> dict[str, str]:
    """Public historical-test helper; never used by R16 authoring."""

    if not isinstance(value, Mapping) or set(value) != {
        "ambient_description",
        "ambient_query",
    }:
        raise AuthoringError("LEGACY_AMBIENT_FACTOR_FIELD_SET_MISMATCH")
    return _legacy_ambient_text_factor(
        value["ambient_description"], value["ambient_query"]
    )


def validate_legacy_component_factor_output(
    value: Any,
) -> dict[str, str]:
    """Historical natural-language component helper, excluded from R16."""

    legacy_fields = {
        *VISUAL_OUTPUT_SCHEMA,
        "ambient_description",
        "ambient_query",
    }
    if not isinstance(value, Mapping) or set(value) != legacy_fields:
        raise AuthoringError("LEGACY_COMPONENT_FACTOR_FIELD_SET_MISMATCH")
    return {
        **validate_visual_factor_output(
            {key: value[key] for key in VISUAL_OUTPUT_SCHEMA}
        ),
        **validate_legacy_ambient_factor_output(
            {
                "ambient_description": value["ambient_description"],
                "ambient_query": value["ambient_query"],
            }
        ),
    }


def _parsed_output_binding_hash(
    factor_kind: str, parsed: Mapping[str, Any]
) -> str:
    """Bind raw ambient attempts to the model-authored tuple, not derived text."""

    if factor_kind == "ambient":
        accepted = validate_accepted_ambient_factor(parsed)
        return semantic_hash(accepted["ambient_semantics"])
    return semantic_hash(parsed)


def _validate_attempt_constraint_binding(
    attempt: Mapping[str, Any],
    *,
    trusted_context: Mapping[str, Any] | None = None,
) -> None:
    """Bind every attempt to the decoder constraint appropriate to its kind."""

    constraint_fields = {
        "constraint_kind",
        "constraint_manifest",
        "constraint_manifest_sha256",
        "constraint_trie_sha256",
        "constraint_tokenizer_fingerprint_sha256",
        "constraint_leaf_count",
        "constraint_reachable_count",
        "constraint_stop_token_ids",
        "constraint_assistant_prefill",
    }
    if {
        key for key in attempt if key.startswith("constraint_")
    } != constraint_fields:
        raise AuthoringError("ATTEMPT_CONSTRAINT_FIELD_SET_INVALID")
    factor_kind = attempt.get("factor_kind")
    context = (
        trusted_ambient_constraint_context()
        if trusted_context is None
        else trusted_context
    )
    if factor_kind == "ambient":
        expected = context["attempt_constraint"]
        if any(attempt.get(key) != value for key, value in expected.items()):
            raise AuthoringError("AMBIENT_ATTEMPT_CONSTRAINT_BINDING_INVALID")
        if attempt.get("attempt_kind") == "schema_only_repair":
            raise AuthoringError("AMBIENT_SCHEMA_REPAIR_ATTEMPT_FORBIDDEN")
    elif factor_kind in {"visual", "family_composition"}:
        expected = context["json_boundary_constraint"]
        if any(attempt.get(key) != value for key, value in expected.items()):
            raise AuthoringError(
                "NON_AMBIENT_ATTEMPT_CONSTRAINT_BINDING_INVALID"
            )
    else:
        raise AuthoringError("ATTEMPT_FACTOR_KIND_INVALID")


def structured_ambient_generator_self_audit() -> dict[str, Any]:
    """Exhaustively verify every allowed tuple and reject pair collisions."""

    _ambient_derivation_hashes_match_runtime_spec()
    pair_to_tuple: dict[tuple[str, str], str] = {}
    combination_count = 0
    for event_kind in STRUCTURED_AMBIENT_EVENT_KINDS:
        for timbre in STRUCTURED_AMBIENT_TIMBRES:
            for loudness in STRUCTURED_AMBIENT_LOUDNESS:
                for temporal_pattern in (
                    STRUCTURED_AMBIENT_TEMPORAL_PATTERNS
                ):
                    semantic = {
                        "event_kind": event_kind,
                        "acoustic_properties": {
                            "timbre": timbre,
                            "loudness": loudness,
                            "temporal_pattern": temporal_pattern,
                        },
                    }
                    accepted = _accepted_ambient_factor(semantic)
                    pair = (
                        accepted["ambient_description"],
                        accepted["ambient_query"],
                    )
                    try:
                        validate_ambient_derived_pair_parse_back(
                            semantic,
                            pair[0],
                            pair[1],
                            error_prefix=(
                                "AMBIENT_SELF_AUDIT:"
                                f"{event_kind}:{timbre}:"
                                f"{loudness}:{temporal_pattern}"
                            ),
                        )
                    except AuthoringError as exc:
                        raise AuthoringError(
                            "AMBIENT_SELF_AUDIT_PARSE_BACK_FAILED:"
                            f"tuple={semantic_hash(semantic)}:{exc}"
                        ) from exc
                    tuple_hash = accepted[
                        "ambient_semantic_tuple_sha256"
                    ]
                    prior = pair_to_tuple.setdefault(pair, tuple_hash)
                    if prior != tuple_hash:
                        raise AuthoringError(
                            "AMBIENT_SELF_AUDIT_PAIR_COLLISION:"
                            f"pair={semantic_hash(pair)}:"
                            f"first={prior}:second={tuple_hash}"
                        )
                    if (
                        validate_accepted_ambient_factor(accepted)
                        != accepted
                    ):
                        raise AuthoringError(
                            "AMBIENT_DERIVED_PAIR_ROUND_TRIP_FAILED"
                        )
                    combination_count += 1
    if combination_count != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS:
        raise AuthoringError(
            "AMBIENT_SELF_AUDIT_COMBINATION_COUNT_MISMATCH:"
            f"expected={EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS}:"
            f"observed={combination_count}"
        )
    unique_pair_count = len(pair_to_tuple)
    if unique_pair_count != EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS:
        raise AuthoringError(
            "AMBIENT_SELF_AUDIT_UNIQUE_PAIR_COUNT_MISMATCH:"
            f"expected={EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS}:"
            f"observed={unique_pair_count}"
        )
    return {
        "status": "PASS",
        "event_kind_count": len(STRUCTURED_AMBIENT_EVENT_KINDS),
        "combination_count": combination_count,
        "unique_pair_count": unique_pair_count,
        "independent_description_parse_back_count": combination_count,
        "independent_query_parse_back_count": combination_count,
        "registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "generator_sha256": AMBIENT_GENERATOR_SHA256,
        "template_sha256": AMBIENT_TEMPLATE_SHA256,
        "constraint_kind": AMBIENT_CONSTRAINT_KIND,
        "constraint_manifest": json.loads(
            canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
        ),
        "constraint_manifest_sha256": AMBIENT_CONSTRAINT_MANIFEST_SHA256,
        "constraint_leaf_count": EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS,
        "constraint_reachable_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
    }


def liquid_confusion_synthetic_suite() -> dict[str, Any]:
    """Audit the source-free liquid ontology without any clip identifiers."""

    expected = {
        "drip",
        "trickle",
        "continuous_liquid_flow",
        "slosh",
        "splash",
        "gurgle",
        "bubble",
    }
    if set(LIQUID_EVENT_BOUNDARIES) != expected:
        raise AuthoringError("LIQUID_CONFUSION_BOUNDARY_SET_MISMATCH")
    if "pour" in STRUCTURED_AMBIENT_EVENT_KINDS:
        raise AuthoringError("LIQUID_CONFUSION_BARE_POUR_BECAME_LEGAL")
    rows = []
    for event_kind in sorted(expected):
        semantic = {
            "event_kind": event_kind,
            "acoustic_properties": {
                "timbre": None,
                "loudness": None,
                "temporal_pattern": None,
            },
        }
        accepted = validate_ambient_factor_output(semantic)
        if (
            parse_ambient_description(accepted["ambient_description"])
            != semantic
            or parse_ambient_query(accepted["ambient_query"]) != semantic
        ):
            raise AuthoringError(
                f"LIQUID_CONFUSION_PARSE_BACK_FAILED:{event_kind}"
            )
        rows.append(
            {
                "event_kind": event_kind,
                "definition": LIQUID_EVENT_BOUNDARIES[event_kind],
                "ambient_description": accepted["ambient_description"],
                "ambient_query": accepted["ambient_query"],
            }
        )
    for forbidden in (
        "container",
        "cup",
        "bottle",
        "sink",
        "left",
        "right",
        "into",
        "from",
    ):
        continuous = next(
            row
            for row in rows
            if row["event_kind"] == "continuous_liquid_flow"
        )
        rendered = (
            continuous["ambient_description"]
            + " "
            + continuous["ambient_query"]
        ).casefold()
        if forbidden in rendered:
            raise AuthoringError(
                "LIQUID_CONFUSION_SOURCE_OR_DIRECTION_LEAK"
            )
    return {
        "status": "PASS",
        "clip_ids_used": False,
        "event_kind_count": len(rows),
        "rows": rows,
    }


def _validate_final_mechanical_semantic_language(
    text: str, *, field: str
) -> None:
    causal = _matching_patterns(text, UNSUPPORTED_CONTINUITY_PATTERNS[3:])
    if causal:
        raise AuthoringError(f"MECHANICAL_CAUSAL_LANGUAGE_FORBIDDEN:{field}")


def validate_component_factor_output(value: Any) -> dict[str, Any]:
    """Validate a complete accepted component or a historical legacy fixture."""

    if not isinstance(value, Mapping):
        raise AuthoringError("MODEL_OUTPUT_NOT_OBJECT")
    _forbidden_factor_structure(value)
    legacy_fields = {
        *VISUAL_OUTPUT_SCHEMA,
        "ambient_description",
        "ambient_query",
    }
    if set(value) == legacy_fields:
        return validate_legacy_component_factor_output(value)
    if set(value) != set(COMPONENT_OUTPUT_SCHEMA):
        raise AuthoringError("MODEL_COMPONENT_FACTOR_FIELD_SET_MISMATCH")
    return {
        **validate_visual_factor_output(
            {key: value[key] for key in VISUAL_OUTPUT_SCHEMA}
        ),
        **validate_accepted_ambient_factor(
            {key: value[key] for key in AMBIENT_ACCEPTED_FIELDS}
        ),
    }


def validate_accepted_component_factor(
    value: Any,
) -> dict[str, Any]:
    """Validate only the current accepted visual-plus-ambient component."""

    if not isinstance(value, Mapping):
        raise AuthoringError("ACCEPTED_COMPONENT_FACTOR_NOT_OBJECT")
    if set(value) != set(COMPONENT_OUTPUT_SCHEMA):
        raise AuthoringError("ACCEPTED_COMPONENT_FACTOR_FIELD_SET_MISMATCH")
    return {
        **validate_visual_factor_output(
            {key: value[key] for key in VISUAL_OUTPUT_SCHEMA}
        ),
        **validate_accepted_ambient_factor(
            {key: value[key] for key in AMBIENT_ACCEPTED_FIELDS}
        ),
    }


def accepted_component_model_projection(
    value: Any,
) -> dict[str, str]:
    """Expose only validated accepted natural-language fields to composition."""

    accepted = validate_accepted_component_factor(value)
    return {
        key: accepted[key]
        for key in (
            "visual_description",
            "visual_query",
            "ambient_description",
            "ambient_query",
        )
    }


def _component_validation_projection(
    component: Mapping[str, Any],
) -> dict[str, Any]:
    """Retain legacy fixture support while preserving current type boundaries."""

    legacy_fields = {
        *VISUAL_OUTPUT_SCHEMA,
        "ambient_description",
        "ambient_query",
    }
    if legacy_fields <= set(component) and "ambient_semantics" not in component:
        return {key: component[key] for key in legacy_fields}
    return {key: component[key] for key in COMPONENT_OUTPUT_SCHEMA}


def validate_composition_factor_output(
    value: Any,
    *,
    component_count: int | None = None,
    family_shape: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AuthoringError("MODEL_OUTPUT_NOT_OBJECT")
    _forbidden_factor_structure(value)
    if set(value) != set(COMPOSITION_OUTPUT_SCHEMA):
        raise AuthoringError("MODEL_COMPOSITION_FACTOR_FIELD_SET_MISMATCH")
    if component_count is None and family_shape is None:
        raise AuthoringError("COMPOSITION_FROZEN_SHAPE_BINDING_REQUIRED")
    if component_count is not None:
        if component_count not in {1, 2}:
            raise AuthoringError("COMPOSITION_COMPONENT_COUNT_MISMATCH")
        expected_shape = (
            "one_component"
            if component_count == 1
            else "two_component_ordered"
        )
        if family_shape is not None and family_shape != expected_shape:
            raise AuthoringError("COMPOSITION_FAMILY_SHAPE_MISMATCH")
        family_shape = expected_shape
    if family_shape not in RELATION_KIND_BY_SHAPE:
        raise AuthoringError("FAMILY_SHAPE_ENUM_INVALID")
    expected_relation_kind = RELATION_KIND_BY_SHAPE[family_shape]
    relation_kind = value["relation_kind"]
    if (
        not isinstance(relation_kind, str)
        or relation_kind != expected_relation_kind
    ):
        raise AuthoringError("COMPOSITION_RELATION_KIND_SHAPE_MISMATCH")
    return {"relation_kind": relation_kind}


def _mechanical_component_clauses(
    components: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    clauses = []
    for ordinal, component in enumerate(components, 1):
        parsed = validate_component_factor_output(
            _component_validation_projection(component)
        )
        clauses.append(
            {
                "ordinal": ordinal,
                "visual_summary": parsed["visual_description"],
                "ambient_summary": parsed["ambient_description"],
            }
        )
    if len(clauses) not in {1, 2}:
        raise AuthoringError("COMPOSITION_COMPONENT_COUNT_MISMATCH")
    return clauses


def _mechanical_composition_texts(
    components: Sequence[Mapping[str, Any]],
    composition_factor: Mapping[str, Any],
    *,
    family_shape: str | None = None,
) -> dict[str, Any]:
    parsed_components = [
        validate_component_factor_output(
            _component_validation_projection(component)
        )
        for component in components
    ]
    parsed = validate_composition_factor_output(
        composition_factor,
        component_count=len(parsed_components),
        family_shape=family_shape,
    )
    clauses = _mechanical_component_clauses(parsed_components)
    if parsed["relation_kind"] == "local_cooccurrence":
        component = parsed_components[0]
        relation_description = (
            f"Component 1: {component['visual_description']} "
            f"Accompanying local sound: {component['ambient_description']} "
            "The accepted observations co-occur locally within component 1."
        )
        relation_query = (
            f"Find one component matching {component['visual_query']} "
            f"together with {component['ambient_query']} as a local "
            "co-occurrence."
        )
    else:
        first, second = parsed_components
        relation_description = (
            f"Component 1: {first['visual_description']} "
            f"Accompanying local sound: {first['ambient_description']} "
            f"Component 2: {second['visual_description']} "
            f"Accompanying local sound: {second['ambient_description']} "
            "Frozen order: component 1 before component 2."
        )
        relation_query = (
            f"Find component 1 matching {first['visual_query']} with "
            f"{first['ambient_query']}; then find component 2 matching "
            f"{second['visual_query']} with {second['ambient_query']}; "
            "keep the frozen 1 to 2 order."
        )

    description_source = " ".join(
        str(component[field])
        for component in parsed_components
        for field in ("visual_description", "ambient_description")
    )
    query_source = " ".join(
        str(component[field])
        for component in parsed_components
        for field in ("visual_query", "ambient_query")
    )
    _validate_mechanical_family_text(
        relation_description,
        description_source,
        field="relation_description",
    )
    _validate_mechanical_family_text(
        relation_query,
        query_source,
        field="relation_query",
    )
    return {
        "component_clauses": clauses,
        "relation_description": relation_description,
        "relation_query": relation_query,
        "family_compositional_description": relation_description,
        "family_compositional_query": relation_query,
    }


def _validate_mechanical_family_text(
    text: str,
    component_source_text: str,
    *,
    field: str,
) -> None:
    """Allow only accepted component words plus the frozen template lexicon."""

    _validate_final_mechanical_semantic_language(text, field=field)
    source_words = set(_normalized_words(component_source_text))
    output_words = set(_normalized_words(text))
    unexpected = sorted(
        output_words - source_words - MECHANICAL_FAMILY_TEXT_TERMS
    )
    if unexpected:
        raise AuthoringError(
            f"MECHANICAL_FAMILY_TEXT_NEW_CONTENT:{field}:"
            + ",".join(unexpected)
        )


def validate_model_output(
    value: Any, *, component_count: int
) -> dict[str, Any]:
    """Reject the legacy combined family schema without retrying it."""

    if isinstance(value, Mapping) and "components" in value:
        components = value["components"]
        if not isinstance(components, list) or len(components) != component_count:
            raise AuthoringError("MODEL_COMPONENT_COUNT_MISMATCH")
        for index, row in enumerate(components, 1):
            if not isinstance(row, Mapping) or row.get("ordinal") != index:
                raise AuthoringError("MODEL_COMPONENT_ORDINAL_MISMATCH")
    raise AuthoringError("MODEL_LEGACY_COMBINED_OUTPUT_FORBIDDEN")


def assemble_family_factors(
    family: Mapping[str, Any],
    visual_factors: Sequence[Mapping[str, Any]],
    ambient_factors: Sequence[Mapping[str, Any]],
    composition_factor: Mapping[str, Any],
) -> dict[str, Any]:
    """Pair exact same-clip visual/ambient factors and assemble a family."""

    expected_count = len(family["intervals"])
    if (
        len(visual_factors) != expected_count
        or len(ambient_factors) != expected_count
    ):
        raise AuthoringError("ASSEMBLY_COMPONENT_COUNT_MISMATCH")
    components = [
        {
            "ordinal": ordinal,
            **validate_visual_factor_output(visual),
            **validate_accepted_ambient_factor(ambient),
        }
        for ordinal, (visual, ambient) in enumerate(
            zip(visual_factors, ambient_factors, strict=True), 1
        )
    ]
    validated_composition = validate_composition_factor_output(
        composition_factor,
        component_count=expected_count,
        family_shape=str(family["shape"]),
    )
    mechanical = _mechanical_composition_texts(
        components,
        validated_composition,
        family_shape=str(family["shape"]),
    )
    validate_component_local_composition(
        family,
        components,
        {
            **validated_composition,
            **mechanical,
        },
    )
    return {
        "components": components,
        "composition_factor": validated_composition,
        **validated_composition,
        **mechanical,
    }


def validate_component_local_composition(
    family: Mapping[str, Any],
    components: Sequence[Mapping[str, Any]],
    composition: Mapping[str, Any],
) -> dict[str, Any]:
    """Layer exact binding, description coverage, and local references."""

    clauses = composition.get("component_clauses")
    expected_clauses = _mechanical_component_clauses(components)
    if not isinstance(clauses, list) or len(clauses) != len(
        expected_clauses
    ):
        raise AuthoringError("BINDING_MISMATCH:component_clauses")
    results = []
    for ordinal, (component, clause, expected_clause) in enumerate(
        zip(components, clauses, expected_clauses, strict=True), 1
    ):
        if not isinstance(clause, Mapping):
            raise AuthoringError(f"BINDING_MISMATCH:{ordinal}:not_object")
        observed_keys = set(clause)
        expected_keys = set(expected_clause)
        visual_observed = _normalized_text(
            str(clause.get("visual_summary", ""))
        )
        visual_expected = _normalized_text(
            str(expected_clause["visual_summary"])
        )
        ambient_observed = _normalized_text(
            str(clause.get("ambient_summary", ""))
        )
        ambient_expected = _normalized_text(
            str(expected_clause["ambient_summary"])
        )
        binding = {
            "status": "PASS",
            "exact_key_set": observed_keys == expected_keys,
            "ordinal_equal": clause.get("ordinal") == ordinal,
            "visual_normalized_equal": visual_observed == visual_expected,
            "ambient_normalized_equal": ambient_observed == ambient_expected,
            "visual_hash_equal": (
                semantic_hash(visual_observed)
                == semantic_hash(visual_expected)
            ),
            "ambient_hash_equal": (
                semantic_hash(ambient_observed)
                == semantic_hash(ambient_expected)
            ),
            "expected_visual_sha256": semantic_hash(visual_expected),
            "observed_visual_sha256": semantic_hash(visual_observed),
            "expected_ambient_sha256": semantic_hash(ambient_expected),
            "observed_ambient_sha256": semantic_hash(ambient_observed),
        }
        if not all(
            binding[key]
            for key in (
                "exact_key_set",
                "ordinal_equal",
                "visual_normalized_equal",
                "ambient_normalized_equal",
                "visual_hash_equal",
                "ambient_hash_equal",
            )
        ):
            binding["status"] = "FAIL"
            raise AuthoringError(f"BINDING_MISMATCH:{ordinal}")
        visual = _visual_component_coverage(
            str(clause["visual_summary"]),
            str(component["visual_description"]),
        )
        ambient = _ambient_component_coverage(
            str(clause["ambient_summary"]),
            str(component["ambient_description"]),
        )
        coverage = {
            "status": (
                "PASS"
                if visual["covered"] and ambient["covered"]
                else "FAIL"
            ),
            "source_policy": "accepted_descriptions_only",
            "visual": visual,
            "ambient": ambient,
        }
        if coverage["status"] != "PASS":
            raise AuthoringError(f"COVERAGE_INVALID:{ordinal}")
        continuity = _component_local_continuity_evidence(
            " ".join(
                (
                    str(clause["visual_summary"]),
                    str(clause["ambient_summary"]),
                )
            )
        )
        local_reference = {
            "status": "FAIL" if continuity["unsupported"] else "PASS",
            "continuity": continuity,
        }
        if local_reference["status"] != "PASS":
            raise AuthoringError(f"LOCAL_REFERENCE_INVALID:{ordinal}")
        results.append(
            {
                "ordinal": ordinal,
                "binding": binding,
                "coverage": coverage,
                "local_reference": local_reference,
                "visual": visual,
                "ambient": ambient,
                "continuity": continuity,
            }
        )
    expected_mechanical = _mechanical_composition_texts(
        components,
        {"relation_kind": composition["relation_kind"]},
        family_shape=str(family["shape"]),
    )
    for field in (
        "relation_description",
        "relation_query",
        "family_compositional_description",
        "family_compositional_query",
    ):
        if composition.get(field) != expected_mechanical[field]:
            raise AuthoringError(
                f"COMPOSITION_MECHANICAL_TEXT_MISMATCH:{field}"
            )
    relation = " ".join(
        (
            str(expected_mechanical["relation_description"]),
            str(expected_mechanical["relation_query"]),
        )
    )
    if str(family["shape"]) == "one_component":
        relation_continuity = _component_local_continuity_evidence(relation)
    else:
        component_local_texts = [
            str(component[field])
            for component in components
            for field in (
                "visual_description",
                "ambient_description",
                "visual_query",
                "ambient_query",
            )
        ]
        relation_only = _relation_only_text(
            relation, component_local_texts
        )
        relation_continuity = _unsupported_continuity_evidence(
            relation_only,
            reject_agent_terms=False,
            reject_reused_entities=False,
        )
        relation_continuity["relation_only_text"] = relation_only
        relation_continuity["component_local_spans_removed"] = len(
            component_local_texts
        )
    if relation_continuity["unsupported"]:
        raise AuthoringError("COMPOSITION_RELATION_CONTINUITY_INVALID")
    validate_composition_factor_output(
        {"relation_kind": composition["relation_kind"]},
        component_count=len(components),
        family_shape=str(family["shape"]),
    )
    return {
        "status": "PASS",
        "component_clauses": results,
        "relation_continuity": relation_continuity,
    }


ACCEPTED_FACTOR_BINDING_FIELDS = (
    "factor_key",
    "family_key",
    "factor_kind",
    "component_ordinal",
    "clip_key",
    "media_modality",
    "video_sha256",
    "audio_sha256",
    "frozen_family_shape",
    "frozen_component_count",
    "relation_kind",
    "accepted_attempt_index",
    "accepted_attempt_kind",
    "raw_output_sha256",
    "parsed_output_sha256",
    "ambient_semantic_tuple_sha256",
    "ambient_description_sha256",
    "ambient_query_sha256",
    "ambient_derived_text_sha256",
    "ambient_registry_sha256",
    "ambient_generator_sha256",
    "ambient_template_sha256",
    "ambient_constraint_kind",
    "ambient_constraint_manifest",
    "ambient_constraint_manifest_sha256",
    "ambient_constraint_leaf_count",
    "ambient_constraint_reachable_count",
    "ambient_semantics",
    "ambient_description",
    "ambient_query",
)


def _parsed_factors_by_key(
    structural: Mapping[str, Any],
    parsed_by_family: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    factors = {}
    for family in structural["families"]:
        family_key = str(family["family_key"])
        parsed = parsed_by_family.get(family_key)
        if not isinstance(parsed, Mapping):
            raise AuthoringError(f"MISSING_PARSED_FAMILY:{family_key}")
        components = parsed.get("components")
        if not isinstance(components, list) or len(components) != len(
            family["intervals"]
        ):
            raise AuthoringError("PARSED_COMPONENT_COUNT_MISMATCH")
        for ordinal, component in enumerate(components, 1):
            if not isinstance(component, Mapping):
                raise AuthoringError("PARSED_COMPONENT_FACTOR_INVALID")
            factors[f"{family_key}:component:{ordinal}:visual"] = (
                validate_visual_factor_output(
                    {key: component[key] for key in VISUAL_OUTPUT_SCHEMA}
                )
            )
            factors[f"{family_key}:component:{ordinal}:ambient"] = (
                validate_accepted_ambient_factor(
                    {
                        key: component[key]
                        for key in AMBIENT_ACCEPTED_FIELDS
                    }
                )
            )
        factors[f"{family_key}:family_composition"] = (
            validate_composition_factor_output(
                {
                    key: parsed[key]
                    for key in COMPOSITION_OUTPUT_SCHEMA
                },
                component_count=len(family["intervals"]),
                family_shape=str(family["shape"]),
            )
        )
    return factors


def build_accepted_factor_manifest(
    structural: Mapping[str, Any],
    parsed_by_family: Mapping[str, Mapping[str, Any]],
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind every accepted factor to its exact successful raw attempt."""

    parsed_factors = _parsed_factors_by_key(structural, parsed_by_family)
    family_contracts = {
        str(family["family_key"]): {
            "frozen_family_shape": str(family["shape"]),
            "frozen_component_count": len(family["intervals"]),
        }
        for family in structural["families"]
    }
    attempts_by_factor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        factor_key = str(attempt.get("factor_key", ""))
        if factor_key not in parsed_factors:
            raise AuthoringError("ACCEPTED_FACTOR_ATTEMPT_KEY_UNEXPECTED")
        attempts_by_factor[factor_key].append(attempt)
    if set(attempts_by_factor) != set(parsed_factors):
        raise AuthoringError("ACCEPTED_FACTOR_ATTEMPT_SET_MISMATCH")

    rows = []
    for factor_key in sorted(parsed_factors):
        factor_attempts = attempts_by_factor[factor_key]
        if not 1 <= len(factor_attempts) <= 2:
            raise AuthoringError("ACCEPTED_FACTOR_ATTEMPT_COUNT_INVALID")
        ordered = sorted(
            factor_attempts, key=lambda row: int(row.get("attempt", -1))
        )
        if [row.get("attempt") for row in ordered] != list(
            range(1, len(ordered) + 1)
        ):
            raise AuthoringError("ACCEPTED_FACTOR_ATTEMPT_INDEX_INVALID")
        if ordered[0].get("attempt_kind") != "initial" or (
            len(ordered) == 2
            and ordered[1].get("attempt_kind") != "schema_only_repair"
        ):
            raise AuthoringError("ACCEPTED_FACTOR_ATTEMPT_KIND_INVALID")
        accepted = [
            row
            for row in ordered
            if isinstance(row.get("parsed_output_sha256"), str)
            and row.get("parser_error") is None
        ]
        if len(accepted) != 1 or accepted[0] is not ordered[-1]:
            raise AuthoringError("ACCEPTED_FACTOR_SUCCESS_ATTEMPT_INVALID")
        for constraint_attempt in ordered:
            _validate_attempt_constraint_binding(constraint_attempt)
        attempt = accepted[0]
        raw_output = attempt.get("raw_output")
        if not isinstance(raw_output, str):
            raise AuthoringError("ACCEPTED_FACTOR_RAW_OUTPUT_MISSING")
        observed_raw_hash = "sha256:" + hashlib.sha256(
            raw_output.encode("utf-8")
        ).hexdigest()
        if attempt.get("raw_output_sha256") != observed_raw_hash:
            raise AuthoringError("ACCEPTED_FACTOR_RAW_OUTPUT_HASH_MISMATCH")
        parsed_hash = _parsed_output_binding_hash(
            str(attempt.get("factor_kind")),
            parsed_factors[factor_key],
        )
        if attempt.get("parsed_output_sha256") != parsed_hash:
            raise AuthoringError("ACCEPTED_FACTOR_PARSED_OUTPUT_MISMATCH")
        row = {
            "factor_key": factor_key,
            "family_key": str(attempt.get("family_key")),
            "factor_kind": str(attempt.get("factor_kind")),
            "component_ordinal": attempt.get("component_ordinal"),
            "clip_key": (
                attempt.get("clip_keys", [None])[0]
                if len(attempt.get("clip_keys", [])) == 1
                else None
            ),
            "media_modality": attempt.get("media_modality"),
            "video_sha256": None,
            "audio_sha256": None,
            **family_contracts[str(attempt.get("family_key"))],
            "relation_kind": (
                parsed_factors[factor_key]["relation_kind"]
                if str(attempt.get("factor_kind")) == "family_composition"
                else None
            ),
            "accepted_attempt_index": int(attempt["attempt"]),
            "accepted_attempt_kind": str(attempt["attempt_kind"]),
            "raw_output_sha256": observed_raw_hash,
            "parsed_output_sha256": parsed_hash,
            "ambient_semantic_tuple_sha256": None,
            "ambient_description_sha256": None,
            "ambient_query_sha256": None,
            "ambient_derived_text_sha256": None,
            "ambient_registry_sha256": None,
            "ambient_generator_sha256": None,
            "ambient_template_sha256": None,
            "ambient_constraint_kind": None,
            "ambient_constraint_manifest": None,
            "ambient_constraint_manifest_sha256": None,
            "ambient_constraint_leaf_count": None,
            "ambient_constraint_reachable_count": None,
            "ambient_semantics": None,
            "ambient_description": None,
            "ambient_query": None,
        }
        expected_prefix = f"{row['family_key']}:"
        if not factor_key.startswith(expected_prefix):
            raise AuthoringError("ACCEPTED_FACTOR_FAMILY_KEY_MISMATCH")
        clip_hashes = attempt.get("clip_manifest_hashes")
        if not isinstance(clip_hashes, list):
            raise AuthoringError("ACCEPTED_FACTOR_CLIP_HASHES_INVALID")
        if row["factor_kind"] in {"visual", "ambient"}:
            if len(clip_hashes) != 1:
                raise AuthoringError("ACCEPTED_FACTOR_CLIP_BINDING_INVALID")
            clip_hash = clip_hashes[0]
            if (
                not isinstance(clip_hash, Mapping)
                or clip_hash.get("clip_key") != row["clip_key"]
            ):
                raise AuthoringError("ACCEPTED_FACTOR_CLIP_BINDING_INVALID")
        if row["factor_kind"] == "visual":
            expected_key = (
                f"{row['family_key']}:component:"
                f"{row['component_ordinal']}:visual"
            )
            row["video_sha256"] = clip_hashes[0].get("video_sha256")
            if (
                row["media_modality"] != "visual"
                or not isinstance(row["video_sha256"], str)
                or "audio_sha256" in clip_hashes[0]
            ):
                raise AuthoringError(
                    "ACCEPTED_VISUAL_MEDIA_BINDING_INVALID"
                )
        elif row["factor_kind"] == "ambient":
            expected_key = (
                f"{row['family_key']}:component:"
                f"{row['component_ordinal']}:ambient"
            )
            row["audio_sha256"] = clip_hashes[0].get("audio_sha256")
            if (
                row["media_modality"] != "ambient"
                or not isinstance(row["audio_sha256"], str)
                or "video_sha256" in clip_hashes[0]
            ):
                raise AuthoringError(
                    "ACCEPTED_AMBIENT_MEDIA_BINDING_INVALID"
                )
            ambient = parsed_factors[factor_key]
            for key in (
                "ambient_semantic_tuple_sha256",
                "ambient_description_sha256",
                "ambient_query_sha256",
                "ambient_derived_text_sha256",
                "ambient_registry_sha256",
                "ambient_generator_sha256",
                "ambient_template_sha256",
                "ambient_constraint_kind",
                "ambient_constraint_manifest",
                "ambient_constraint_manifest_sha256",
                "ambient_constraint_leaf_count",
                "ambient_constraint_reachable_count",
            ):
                row[key] = ambient[key]
            row["ambient_semantics"] = ambient["ambient_semantics"]
            row["ambient_description"] = ambient["ambient_description"]
            row["ambient_query"] = ambient["ambient_query"]
        elif row["factor_kind"] == "family_composition":
            expected_key = f"{row['family_key']}:family_composition"
            if (
                row["component_ordinal"] is not None
                or row["clip_key"] is not None
                or row["media_modality"] is not None
                or clip_hashes
            ):
                raise AuthoringError(
                    "ACCEPTED_COMPOSITION_MEDIA_OR_ORDINAL_INVALID"
                )
        else:
            raise AuthoringError("ACCEPTED_FACTOR_KIND_INVALID")
        if factor_key != expected_key:
            raise AuthoringError("ACCEPTED_FACTOR_BINDING_MISMATCH")
        if (
            row["frozen_family_shape"] not in RELATION_KIND_BY_SHAPE
            or row["frozen_component_count"]
            != (
                1
                if row["frozen_family_shape"] == "one_component"
                else 2
            )
            or (
                row["factor_kind"] == "family_composition"
                and row["relation_kind"]
                != RELATION_KIND_BY_SHAPE[row["frozen_family_shape"]]
            )
            or (
                row["factor_kind"] in {"visual", "ambient"}
                and row["relation_kind"] is not None
            )
        ):
            raise AuthoringError("ACCEPTED_FACTOR_FROZEN_SHAPE_BINDING_INVALID")
        rows.append(row)
    manifest = {
        "schema_version": (
            ACCEPTED_FACTOR_MANIFEST_SCHEMA_VERSION
        ),
        "pipeline_id": PIPELINE_ID,
        "ambient_constraint": ambient_constraint_contract(),
        "accepted_factor_count": len(rows),
        "visual_factor_count": sum(
            row["factor_kind"] == "visual" for row in rows
        ),
        "ambient_factor_count": sum(
            row["factor_kind"] == "ambient" for row in rows
        ),
        "composition_factor_count": sum(
            row["factor_kind"] == "family_composition" for row in rows
        ),
        "factors": rows,
        "cross_factor_fill_or_substitution_permitted": False,
    }
    manifest["manifest_payload_sha256"] = semantic_hash(manifest)
    return manifest


def _factor_bindings_by_key(
    accepted_factor_manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if (
        accepted_factor_manifest.get("schema_version")
        != ACCEPTED_FACTOR_MANIFEST_SCHEMA_VERSION
        or accepted_factor_manifest.get("ambient_constraint")
        != ambient_constraint_contract()
    ):
        raise AuthoringError("ACCEPTED_FACTOR_MANIFEST_R20_CONTRACT_INVALID")
    observed_hash = accepted_factor_manifest.get("manifest_payload_sha256")
    body = {
        key: value
        for key, value in accepted_factor_manifest.items()
        if key != "manifest_payload_sha256"
    }
    if observed_hash != semantic_hash(body):
        raise AuthoringError("ACCEPTED_FACTOR_MANIFEST_HASH_MISMATCH")
    factors = accepted_factor_manifest.get("factors")
    if not isinstance(factors, list):
        raise AuthoringError("ACCEPTED_FACTOR_MANIFEST_ROWS_INVALID")
    bindings: dict[str, dict[str, Any]] = {}
    for value in factors:
        if not isinstance(value, Mapping) or set(value) != set(
            ACCEPTED_FACTOR_BINDING_FIELDS
        ):
            raise AuthoringError("ACCEPTED_FACTOR_MANIFEST_ROW_INVALID")
        row = dict(value)
        factor_key = row["factor_key"]
        if not isinstance(factor_key, str) or factor_key in bindings:
            raise AuthoringError("ACCEPTED_FACTOR_MANIFEST_KEY_INVALID")
        ambient_hash_fields = (
            "ambient_semantic_tuple_sha256",
            "ambient_description_sha256",
            "ambient_query_sha256",
            "ambient_derived_text_sha256",
            "ambient_registry_sha256",
            "ambient_generator_sha256",
            "ambient_template_sha256",
            "ambient_constraint_manifest_sha256",
        )
        ambient_constraint_fields = (
            "ambient_constraint_kind",
            "ambient_constraint_leaf_count",
            "ambient_constraint_reachable_count",
        )
        if row["factor_kind"] == "ambient":
            if (
                not all(isinstance(row[key], str) for key in ambient_hash_fields)
                or row["ambient_registry_sha256"]
                != STRUCTURED_AMBIENT_REGISTRY_SHA256
                or row["ambient_generator_sha256"]
                != AMBIENT_GENERATOR_SHA256
                or row["ambient_template_sha256"]
                != AMBIENT_TEMPLATE_SHA256
                or row["ambient_constraint_kind"]
                != AMBIENT_CONSTRAINT_KIND
                or row["ambient_constraint_manifest"]
                != AMBIENT_CONSTRAINT_MANIFEST
                or row["ambient_constraint_manifest_sha256"]
                != AMBIENT_CONSTRAINT_MANIFEST_SHA256
                or row["ambient_constraint_leaf_count"]
                != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
                or row["ambient_constraint_reachable_count"]
                != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            ):
                raise AuthoringError(
                    "ACCEPTED_AMBIENT_DERIVATION_HASH_BINDING_INVALID"
                )
            expected = validate_accepted_ambient_factor(
                {
                    key: row[key]
                    for key in AMBIENT_ACCEPTED_FIELDS
                }
            )
            for key in AMBIENT_BINDING_PAYLOAD_FIELDS:
                if row[key] != expected[key]:
                    raise AuthoringError(
                        f"ACCEPTED_AMBIENT_PAYLOAD_BINDING_INVALID:{key}"
                    )
        elif any(
            row[key] is not None
            for key in (
                *ambient_hash_fields,
                *ambient_constraint_fields,
                "ambient_semantics",
                "ambient_description",
                "ambient_query",
            )
        ):
            raise AuthoringError(
                "ACCEPTED_NON_AMBIENT_DERIVATION_HASH_PRESENT"
            )
        bindings[factor_key] = row
    if (
        accepted_factor_manifest.get("accepted_factor_count")
        != len(bindings)
        or accepted_factor_manifest.get("visual_factor_count")
        != sum(
            row["factor_kind"] == "visual" for row in bindings.values()
        )
        or accepted_factor_manifest.get("ambient_factor_count")
        != sum(
            row["factor_kind"] == "ambient" for row in bindings.values()
        )
        or accepted_factor_manifest.get("composition_factor_count")
        != sum(
            row["factor_kind"] == "family_composition"
            for row in bindings.values()
        )
    ):
        raise AuthoringError("ACCEPTED_FACTOR_MANIFEST_COUNT_MISMATCH")
    return bindings


def _structural_from_sealed_contract(
    contract: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    prompt_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the minimal structural scope from independently sealed inputs."""

    targets = target_manifest.get("targets")
    visual_prompts = prompt_manifest.get("visual_prompts")
    ambient_prompts = prompt_manifest.get("ambient_prompts")
    contracts = prompt_manifest.get("composition_contracts")
    if (
        not isinstance(targets, list)
        or not isinstance(visual_prompts, list)
        or not isinstance(ambient_prompts, list)
        or not isinstance(contracts, list)
    ):
        raise AuthoringError("SEALED_STRUCTURAL_INPUT_INVALID")
    target_by_key = {
        str(row["clip_key"]): row
        for row in targets
        if isinstance(row, Mapping) and isinstance(row.get("clip_key"), str)
    }
    family_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in visual_prompts:
        if not isinstance(row, Mapping):
            raise AuthoringError("SEALED_PROMPT_ROW_INVALID")
        family_rows[str(row.get("family_key"))].append(row)
    visual_keys = {
        (
            str(row.get("family_key")),
            row.get("component_ordinal"),
            tuple(row.get("media_component_clip_keys", [])),
        )
        for row in visual_prompts
        if isinstance(row, Mapping)
    }
    ambient_keys = {
        (
            str(row.get("family_key")),
            row.get("component_ordinal"),
            tuple(row.get("media_component_clip_keys", [])),
        )
        for row in ambient_prompts
        if isinstance(row, Mapping)
    }
    if visual_keys != ambient_keys:
        raise AuthoringError("SEALED_MODALITY_FACTOR_PAIR_MISMATCH")
    shapes = {
        str(row.get("family_key")): str(row.get("family_shape"))
        for row in contracts
        if isinstance(row, Mapping)
    }
    families = []
    for family_key, rows in sorted(family_rows.items()):
        rows = sorted(rows, key=lambda row: int(row["component_ordinal"]))
        if [row["component_ordinal"] for row in rows] != list(
            range(1, len(rows) + 1)
        ):
            raise AuthoringError("SEALED_COMPONENT_ORDINAL_INVALID")
        intervals = []
        for row in rows:
            clip_keys = row.get("media_component_clip_keys")
            if not isinstance(clip_keys, list) or len(clip_keys) != 1:
                raise AuthoringError("SEALED_COMPONENT_CLIP_BINDING_INVALID")
            clip_key = str(clip_keys[0])
            target = target_by_key.get(clip_key)
            if target is None:
                raise AuthoringError("SEALED_COMPONENT_TARGET_MISSING")
            intervals.append(
                {
                    "clip_key": clip_key,
                    "start_us": target.get("start_us"),
                    "end_us": target.get("end_us"),
                }
            )
        families.append(
            {
                "family_key": family_key,
                "shape": shapes.get(family_key),
                "slot_names": [],
                "intervals": intervals,
            }
        )
    counts = contract.get("counts")
    if not isinstance(counts, Mapping):
        counts = {
            "families": len(families),
            "target_clips": len(targets),
            "queries": len(targets) * 2 + len(families),
        }
    return {
        "families": families,
        "targets": targets,
        "counts": dict(counts),
    }


def validate_accepted_factor_provenance(
    accepted_factor_manifest: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
    *,
    structural: Mapping[str, Any] | None = None,
    prompt_manifest: Mapping[str, Any] | None = None,
    trusted_constraint_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-derive accepted factors and verify every final row's exact binding."""

    bindings = _factor_bindings_by_key(accepted_factor_manifest)
    expected_specs = None
    if structural is not None or prompt_manifest is not None:
        if structural is None or prompt_manifest is None:
            raise AuthoringError("PROVENANCE_EXPECTED_SCOPE_INCOMPLETE")
        expected_specs = derive_expected_factor_specs(
            structural, prompt_manifest
        )
        if set(bindings) != set(expected_specs):
            raise AuthoringError("PROVENANCE_EXPECTED_FACTOR_SET_MISMATCH")
        for factor_key, expected in expected_specs.items():
            for key in (
                "family_key",
                "factor_kind",
                "component_ordinal",
            ):
                if bindings[factor_key][key] != expected[key]:
                    raise AuthoringError(
                        f"PROVENANCE_EXPECTED_BINDING_MISMATCH:{key}"
                    )
            if (
                bindings[factor_key]["frozen_family_shape"]
                != expected["family_shape"]
                or bindings[factor_key]["frozen_component_count"]
                != expected["component_count"]
            ):
                raise AuthoringError(
                    "PROVENANCE_EXPECTED_FROZEN_SHAPE_BINDING_MISMATCH"
                )
            if bindings[factor_key]["clip_key"] != expected["clip_key"]:
                raise AuthoringError(
                    "PROVENANCE_EXPECTED_CLIP_BINDING_MISMATCH"
                )
            if (
                bindings[factor_key]["media_modality"]
                != expected.get("media_modality")
            ):
                raise AuthoringError(
                    "PROVENANCE_EXPECTED_MODALITY_BINDING_MISMATCH"
                )
    attempts_by_factor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        factor_key = attempt.get("factor_key")
        if not isinstance(factor_key, str) or factor_key not in bindings:
            raise AuthoringError("PROVENANCE_ATTEMPT_FACTOR_UNEXPECTED")
        _validate_attempt_constraint_binding(
            attempt,
            trusted_context=trusted_constraint_context,
        )
        attempts_by_factor[factor_key].append(attempt)
    if set(attempts_by_factor) != set(bindings):
        raise AuthoringError("PROVENANCE_ATTEMPT_FACTOR_SET_MISMATCH")

    parsed_by_factor: dict[str, dict[str, Any]] = {}
    for factor_key, binding in bindings.items():
        factor_attempts = attempts_by_factor[factor_key]
        if not 1 <= len(factor_attempts) <= 2:
            raise AuthoringError("PROVENANCE_ATTEMPT_COUNT_INVALID")
        if [row.get("attempt") for row in factor_attempts] != list(
            range(1, len(factor_attempts) + 1)
        ):
            raise AuthoringError("PROVENANCE_ATTEMPT_ORDER_INVALID")
        if factor_attempts[0].get("attempt_kind") != "initial":
            raise AuthoringError("PROVENANCE_INITIAL_ATTEMPT_MISSING")
        if len(factor_attempts) == 2:
            initial, repair = factor_attempts
            if repair.get("attempt_kind") != "schema_only_repair":
                raise AuthoringError("PROVENANCE_REPAIR_KIND_INVALID")
            if initial.get("parser_error") is None:
                raise AuthoringError("PROVENANCE_REPAIR_AFTER_SUCCESS")
            if initial.get("schema_only_repair_eligible") is not True:
                raise AuthoringError("PROVENANCE_REPAIR_NOT_ELIGIBLE")
            if repair.get("prior_parser_error") != initial.get("parser_error"):
                raise AuthoringError("PROVENANCE_REPAIR_ERROR_MISMATCH")
            if repair.get("schema_only_repair") is not True:
                raise AuthoringError("PROVENANCE_REPAIR_FLAG_INVALID")
            candidate = _schema_repair_candidate(
                str(initial.get("raw_output", "")),
                str(initial.get("parser_error", "")),
                semantic_fields=(
                    frozenset(VISUAL_OUTPUT_SCHEMA)
                    if binding["factor_kind"] == "visual"
                    else (
                        AMBIENT_SEMANTIC_SCALAR_FIELDS
                        if binding["factor_kind"] == "ambient"
                        else frozenset(COMPOSITION_OUTPUT_SCHEMA)
                    )
                ),
            )
            if candidate is None:
                raise AuthoringError("PROVENANCE_REPAIR_SEMANTICS_INVALID")
            repair_value = _strict_json_output(
                str(repair.get("raw_output", ""))
            )
            if _semantic_scalar_multiset(
                candidate
            ) != _semantic_scalar_multiset(repair_value):
                raise AuthoringError("PROVENANCE_REPAIR_CHANGED_SEMANTICS")
            if repair.get("content_preserving_guard_passed") is not True:
                raise AuthoringError("PROVENANCE_REPAIR_GUARD_INVALID")
        successful = [
            attempt
            for attempt in factor_attempts
            if isinstance(attempt.get("parsed_output_sha256"), str)
            and attempt.get("parser_error") is None
        ]
        if len(successful) != 1 or successful[0] is not factor_attempts[-1]:
            raise AuthoringError("PROVENANCE_SUCCESS_CARDINALITY_INVALID")
        matching = [
            attempt
            for attempt in factor_attempts
            if attempt.get("attempt")
            == binding["accepted_attempt_index"]
            and attempt.get("attempt_kind")
            == binding["accepted_attempt_kind"]
        ]
        if len(matching) != 1:
            raise AuthoringError("PROVENANCE_ACCEPTED_ATTEMPT_MISSING")
        attempt = matching[0]
        for key in (
            "factor_key",
            "family_key",
            "factor_kind",
            "component_ordinal",
            "raw_output_sha256",
            "parsed_output_sha256",
        ):
            if attempt.get(key) != binding[key]:
                raise AuthoringError(
                    f"PROVENANCE_ACCEPTED_ATTEMPT_MISMATCH:{key}"
                )
        if binding["factor_kind"] in {"visual", "ambient"}:
            if (
                attempt.get("media_modality")
                != binding["media_modality"]
                or attempt.get("clip_keys") != [binding["clip_key"]]
            ):
                raise AuthoringError(
                    "PROVENANCE_ATTEMPT_MEDIA_BINDING_MISMATCH"
                )
            clip_hashes = attempt.get("clip_manifest_hashes")
            expected_hashes = [
                {
                    "clip_key": binding["clip_key"],
                    "start_us": clip_hashes[0].get("start_us")
                    if isinstance(clip_hashes, list) and clip_hashes
                    else None,
                    "end_us": clip_hashes[0].get("end_us")
                    if isinstance(clip_hashes, list) and clip_hashes
                    else None,
                    "duration_us": clip_hashes[0].get("duration_us")
                    if isinstance(clip_hashes, list) and clip_hashes
                    else None,
                    (
                        "video_sha256"
                        if binding["factor_kind"] == "visual"
                        else "audio_sha256"
                    ): (
                        binding["video_sha256"]
                        if binding["factor_kind"] == "visual"
                        else binding["audio_sha256"]
                    ),
                }
            ]
            if clip_hashes != expected_hashes:
                raise AuthoringError(
                    "PROVENANCE_ATTEMPT_MEDIA_HASH_MISMATCH"
                )
        elif (
            attempt.get("media_modality") is not None
            or attempt.get("clip_keys") != []
            or attempt.get("clip_manifest_hashes") != []
        ):
            raise AuthoringError("PROVENANCE_COMPOSITION_MEDIA_PRESENT")
        raw = attempt.get("raw_output")
        if not isinstance(raw, str):
            raise AuthoringError("PROVENANCE_RAW_OUTPUT_MISSING")
        if (
            "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
            != binding["raw_output_sha256"]
        ):
            raise AuthoringError("PROVENANCE_RAW_OUTPUT_TAMPERED")
        value = _strict_json_output(raw)
        if binding["factor_kind"] == "visual":
            parsed = validate_visual_factor_output(value)
        elif binding["factor_kind"] == "ambient":
            parsed_raw = validate_ambient_factor_output(value)
            parsed = validate_accepted_ambient_factor(
                {
                    key: binding[key]
                    for key in AMBIENT_ACCEPTED_FIELDS
                }
            )
            if parsed_raw != parsed:
                raise AuthoringError(
                    "PROVENANCE_AMBIENT_RAW_ACCEPTED_MISMATCH"
                )
            for key in (
                "ambient_semantic_tuple_sha256",
                "ambient_description_sha256",
                "ambient_query_sha256",
                "ambient_derived_text_sha256",
                "ambient_registry_sha256",
                "ambient_generator_sha256",
                "ambient_template_sha256",
                "ambient_constraint_kind",
                "ambient_constraint_manifest",
                "ambient_constraint_manifest_sha256",
                "ambient_constraint_leaf_count",
                "ambient_constraint_reachable_count",
            ):
                if binding[key] != parsed_raw[key]:
                    raise AuthoringError(
                        f"PROVENANCE_AMBIENT_HASH_BINDING_MISMATCH:{key}"
                    )
        else:
            parsed = validate_composition_factor_output(
                value,
                component_count=int(binding["frozen_component_count"]),
                family_shape=str(binding["frozen_family_shape"]),
            )
            if parsed["relation_kind"] != binding["relation_kind"]:
                raise AuthoringError(
                    "PROVENANCE_RELATION_KIND_BINDING_MISMATCH"
                )
        if (
            _parsed_output_binding_hash(binding["factor_kind"], parsed)
            != binding["parsed_output_sha256"]
        ):
            raise AuthoringError("PROVENANCE_PARSED_OUTPUT_TAMPERED")
        parsed_by_factor[factor_key] = parsed

    seen: Counter[tuple[str, str]] = Counter()
    for row_kind, rows in (("query", queries), ("description", descriptions)):
        for row in rows:
            family_key = str(row.get("family_key"))
            component_ordinal = row.get("component_ordinal")
            content_kind = str(
                row.get(
                    "query_kind"
                    if row_kind == "query"
                    else "description_kind"
                )
            )
            if content_kind == "family_compositional":
                factor_key = f"{family_key}:family_composition"
                field = f"family_compositional_{row_kind}"
                if component_ordinal is not None:
                    raise AuthoringError(
                        "PROVENANCE_COMPOSITION_ORDINAL_INVALID"
                    )
            elif content_kind in {"visual", "ambient"}:
                if not isinstance(component_ordinal, int):
                    raise AuthoringError(
                        "PROVENANCE_COMPONENT_ORDINAL_MISSING"
                    )
                factor_key = (
                    f"{family_key}:component:{component_ordinal}:"
                    f"{content_kind}"
                )
                field = f"{content_kind}_{row_kind}"
            else:
                raise AuthoringError("PROVENANCE_CONTENT_KIND_INVALID")
            binding = bindings.get(factor_key)
            if binding is None:
                raise AuthoringError("PROVENANCE_ROW_FACTOR_MISSING")
            if row.get("factor_binding") != binding:
                raise AuthoringError("PROVENANCE_ROW_BINDING_MISMATCH")
            text_key = (
                "query_text" if row_kind == "query" else "description_text"
            )
            expected_text = parsed_by_factor[factor_key].get(field)
            if content_kind == "family_compositional":
                component_factors = [
                    {
                        **parsed_by_factor[
                            f"{family_key}:component:{ordinal}:visual"
                        ],
                        **parsed_by_factor[
                            f"{family_key}:component:{ordinal}:ambient"
                        ],
                    }
                    for ordinal in range(
                        1,
                        int(
                            expected_specs[factor_key]["component_count"]
                            if expected_specs is not None
                            else sum(
                                key.endswith(":visual")
                                and key.startswith(
                                    f"{family_key}:component:"
                                )
                                for key in parsed_by_factor
                            )
                        )
                        + 1,
                    )
                ]
                assembled = _mechanical_composition_texts(
                    component_factors,
                    parsed_by_factor[factor_key],
                    family_shape=(
                        expected_specs[factor_key]["family_shape"]
                        if expected_specs is not None
                        else (
                            "one_component"
                            if len(component_factors) == 1
                            else "two_component_ordered"
                        )
                    ),
                )
                expected_text = assembled[field]
                if row.get("composition_clauses") != assembled[
                    "component_clauses"
                ]:
                    raise AuthoringError(
                        "PROVENANCE_COMPOSITION_CLAUSES_MISMATCH"
                    )
            if row.get(text_key) != expected_text:
                raise AuthoringError("PROVENANCE_CROSS_FACTOR_SUBSTITUTION")
            seen[(factor_key, field)] += 1

    expected = Counter()
    for factor_key, binding in bindings.items():
        if binding["factor_kind"] == "visual":
            expected[(factor_key, "visual_query")] = 1
            expected[(factor_key, "visual_description")] = 1
        elif binding["factor_kind"] == "ambient":
            expected[(factor_key, "ambient_query")] = 1
            expected[(factor_key, "ambient_description")] = 1
        else:
            expected[(factor_key, "family_compositional_query")] = 1
            expected[(factor_key, "family_compositional_description")] = 1
    if seen != expected:
        raise AuthoringError("PROVENANCE_FINAL_ROW_INVENTORY_MISMATCH")
    rebuilt = {
        "schema_version": (
            ACCEPTED_FACTOR_MANIFEST_SCHEMA_VERSION
        ),
        "pipeline_id": accepted_factor_manifest.get("pipeline_id"),
        "ambient_constraint": ambient_constraint_contract(),
        "accepted_factor_count": len(bindings),
        "visual_factor_count": sum(
            row["factor_kind"] == "visual" for row in bindings.values()
        ),
        "ambient_factor_count": sum(
            row["factor_kind"] == "ambient" for row in bindings.values()
        ),
        "composition_factor_count": sum(
            row["factor_kind"] == "family_composition"
            for row in bindings.values()
        ),
        "factors": [
            bindings[key]
            for key in sorted(bindings)
        ],
        "cross_factor_fill_or_substitution_permitted": False,
    }
    rebuilt["manifest_payload_sha256"] = semantic_hash(rebuilt)
    if rebuilt != dict(accepted_factor_manifest):
        raise AuthoringError("PROVENANCE_ACCEPTED_MANIFEST_NOT_EXACT")
    return {
        "status": "PASS",
        "accepted_factor_count": len(bindings),
        "bound_final_row_count": sum(seen.values()),
        "cross_factor_fill_or_substitution_detected": False,
    }


def derive_expected_factor_specs(
    structural: Mapping[str, Any],
    prompt_manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Rebuild the complete factor namespace without trusting the manifest."""

    if (
        prompt_manifest.get("schema_version")
        != PROMPT_MANIFEST_SCHEMA_VERSION
        or prompt_manifest.get("ambient_constraint")
        != ambient_constraint_contract()
    ):
        raise AuthoringError("PROMPT_MANIFEST_R20_CONTRACT_INVALID")
    firewall = prompt_manifest.get("model_visible_firewall")
    if not isinstance(firewall, Mapping):
        raise AuthoringError("PROMPT_MANIFEST_R20_CONTRACT_INVALID")
    _validate_ambient_derivation_contract(
        firewall,
        error="PROMPT_MANIFEST_R20_CONTRACT_INVALID",
    )
    families = structural.get("families")
    if not isinstance(families, list):
        raise AuthoringError("PROVENANCE_STRUCTURAL_FAMILIES_INVALID")
    expected: dict[str, dict[str, Any]] = {}
    for family in families:
        family_key = str(family["family_key"])
        intervals = family.get("intervals")
        if not isinstance(intervals, list) or not intervals:
            raise AuthoringError("PROVENANCE_STRUCTURAL_INTERVALS_INVALID")
        for ordinal, interval in enumerate(intervals, 1):
            for factor_kind in ("visual", "ambient"):
                factor_key = (
                    f"{family_key}:component:{ordinal}:{factor_kind}"
                )
                expected[factor_key] = {
                    "factor_key": factor_key,
                    "family_key": family_key,
                    "factor_kind": factor_kind,
                    "component_ordinal": ordinal,
                    "component_count": len(intervals),
                    "family_shape": str(family["shape"]),
                    "clip_key": str(interval["clip_key"]),
                    "media_modality": factor_kind,
                }
        factor_key = f"{family_key}:family_composition"
        expected[factor_key] = {
            "factor_key": factor_key,
            "family_key": family_key,
            "factor_kind": "family_composition",
            "component_ordinal": None,
            "component_count": len(intervals),
            "family_shape": str(family["shape"]),
            "clip_key": None,
        }

    visual_prompts = prompt_manifest.get("visual_prompts")
    ambient_prompts = prompt_manifest.get("ambient_prompts")
    composition_contracts = prompt_manifest.get("composition_contracts")
    if (
        not isinstance(visual_prompts, list)
        or not isinstance(ambient_prompts, list)
        or not isinstance(composition_contracts, list)
    ):
        raise AuthoringError("PROVENANCE_PROMPT_MANIFEST_INVALID")
    observed_media = {}
    for factor_kind, rows in (
        ("visual", visual_prompts),
        ("ambient", ambient_prompts),
    ):
        for row in rows:
            family_key = str(row.get("family_key"))
            ordinal = row.get("component_ordinal")
            factor_key = (
                f"{family_key}:component:{ordinal}:{factor_kind}"
            )
            if factor_key in observed_media:
                raise AuthoringError("PROVENANCE_PROMPT_FACTOR_DUPLICATE")
            observed_media[factor_key] = row
    observed_compositions = {}
    for row in composition_contracts:
        family_key = str(row.get("family_key"))
        factor_key = f"{family_key}:family_composition"
        if factor_key in observed_compositions:
            raise AuthoringError("PROVENANCE_PROMPT_FACTOR_DUPLICATE")
        observed_compositions[factor_key] = row
    if set(observed_media) != {
        key
        for key, row in expected.items()
        if row["factor_kind"] in {"visual", "ambient"}
    }:
        raise AuthoringError("PROVENANCE_PROMPT_MEDIA_FACTOR_SET_MISMATCH")
    if set(observed_compositions) != {
        key
        for key, row in expected.items()
        if row["factor_kind"] == "family_composition"
    }:
        raise AuthoringError("PROVENANCE_PROMPT_COMPOSITION_SET_MISMATCH")
    for factor_key, row in observed_media.items():
        spec = expected[factor_key]
        if (
            row.get("factor_kind") != spec["factor_kind"]
            or row.get("media_component_count") != 1
            or row.get("media_modalities") != [spec["media_modality"]]
            or row.get("media_component_clip_keys") != [spec["clip_key"]]
        ):
            raise AuthoringError(
                "PROVENANCE_PROMPT_MEDIA_BINDING_INVALID"
            )
        if spec["factor_kind"] == "ambient":
            expected_row = _prompt_record(
                factor_kind="ambient",
                user_payload=ambient_model_visible_prompt(),
                system_prompt=AMBIENT_SYSTEM_PROMPT,
                family_key=spec["family_key"],
                component_ordinal=spec["component_ordinal"],
                clip_key=spec["clip_key"],
                media_modality="ambient",
            )
            if row != expected_row:
                raise AuthoringError(
                    "PROMPT_MANIFEST_AMBIENT_PROMPT_DRIFT"
                )
    for row in observed_compositions.values():
        family_key = str(row.get("family_key"))
        spec = expected[f"{family_key}:family_composition"]
        if (
            row.get("factor_kind") != "family_composition"
            or row.get("media_component_count") != 0
            or row.get("family_shape") != spec["family_shape"]
            or row.get("component_count") != spec["component_count"]
            or row.get("required_relation_kind")
            != RELATION_KIND_BY_SHAPE[spec["family_shape"]]
        ):
            raise AuthoringError(
                "PROVENANCE_PROMPT_COMPOSITION_BINDING_INVALID"
            )
    if (
        prompt_manifest.get("visual_prompt_count")
        != len(visual_prompts)
        or prompt_manifest.get("ambient_prompt_count")
        != len(ambient_prompts)
        or prompt_manifest.get("composition_prompt_count")
        != len(observed_compositions)
        or prompt_manifest.get("prompt_count") != len(expected)
    ):
        raise AuthoringError("PROVENANCE_PROMPT_COUNT_MISMATCH")
    return expected


def materialize_query_records(
    structural: Mapping[str, Any],
    parsed_by_family: Mapping[str, Mapping[str, Any]],
    accepted_factor_manifest: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bindings = (
        _factor_bindings_by_key(accepted_factor_manifest)
        if accepted_factor_manifest is not None
        else {}
    )
    queries: list[dict[str, Any]] = []
    descriptions: list[dict[str, Any]] = []
    query_index = 0
    for family in structural["families"]:
        family_key = family["family_key"]
        if family_key not in parsed_by_family:
            raise AuthoringError(f"MISSING_PARSED_FAMILY:{family_key}")
        parsed = parsed_by_family[family_key]
        components = parsed["components"]
        for ordinal, (interval, component_value) in enumerate(
            zip(family["intervals"], components, strict=True), 1
        ):
            if not isinstance(component_value, Mapping):
                raise AuthoringError("MATERIALIZATION_COMPONENT_INVALID")
            component = validate_accepted_component_factor(
                {
                    key: component_value[key]
                    for key in COMPONENT_OUTPUT_SCHEMA
                }
            )
            for channel in ("visual", "ambient"):
                factor_key = (
                    f"{family_key}:component:{ordinal}:{channel}"
                )
                factor_binding = bindings.get(factor_key)
                if bindings and factor_binding is None:
                    raise AuthoringError(
                        "MATERIALIZATION_FACTOR_BINDING_MISSING"
                    )
                query_index += 1
                queries.append(
                    {
                        "query_key": f"query-{query_index:03d}",
                        "family_key": family_key,
                        "clip_key": interval["clip_key"],
                        "component_ordinal": ordinal,
                        "factor_binding": factor_binding,
                        "query_scope": "handle",
                        "query_kind": channel,
                        "query_text": component[f"{channel}_query"],
                        "machine_observation_status": (
                            "PENDING_MACHINE_SEMANTIC_GATES"
                        ),
                        "field_gate_status": {
                            name: "PENDING" for name in SEMANTIC_GATE_NAMES
                        },
                        "human_grounded": False,
                        "template_only_control": False,
                    }
                )
                descriptions.append(
                    {
                        "description_key": (
                            f"description:{family_key}:"
                            f"{interval['clip_key']}:{channel}"
                        ),
                        "family_key": family_key,
                        "clip_key": interval["clip_key"],
                        "component_ordinal": ordinal,
                        "factor_binding": factor_binding,
                        "description_kind": channel,
                        "description_text": component[
                            f"{channel}_description"
                        ],
                        "machine_authored": True,
                        "human_semantic_label": False,
                        "machine_observation_status": (
                            "PENDING_MACHINE_SEMANTIC_GATES"
                        ),
                        "field_gate_status": {
                            name: "PENDING" for name in SEMANTIC_GATE_NAMES
                        },
                        "human_grounded": False,
                    }
                )
        composition_factor_key = f"{family_key}:family_composition"
        composition_binding = bindings.get(composition_factor_key)
        if bindings and composition_binding is None:
            raise AuthoringError("MATERIALIZATION_FACTOR_BINDING_MISSING")
        query_index += 1
        queries.append(
            {
                "query_key": f"query-{query_index:03d}",
                "family_key": family_key,
                "clip_key": None,
                "component_ordinal": None,
                "factor_binding": composition_binding,
                "query_scope": "family",
                "query_kind": "family_compositional",
                "query_text": parsed["family_compositional_query"],
                "composition_clauses": parsed.get("component_clauses"),
                "machine_observation_status": (
                    "PENDING_MACHINE_SEMANTIC_GATES"
                ),
                "field_gate_status": {
                    name: "PENDING" for name in SEMANTIC_GATE_NAMES
                },
                "human_grounded": False,
                "template_only_control": False,
            }
        )
        descriptions.append(
            {
                "description_key": (
                    f"description:{family_key}:family_compositional"
                ),
                "family_key": family_key,
                "clip_key": None,
                "component_ordinal": None,
                "factor_binding": composition_binding,
                "description_kind": "family_compositional",
                "description_text": parsed[
                    "family_compositional_description"
                ],
                "composition_clauses": parsed.get("component_clauses"),
                "machine_authored": True,
                "human_semantic_label": False,
                "machine_observation_status": (
                    "PENDING_MACHINE_SEMANTIC_GATES"
                ),
                "field_gate_status": {
                    name: "PENDING" for name in SEMANTIC_GATE_NAMES
                },
                "human_grounded": False,
            }
        )
    if len(queries) != EXPECTED_QUERY_COUNT:
        raise AuthoringError("AUTHORED_QUERY_COUNT_MISMATCH")
    return queries, descriptions


def _phrase_overlap(
    text: str, transcript: str, *, ngram: int = 4
) -> list[str]:
    words = _normalized_words(text)
    transcript_words = _normalized_words(transcript)
    if len(words) < ngram or len(transcript_words) < ngram:
        return []
    text_ngrams = {
        tuple(words[index : index + ngram])
        for index in range(len(words) - ngram + 1)
    }
    transcript_ngrams = {
        tuple(transcript_words[index : index + ngram])
        for index in range(len(transcript_words) - ngram + 1)
    }
    return [" ".join(row) for row in sorted(text_ngrams & transcript_ngrams)]


def literal_leakage_findings(
    texts: Sequence[Mapping[str, Any]],
    *,
    transcripts_by_clip: Mapping[str, str],
    slot_names_by_family: Mapping[str, Sequence[str]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in texts:
        text = str(row["text"])
        key = str(row["key"])
        family_key = str(row["family_key"])
        clip_key = row.get("clip_key")
        lowered = text.casefold()
        if PRIVATE_ID_RE.search(text):
            findings.append({"key": key, "kind": "private_id"})
        if TIMESTAMP_RE.search(text):
            findings.append({"key": key, "kind": "timestamp"})
        for literal in SOURCE_LITERALS:
            if literal.casefold() in lowered:
                findings.append(
                    {"key": key, "kind": "source_name", "literal": literal}
                )
        words = set(_normalized_words(text))
        labels = sorted(words & FINAL_MODALITY_LABELS)
        if labels:
            findings.append(
                {
                    "key": key,
                    "kind": "modality_label",
                    "literals": labels,
                }
            )
        for slot_name in slot_names_by_family.get(family_key, []):
            forms = {
                slot_name.casefold(),
                slot_name.casefold().replace("_", " "),
                f"[{slot_name.casefold()}]",
            }
            if any(form in lowered for form in forms):
                findings.append(
                    {
                        "key": key,
                        "kind": "provisional_slot_literal",
                        "literal": slot_name,
                    }
                )
        candidate_transcripts: list[tuple[str, str]] = []
        if isinstance(clip_key, str) and clip_key in transcripts_by_clip:
            candidate_transcripts.append(
                (clip_key, transcripts_by_clip[clip_key])
            )
        elif clip_key is None:
            candidate_transcripts.extend(sorted(transcripts_by_clip.items()))
        overlaps: list[dict[str, str]] = []
        for transcript_key, transcript in candidate_transcripts:
            for phrase in _phrase_overlap(text, transcript):
                overlaps.append(
                    {"clip_key": transcript_key, "phrase": phrase}
                )
        if overlaps:
            findings.append(
                {
                    "key": key,
                    "kind": "copied_asr_ngram",
                    "overlaps": overlaps,
                }
            )
    return findings


def lexical_collision_findings(
    queries: Sequence[Mapping[str, Any]],
    *,
    threshold: float = LEXICAL_COLLISION_THRESHOLD,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    normalized_groups: dict[str, list[str]] = defaultdict(list)
    for row in queries:
        normalized_groups[_normalized_text(str(row["query_text"]))].append(
            str(row["query_key"])
        )
    for normalized, keys in sorted(normalized_groups.items()):
        if len(keys) > 1:
            findings.append(
                {
                    "kind": "exact_duplicate",
                    "query_keys": keys,
                    "normalized_sha256": semantic_hash(normalized),
                }
            )
    for index, left in enumerate(queries):
        left_words = set(_normalized_words(str(left["query_text"])))
        for right in queries[index + 1 :]:
            if left["query_kind"] != right["query_kind"]:
                continue
            right_words = set(_normalized_words(str(right["query_text"])))
            union = left_words | right_words
            if not union:
                continue
            shared = left_words & right_words
            similarity = len(shared) / len(union)
            if len(shared) >= 5 and similarity >= threshold:
                findings.append(
                    {
                        "kind": "lexical_near_collision",
                        "left_query_key": left["query_key"],
                        "right_query_key": right["query_key"],
                        "query_kind": left["query_kind"],
                        "jaccard": round(similarity, 8),
                    }
                )
    return findings


def ambient_semantic_tuple_duplicate_audit(
    accepted_factor_manifest: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]] = (),
    *,
    scope: str = "authoring",
) -> dict[str, Any]:
    """Mechanically inventory ambient tuple collisions without rewriting.

    Repeated tuples are grouped by their canonical semantic hash, independent
    of ordinal or rendered wording.  A repeated tuple within one family is a
    blocking failure.  Cross-family repeats remain explicit global findings
    for outer selection governance but are not silently rewritten or retried.
    """

    bindings = _factor_bindings_by_key(accepted_factor_manifest)
    query_keys_by_factor: dict[str, list[str]] = defaultdict(list)
    for query in queries:
        if query.get("query_kind") != "ambient":
            continue
        binding = query.get("factor_binding")
        if not isinstance(binding, Mapping):
            continue
        factor_key = binding.get("factor_key")
        query_key = query.get("query_key")
        if isinstance(factor_key, str) and isinstance(query_key, str):
            query_keys_by_factor[factor_key].append(query_key)

    ambient_rows = []
    for factor_key, row in sorted(bindings.items()):
        if row["factor_kind"] != "ambient":
            continue
        semantic = validate_ambient_semantic_tuple(row["ambient_semantics"])
        tuple_sha256 = semantic_hash(semantic)
        if row["ambient_semantic_tuple_sha256"] != tuple_sha256:
            raise AuthoringError(
                "AMBIENT_SEMANTIC_TUPLE_DUPLICATE_INPUT_HASH_MISMATCH"
            )
        ambient_rows.append(
            {
                "factor_key": factor_key,
                "family_key": str(row["family_key"]),
                "component_ordinal": int(row["component_ordinal"]),
                "clip_key": str(row["clip_key"]),
                "query_keys": sorted(query_keys_by_factor.get(factor_key, [])),
                "ambient_semantic_tuple_sha256": tuple_sha256,
                "ambient_semantics": semantic,
            }
        )

    by_tuple: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ambient_rows:
        by_tuple[row["ambient_semantic_tuple_sha256"]].append(row)

    findings = []
    blocking_findings = []
    collision_ledger = []
    for tuple_sha256, rows in sorted(by_tuple.items()):
        if len(rows) < 2:
            continue
        family_counts = Counter(row["family_key"] for row in rows)
        same_family_keys = sorted(
            family_key
            for family_key, count in family_counts.items()
            if count > 1
        )
        finding = {
            "kind": "ambient_semantic_tuple_duplicate",
            "ambient_semantic_tuple_sha256": tuple_sha256,
            "ambient_semantics": rows[0]["ambient_semantics"],
            "occurrence_count": len(rows),
            "family_keys": sorted(family_counts),
            "same_family_keys": same_family_keys,
            "blocking_same_family_duplicate": bool(same_family_keys),
            "occurrences": rows,
        }
        findings.append(finding)
        if same_family_keys:
            blocking_findings.append(finding)
        for left_index, left in enumerate(rows):
            for right in rows[left_index + 1 :]:
                collision_ledger.append(
                    {
                        "ambient_semantic_tuple_sha256": tuple_sha256,
                        "left_factor_key": left["factor_key"],
                        "right_factor_key": right["factor_key"],
                        "left_family_key": left["family_key"],
                        "right_family_key": right["family_key"],
                        "left_component_ordinal": left[
                            "component_ordinal"
                        ],
                        "right_component_ordinal": right[
                            "component_ordinal"
                        ],
                        "left_query_keys": left["query_keys"],
                        "right_query_keys": right["query_keys"],
                        "same_family": (
                            left["family_key"] == right["family_key"]
                        ),
                    }
                )

    return {
        "schema_version": (
            "av-trace.p23-102-ambient-semantic-tuple-collisions/1.0"
        ),
        "scope": scope,
        "status": "PASS" if not blocking_findings else "FAIL_CLOSED",
        "blocking_policy": "same_family_duplicate_tuple",
        "automatic_rewrite_permitted": False,
        "synonym_template_substitution_permitted": False,
        "ordinal_disambiguation_permitted": False,
        "authoring_retry_permitted": False,
        "ambient_factor_count": len(ambient_rows),
        "duplicate_group_count": len(findings),
        "blocking_duplicate_group_count": len(blocking_findings),
        "global_duplicate_findings": findings,
        "blocking_findings": blocking_findings,
        "collision_ledger": collision_ledger,
    }


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise AuthoringError("ZERO_NORM_AUDIT_EMBEDDING")
    return numerator / (left_norm * right_norm)


def _token_jaccard(left: str, right: str) -> tuple[float, int]:
    left_words = set(_normalized_words(left))
    right_words = set(_normalized_words(right))
    union = left_words | right_words
    shared = left_words & right_words
    return (len(shared) / len(union) if union else 0.0, len(shared))


def _has_explicit_acoustic_lexicon(text: str) -> bool:
    return bool(_acoustic_concepts(text))


def _throat_clearing_mentions(words: Sequence[str]) -> list[dict[str, Any]]:
    mentions = []
    for index, word in enumerate(words):
        if (
            word in {"clear", "clears", "clearing", "cleared"}
            and index + 2 < len(words)
            and words[index + 1]
            in {
                "a",
                "an",
                "her",
                "his",
                "its",
                "my",
                "our",
                "the",
                "their",
                "your",
            }
            and words[index + 2] == "throat"
        ) or (
            word == "throat"
            and index + 1 < len(words)
            and words[index + 1]
            in {"clear", "clears", "clearing", "cleared"}
        ):
            mentions.append(
                {
                    "concept": "throat-clearing",
                    "index": index,
                    "token": word,
                    "category": "unambiguous",
                }
            )
    return mentions


def _acoustic_mentions(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    words = _normalized_words(text)
    mentions = _throat_clearing_mentions(words)
    for index, word in enumerate(words):
        unambiguous = UNAMBIGUOUS_ACOUSTIC_FORM_TO_CONCEPT.get(word)
        if unambiguous is not None:
            mentions.append(
                {
                    "concept": unambiguous,
                    "index": index,
                    "token": word,
                    "category": "unambiguous",
                }
            )
            continue
        ambiguous = AMBIGUOUS_ACOUSTIC_FORM_TO_CONCEPT.get(word)
        if ambiguous is not None:
            mentions.append(
                {
                    "concept": ambiguous,
                    "index": index,
                    "token": word,
                    "category": "ambiguous",
                }
            )
    deduplicated = {
        (row["concept"], row["index"], row["category"]): row
        for row in mentions
    }
    return words, sorted(
        deduplicated.values(),
        key=lambda row: (row["index"], row["concept"]),
    )


def _ambiguous_acoustic_binding(
    words: Sequence[str], mention: Mapping[str, Any]
) -> dict[str, Any]:
    index = int(mention["index"])
    token = str(mention["token"])
    left = list(words[max(0, index - 4) : index])
    right = list(words[index + 1 : index + 6])
    immediate_left = words[index - 1] if index else ""
    immediate_right = words[index + 1] if index + 1 < len(words) else ""

    if immediate_left in AUDITORY_ADJECTIVE_MARKERS:
        return {"bound": True, "route": "auditory_adjective"}
    if immediate_right in AUDITORY_ADJECTIVE_MARKERS:
        return {"bound": True, "route": "event_then_auditory_adjective"}
    if (
        immediate_right in AUDITORY_NOUN_MARKERS
        and token.endswith("ing")
    ):
        return {"bound": True, "route": "event_plus_sound_noun"}
    if (
        index >= 2
        and words[index - 2] in AUDITORY_NOUN_MARKERS
        and words[index - 1] == "of"
    ) or (
        index >= 3
        and words[index - 3] in AUDITORY_NOUN_MARKERS
        and words[index - 2] == "of"
        and words[index - 1] in {"a", "an", "the"}
    ):
        return {"bound": True, "route": "sound_of_event"}
    if (
        index >= 4
        and words[index - 4] in AUDITORY_NOUN_MARKERS
        and words[index - 3] == "of"
        and words[index - 2] in {"a", "an", "the"}
        and words[index - 1] not in AUDITORY_NOUN_MARKERS
    ):
        return {"bound": True, "route": "sound_of_single_source_event"}
    if any(
        marker in right[:3]
        for marker in AUDITORY_PERCEPTION_MARKERS
        | AUDITORY_ADJECTIVE_MARKERS
    ) and any(word in {"am", "are", "be", "is", "was", "were"} for word in right[:2]):
        return {"bound": True, "route": "event_heard_or_audible"}
    if any(
        marker in left[-3:]
        for marker in AUDITORY_PERCEPTION_MARKERS
    ):
        intervening = left[
            max(
                (
                    position
                    for position, word in enumerate(left)
                    if word in AUDITORY_PERCEPTION_MARKERS
                ),
                default=-1,
            )
            + 1 :
        ]
        if all(
            word in {"a", "an", "the"} | ACOUSTIC_EVENT_MODIFIERS
            for word in intervening
        ):
            return {"bound": True, "route": "heard_event"}
    if immediate_right in AUDITORY_RESPONSE_MARKERS:
        return {"bound": True, "route": "event_auditory_response"}
    if (
        token in {"ring", "ringing", "rings", "rang"}
        and immediate_right == "out"
    ):
        return {"bound": True, "route": "ring_out_phrasal_event"}
    if (
        len(right) >= 2
        and right[0] in {"ring", "rings", "rang", "ringing"}
        and right[1] == "out"
    ):
        return {"bound": True, "route": "event_rings_out"}
    if right and right[0] in {
        "make",
        "made",
        "makes",
        "making",
        "produce",
        "produced",
        "produces",
        "producing",
    } and any(word in AUDITORY_NOUN_MARKERS for word in right[1:5]):
        return {"bound": True, "route": "event_makes_sound"}

    nominal_forms = {
        form
        for form in AMBIGUOUS_ACOUSTIC_FORMS[str(mention["concept"])]
        if not form.endswith("ed")
    }
    modifiers = []
    for word in reversed(left[-3:]):
        if word not in ACOUSTIC_EVENT_MODIFIERS:
            break
        modifiers.append(word)
    modifiers.reverse()
    if (
        token in nominal_forms
        and modifiers
        and (
            str(mention["concept"]) not in CONTEXT_BOUND_ACTION_CONCEPTS
            or any(
                modifier
                in {
                    "audible",
                    "crisp",
                    "distinct",
                    "faint",
                    "loud",
                    "metallic",
                    "muffled",
                    "rhythmic",
                    "sharp",
                    "soft",
                }
                for modifier in modifiers
            )
        )
    ):
        return {
            "bound": True,
            "route": "controlled_sound_event_noun",
            "modifiers": modifiers,
        }
    return {"bound": False, "route": "ambiguous_action_without_auditory_context"}


def _acoustic_context_evidence(text: str) -> dict[str, Any]:
    words, mentions = _acoustic_mentions(text)
    evaluated = []
    for mention in mentions:
        if mention["category"] == "unambiguous":
            evaluated.append(
                {
                    **mention,
                    "bound": True,
                    "route": "unambiguous_acoustic_event",
                }
            )
            continue
        binding = _ambiguous_acoustic_binding(words, mention)
        evaluated.append({**mention, **binding})

    accepted_indices = {
        int(row["index"]) for row in evaluated if row["bound"]
    }
    controlled_auditory_markers = []
    controlled_marker_indices = set()
    for row in evaluated:
        index = int(row["index"])
        marker_index = index + 1
        if (
            index not in accepted_indices
            or marker_index >= len(words)
            or words[marker_index] not in AUDITORY_RESPONSE_MARKERS
        ):
            continue
        controlled_marker_indices.add(marker_index)
        controlled_auditory_markers.append(
            {
                "index": marker_index,
                "token": words[marker_index],
                "role": "controlled_auditory_marker",
                "governing_event_index": index,
                "governing_event_concept": row["concept"],
            }
        )

    accepted = [
        row
        for row in evaluated
        if row["bound"] and int(row["index"]) not in controlled_marker_indices
    ]
    rejected = [
        row
        for row in evaluated
        if not row["bound"]
        and int(row["index"]) not in controlled_marker_indices
    ]
    return {
        "accepted": accepted,
        "rejected_ambiguous": rejected,
        "controlled_auditory_markers": controlled_auditory_markers,
        "concepts": sorted({row["concept"] for row in accepted}),
    }


def _specific_acoustic_terms(text: str) -> list[str]:
    return _acoustic_context_evidence(text)["concepts"]


def _generic_acoustic_claim_only(text: str) -> bool:
    words = set(_normalized_words(text))
    return bool(words & GENERIC_ACOUSTIC_TERMS) and not (
        words
        - GENERIC_ACOUSTIC_TERMS
        - GENERIC_ACOUSTIC_CONTEXT_TERMS
    )


def _clap_acousticness(
    texts: Sequence[str],
    embed_ambient: Callable[[Sequence[str]], Sequence[Sequence[float]]],
) -> list[dict[str, Any]]:
    if not texts:
        return []
    prompts = [
        *texts,
        *ACOUSTICNESS_POSITIVE_PROMPTS,
        *ACOUSTICNESS_NEGATIVE_PROMPTS,
    ]
    vectors = list(embed_ambient(prompts))
    if len(vectors) != len(prompts):
        raise AuthoringError("ACOUSTICNESS_EMBEDDING_COUNT_MISMATCH")
    positive_offset = len(texts)
    negative_offset = positive_offset + len(ACOUSTICNESS_POSITIVE_PROMPTS)
    positive_vectors = vectors[positive_offset:negative_offset]
    negative_vectors = vectors[negative_offset:]
    results = []
    for text, vector in zip(texts, vectors[: len(texts)], strict=True):
        positive = sum(
            _cosine(vector, reference) for reference in positive_vectors
        ) / len(positive_vectors)
        negative = sum(
            _cosine(vector, reference) for reference in negative_vectors
        ) / len(negative_vectors)
        margin = positive - negative
        results.append(
            {
                "text_sha256": semantic_hash(text),
                "positive_cosine": round(positive, 8),
                "negative_cosine": round(negative, 8),
                "margin": round(margin, 8),
                "passed": (
                    positive >= CLAP_ACOUSTICNESS_MIN_POSITIVE_COSINE
                    and margin >= CLAP_ACOUSTICNESS_MIN_MARGIN
                ),
            }
        )
    return results


def ambient_acoustic_grounding_audit(
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
    *,
    embed_ambient: Callable[[Sequence[str]], Sequence[Sequence[float]]],
) -> dict[str, Any]:
    rows = [
        {
            "key": str(row["query_key"]),
            "text": str(row["query_text"]),
        }
        for row in queries
        if row["query_kind"] == "ambient"
    ] + [
        {
            "key": str(row["description_key"]),
            "text": str(row["description_text"]),
        }
        for row in descriptions
        if row["description_kind"] == "ambient"
    ]
    classifier_rows = [
        row
        for row in rows
        if not _has_explicit_acoustic_lexicon(row["text"])
        and not _generic_acoustic_claim_only(row["text"])
    ]
    classifier_results = _clap_acousticness(
        [row["text"] for row in classifier_rows], embed_ambient
    )
    classifier_by_key = {
        row["key"]: result
        for row, result in zip(
            classifier_rows, classifier_results, strict=True
        )
    }
    findings = []
    field_results = {}
    for row in rows:
        context = _acoustic_context_evidence(row["text"])
        specific_terms = context["concepts"]
        lexical = bool(specific_terms)
        generic_only = _generic_acoustic_claim_only(row["text"])
        classifier = classifier_by_key.get(row["key"])
        rejected_ambiguous = context["rejected_ambiguous"]
        passed = not generic_only and lexical and not rejected_ambiguous
        route = (
            "ambiguous_acoustic_context_invalid"
            if rejected_ambiguous
            else "explicit_specific_acoustic_event"
            if lexical
            else "specific_acoustic_event_missing"
        )
        field_results[row["key"]] = {
            "status": "PASS" if passed else "FAIL",
            "route": route,
            "specific_acoustic_terms": specific_terms,
            "acoustic_context_evidence": context["accepted"],
            "rejected_ambiguous_acoustic_mentions": (
                rejected_ambiguous
            ),
            "generic_acoustic_claim_only": generic_only,
            "classifier": classifier,
        }
        if not passed:
            findings.append(
                {
                    "kind": "ambient_action_only_or_non_acoustic_paraphrase",
                    "key": row["key"],
                    "route": route,
                    "classifier": classifier,
                }
            )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "field_results": field_results,
        "explicit_lexicon_sha256": semantic_hash(
            {
                "registry_manifest_sha256": (
                    ACOUSTIC_CONCEPT_REGISTRY_MANIFEST_SHA256
                ),
                "unambiguous": sorted(UNAMBIGUOUS_ACOUSTIC_CONCEPTS),
                "ambiguous_forms": {
                    key: sorted(value)
                    for key, value in sorted(
                        AMBIGUOUS_ACOUSTIC_FORMS.items()
                    )
                },
                "auditory_noun_markers": sorted(AUDITORY_NOUN_MARKERS),
                "auditory_adjective_markers": sorted(
                    AUDITORY_ADJECTIVE_MARKERS
                ),
                "auditory_perception_markers": sorted(
                    AUDITORY_PERCEPTION_MARKERS
                ),
                "auditory_response_markers": sorted(
                    AUDITORY_RESPONSE_MARKERS
                ),
                "controlled_event_modifiers": sorted(
                    ACOUSTIC_EVENT_MODIFIERS
                ),
            }
        ),
        "acoustic_concept_registry_sha256": (
            ACOUSTIC_CONCEPT_REGISTRY_MANIFEST_SHA256
        ),
        "classifier": {
            "encoder": "CLAP text",
            "positive_prompt_sha256": semantic_hash(
                ACOUSTICNESS_POSITIVE_PROMPTS
            ),
            "negative_prompt_sha256": semantic_hash(
                ACOUSTICNESS_NEGATIVE_PROMPTS
            ),
            "minimum_positive_cosine": (
                CLAP_ACOUSTICNESS_MIN_POSITIVE_COSINE
            ),
            "minimum_margin": CLAP_ACOUSTICNESS_MIN_MARGIN,
        },
    }


def degenerate_asr_analysis(transcript: str) -> dict[str, Any]:
    words = _normalized_words(transcript)
    counts = Counter(words)
    token_count = len(words)
    unique_count = len(counts)
    unique_ratio = unique_count / token_count if token_count else 1.0
    dominant_token = None
    dominant_count = 0
    if counts:
        dominant_token, dominant_count = counts.most_common(1)[0]
    dominant_ratio = dominant_count / token_count if token_count else 0.0
    repeated_short_vocalization = (
        dominant_token in SHORT_VOCALIZATION_TOKENS
        and dominant_count >= ASR_REPEATED_VOCALIZATION_MIN_COUNT
        and dominant_ratio >= ASR_REPEATED_VOCALIZATION_DOMINANCE
    )
    low_unique_ratio = (
        token_count >= ASR_LOW_UNIQUE_TOKEN_MIN_TOKENS
        and unique_ratio < ASR_LOW_UNIQUE_TOKEN_RATIO
    )
    low_information = (
        token_count > 0
        and unique_count <= 2
        and (
            token_count >= ASR_REPEATED_VOCALIZATION_MIN_COUNT
            or all(word in SHORT_VOCALIZATION_TOKENS for word in counts)
        )
    )
    reasons = []
    if low_unique_ratio:
        reasons.append("low_unique_token_ratio")
    if repeated_short_vocalization:
        reasons.append("repeated_short_vocalization")
    if low_information:
        reasons.append("low_information")
    return {
        "token_count": token_count,
        "unique_token_count": unique_count,
        "unique_token_ratio": round(unique_ratio, 8),
        "dominant_token_sha256": (
            semantic_hash(dominant_token) if dominant_token else None
        ),
        "dominant_token_count": dominant_count,
        "dominant_token_ratio": round(dominant_ratio, 8),
        "degenerate": bool(reasons),
        "reasons": reasons,
    }


def _human_vocalization_policy(text: str) -> dict[str, Any]:
    words = set(_normalized_words(text))
    acoustic_concepts = _acoustic_concepts(text)
    human_terms = sorted(words & HUMAN_VOCALIZATION_TERMS)
    nonlexical_terms = sorted(words & NONLEXICAL_HUMAN_VOCALIZATION_TERMS)
    if "throat-clearing" in acoustic_concepts:
        human_terms = sorted({*human_terms, "throat-clearing"})
        nonlexical_terms = sorted({*nonlexical_terms, "throat-clearing"})
    lexical_terms = sorted(
        word
        for word in words
        if word in LEXICAL_SPEECH_TERMS
    )
    clearly_nonlexical = bool(nonlexical_terms) and not lexical_terms
    return {
        "acoustic_concepts": sorted(acoustic_concepts),
        "human_vocalization_terms": human_terms,
        "nonlexical_terms": nonlexical_terms,
        "lexical_speech_terms": lexical_terms,
        "clearly_nonlexical_non_speech": clearly_nonlexical,
    }


def asr_vocalization_quarantine_audit(
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
    *,
    transcripts_by_clip: Mapping[str, str],
) -> dict[str, Any]:
    analysis_by_clip = {
        clip_key: degenerate_asr_analysis(transcript)
        for clip_key, transcript in transcripts_by_clip.items()
    }
    findings = []
    quarantined = []
    field_results = {}
    rows = [
        {
            "key": str(row["query_key"]),
            "clip_key": row["clip_key"],
            "text": str(row["query_text"]),
        }
        for row in queries
        if row["query_kind"] == "ambient"
    ] + [
        {
            "key": str(row["description_key"]),
            "clip_key": row["clip_key"],
            "text": str(row["description_text"]),
        }
        for row in descriptions
        if row["description_kind"] == "ambient"
    ]
    for row in rows:
        analysis = analysis_by_clip.get(str(row["clip_key"]), {})
        policy = _human_vocalization_policy(row["text"])
        human_vocalization = bool(policy["human_vocalization_terms"])
        lexical_speech = bool(policy["lexical_speech_terms"])
        degenerate_human_vocalization = bool(
            analysis.get("degenerate") and human_vocalization
        )
        quarantine = lexical_speech or degenerate_human_vocalization
        passed = not lexical_speech and (
            not degenerate_human_vocalization
            or policy["clearly_nonlexical_non_speech"]
        )
        field_results[row["key"]] = {
            "status": "PASS" if passed else "FAIL",
            "clip_asr_degenerate": bool(analysis.get("degenerate")),
            "lexical_speech_fail_closed": lexical_speech,
            "policy": policy,
        }
        if quarantine:
            quarantined.append(row["key"])
        if not passed:
            findings.append(
                {
                    "kind": (
                        "lexical_speech_forbidden"
                        if lexical_speech
                        else "degenerate_asr_human_vocalization_quarantine"
                    ),
                    "key": row["key"],
                    "clip_key": row["clip_key"],
                    "asr_reasons": analysis.get("reasons", []),
                    "policy": policy,
                }
            )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "quarantined_field_keys": quarantined,
        "field_results": field_results,
        "analysis_by_clip": analysis_by_clip,
        "thresholds": {
            "low_unique_token_ratio": ASR_LOW_UNIQUE_TOKEN_RATIO,
            "low_unique_token_min_tokens": ASR_LOW_UNIQUE_TOKEN_MIN_TOKENS,
            "repeated_vocalization_min_count": (
                ASR_REPEATED_VOCALIZATION_MIN_COUNT
            ),
            "repeated_vocalization_dominance": (
                ASR_REPEATED_VOCALIZATION_DOMINANCE
            ),
        },
    }


def standalone_reference_audit(
    queries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    findings = []
    field_results = {}
    for row in queries:
        if row["query_scope"] != "handle":
            continue
        text = str(row["query_text"])
        words = set(_normalized_words(text))
        unresolved = sorted(words & UNRESOLVED_REFERENCE_TERMS)
        if DEFINITE_HUMAN_START_RE.search(text):
            unresolved.append("definite_human_anaphora")
        unresolved = sorted(set(unresolved))
        field_results[str(row["query_key"])] = {
            "status": "PASS" if not unresolved else "FAIL",
            "unresolved_terms": unresolved,
        }
        if unresolved:
            findings.append(
                {
                    "kind": "unresolved_handle_reference",
                    "query_key": row["query_key"],
                    "literals": unresolved,
                }
            )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "field_results": field_results,
    }


def _ordered_component_coverage(
    family_text: str, component_texts: Sequence[str]
) -> tuple[bool, list[dict[str, Any]]]:
    family_words = _normalized_words(family_text)
    cursor = 0
    results = []
    passed = True
    for ordinal, text in enumerate(component_texts, 1):
        component_words = [
            word
            for word in dict.fromkeys(_normalized_words(text))
            if len(word) >= 4
            and word
            not in {
                "with",
                "from",
                "into",
                "during",
                "person",
                "object",
                "item",
                "hand",
            }
        ]
        required = min(2, len(component_words))
        positions = [
            index
            for index, word in enumerate(family_words[cursor:], cursor)
            if word in component_words
        ]
        covered = (
            len({family_words[index] for index in positions}) >= required
        )
        first_position = min(positions) if positions else None
        if not covered:
            passed = False
        elif first_position is not None:
            cursor = first_position + 1
        results.append(
            {
                "ordinal": ordinal,
                "required_distinct_tokens": required,
                "covered": covered,
                "first_position": first_position,
            }
        )
    return passed, results


def _acoustic_concepts(text: str) -> set[str]:
    return set(_acoustic_context_evidence(text)["concepts"])


def _visual_component_coverage(
    family_text: str, component_text: str
) -> dict[str, Any]:
    ignored = {
        "with",
        "from",
        "into",
        "during",
        "person",
        "object",
        "item",
        "hand",
        "operator",
        "someone",
        "worker",
    }
    component_tokens = {
        word
        for word in _normalized_words(component_text)
        if len(word) >= 4 and word not in ignored
    }
    overlap = sorted(component_tokens & set(_normalized_words(family_text)))
    required = min(2, len(component_tokens))
    return {
        "required_distinct_tokens": required,
        "overlap_tokens": overlap,
        "covered": required > 0 and len(overlap) >= required,
    }


def _ambient_component_coverage(
    family_text: str, component_text: str
) -> dict[str, Any]:
    component_concepts = _acoustic_concepts(component_text)
    family_concepts = _acoustic_concepts(family_text)
    overlap = sorted(component_concepts & family_concepts)
    return {
        "component_acoustic_concepts": sorted(component_concepts),
        "family_acoustic_concepts": sorted(family_concepts),
        "overlap_concepts": overlap,
        "covered": bool(component_concepts and overlap),
    }


def _entity_candidate_tokens(text: str) -> set[str]:
    ignored = {
        "after",
        "before",
        "brief",
        "changes",
        "changing",
        "during",
        "followed",
        "follows",
        "motion",
        "moves",
        "moving",
        "numbered",
        "phase",
        "stage",
        "steady",
        "then",
        "through",
        "while",
        *GENERIC_ACOUSTIC_TERMS,
        *AGENT_TERMS,
    }
    acoustic = _acoustic_concepts(text)
    return {
        word
        for word in _normalized_words(text)
        if len(word) >= 4
        and not word.isdigit()
        and word not in ignored
        and word not in acoustic
    }


def _unsupported_continuity_evidence(
    text: str,
    component_visual_texts: Sequence[str] = (),
    *,
    reject_agent_terms: bool = True,
    reject_reused_entities: bool = True,
) -> dict[str, Any]:
    words = set(_normalized_words(text))
    pattern_matches = [
        pattern.pattern
        for pattern in UNSUPPORTED_CONTINUITY_PATTERNS
        if pattern.search(text)
    ]
    reference_terms = sorted(words & CONTINUITY_REFERENCE_TERMS)
    agent_terms = sorted(words & AGENT_TERMS)
    component_entities = [
        _entity_candidate_tokens(component)
        for component in component_visual_texts
    ]
    shared_component_entities = (
        set.intersection(*component_entities)
        if len(component_entities) >= 2
        else set()
    )
    reused_entity_terms = sorted(
        shared_component_entities & set(_normalized_words(text))
    )
    unsupported_agent_bridge = reject_agent_terms and bool(agent_terms)
    unsupported_reused_entities = (
        reject_reused_entities and bool(reused_entity_terms)
    )
    return {
        "pattern_matches": pattern_matches,
        "continuity_reference_terms": reference_terms,
        "agent_terms": agent_terms,
        "unsupported_agent_bridge": unsupported_agent_bridge,
        "shared_component_entity_terms": sorted(shared_component_entities),
        "reused_entity_terms": reused_entity_terms,
        "unsupported_reused_entities": unsupported_reused_entities,
        "unsupported": bool(
            pattern_matches
            or reference_terms
            or unsupported_agent_bridge
            or unsupported_reused_entities
        ),
    }


def _relation_only_text(
    text: str, component_local_texts: Sequence[str]
) -> str:
    """Remove exact local source spans before relation-level continuity."""

    relation_only = text
    for component_text in sorted(
        (value for value in component_local_texts if value),
        key=len,
        reverse=True,
    ):
        relation_only = relation_only.replace(component_text, " ")
    return " ".join(relation_only.split())


def _local_possessive_coreference_analysis(
    text: str,
) -> tuple[list[dict[str, str]], set[str]]:
    """Find clause-local possessives with an explicit local human antecedent."""

    exemptions = []
    unexempted_terms = set()
    for clause in LOCAL_CLAUSE_SPLIT_RE.split(text):
        if not clause.strip():
            continue
        bridged = bool(LOCAL_POSSESSIVE_EXEMPTION_BRIDGE_RE.search(clause))
        antecedents = list(LOCAL_AGENT_ANTECEDENT_RE.finditer(clause))
        for possessive in LOCAL_POSSESSIVE_DETERMINER_RE.finditer(clause):
            term = possessive.group(0).split()[0].casefold()
            eligible_antecedents = [
                antecedent
                for antecedent in antecedents
                if antecedent.end() <= possessive.start()
            ]
            if bridged or not eligible_antecedents:
                unexempted_terms.add(term)
                continue
            exemptions.append(
                {
                    "term": term,
                    "antecedent": eligible_antecedents[-1].group(0).casefold(),
                    "clause": clause.strip(),
                }
            )
        possessive_determiner_starts = {
            match.start()
            for match in LOCAL_POSSESSIVE_DETERMINER_RE.finditer(clause)
        }
        for reference in re.finditer(
            r"\b(?:her|his|their)\b", clause, re.IGNORECASE
        ):
            if reference.start() not in possessive_determiner_starts:
                unexempted_terms.add(reference.group(0).casefold())
    return exemptions, unexempted_terms


def _local_visual_pronoun_coreference_analysis(
    text: str,
) -> tuple[list[dict[str, str]], set[str]]:
    """Allow only a narrow sentence-local locative ``it`` reference."""

    exemptions = []
    unexempted_terms = set()
    for clause in LOCAL_CLAUSE_SPLIT_RE.split(text):
        if not clause.strip():
            continue
        bridged = bool(LOCAL_POSSESSIVE_EXEMPTION_BRIDGE_RE.search(clause))
        antecedents = list(LOCAL_NOUN_ANTECEDENT_RE.finditer(clause))
        exempted_starts = set()
        for reference in LOCAL_LOCATIVE_PRONOUN_RE.finditer(clause):
            term = reference.group("term").casefold()
            eligible_antecedents = [
                antecedent
                for antecedent in antecedents
                if antecedent.end() <= reference.start()
            ]
            if bridged or not eligible_antecedents:
                unexempted_terms.add(term)
                continue
            antecedent = eligible_antecedents[-1]
            antecedent_mentions = list(
                re.finditer(
                    r"\b(?:a|an|the)\s+"
                    r"(?P<noun>[a-z0-9]+(?:'[a-z0-9]+)?)\b",
                    antecedent.group(0),
                    re.IGNORECASE,
                )
            )
            antecedent_mention = (
                antecedent_mentions[-1]
                if antecedent_mentions
                else None
            )
            exempted_starts.add(reference.start("term"))
            exemptions.append(
                {
                    "term": term,
                    "antecedent": (
                        antecedent_mention.group(0).casefold()
                        if antecedent_mention is not None
                        else antecedent.group(0).casefold()
                    ),
                    "antecedent_noun": (
                        antecedent_mention.group("noun").casefold()
                        if antecedent_mention is not None
                        else antecedent.group("phrase")
                        .split()[-1]
                        .casefold()
                    ),
                    "preposition": reference.group("preposition").casefold(),
                    "clause": clause.strip(),
                }
            )
        for reference in re.finditer(r"\bit\b", clause, re.IGNORECASE):
            if reference.start() not in exempted_starts:
                unexempted_terms.add("it")
    return exemptions, unexempted_terms


def _component_local_continuity_evidence(text: str) -> dict[str, Any]:
    """Reject bridges with narrow sentence-local coreference exemptions."""

    evidence = _unsupported_continuity_evidence(
        text,
        reject_agent_terms=False,
        reject_reused_entities=False,
    )
    exemptions, unexempted_possessives = (
        _local_possessive_coreference_analysis(text)
    )
    pronoun_exemptions, unexempted_pronouns = (
        _local_visual_pronoun_coreference_analysis(text)
    )
    exempt_terms = {row["term"] for row in exemptions}
    reference_terms = [
        term
        for term in evidence["continuity_reference_terms"]
        if (
            (
                term not in LOCAL_POSSESSIVE_REFERENCE_TERMS
                or term not in exempt_terms
                or term in unexempted_possessives
            )
            and not (
                term == "it"
                and pronoun_exemptions
                and term not in unexempted_pronouns
            )
        )
    ]
    evidence["local_possessive_coreference_exemptions"] = exemptions
    evidence["local_visual_pronoun_coreference_exemptions"] = (
        pronoun_exemptions
    )
    evidence["continuity_reference_terms"] = reference_terms
    evidence["unsupported"] = bool(
        evidence["pattern_matches"]
        or reference_terms
        or evidence["unsupported_agent_bridge"]
        or evidence["unsupported_reused_entities"]
    )
    return evidence


def far_composition_audit(
    structural: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    queries_by_family = defaultdict(list)
    for row in queries:
        queries_by_family[str(row["family_key"])].append(row)
    descriptions_by_family = defaultdict(list)
    for row in descriptions:
        descriptions_by_family[str(row["family_key"])].append(row)
    findings = []
    field_results = {}
    for family in structural["families"]:
        if family["shape"] != "two_component_ordered":
            continue
        rows = queries_by_family[str(family["family_key"])]
        component_rows = []
        for ordinal, interval in enumerate(family["intervals"], 1):
            clip_key = str(interval["clip_key"])
            visual_row = next(
                row
                for row in rows
                if row["query_kind"] == "visual"
                and str(row["clip_key"]) == clip_key
            )
            ambient_row = next(
                row
                for row in rows
                if row["query_kind"] == "ambient"
                and str(row["clip_key"]) == clip_key
            )
            component_rows.append(
                {
                    "ordinal": ordinal,
                    "visual_text": str(visual_row["query_text"]),
                    "ambient_text": str(ambient_row["query_text"]),
                }
            )
        family_row = next(
            row for row in rows if row["query_kind"] == "family_compositional"
        )
        composition_fields = [
            (str(family_row["query_key"]), str(family_row["query_text"]))
        ]
        family_descriptions = descriptions_by_family[str(family["family_key"])]
        if family_descriptions:
            family_description = next(
                row
                for row in family_descriptions
                if row["description_kind"] == "family_compositional"
            )
            description_components = []
            for component, interval in zip(
                component_rows, family["intervals"], strict=True
            ):
                clip_key = str(interval["clip_key"])
                description_components.append(
                    {
                        **component,
                        "visual_text": str(
                            next(
                                row["description_text"]
                                for row in family_descriptions
                                if row["description_kind"] == "visual"
                                and str(row["clip_key"]) == clip_key
                            )
                        ),
                        "ambient_text": str(
                            next(
                                row["description_text"]
                                for row in family_descriptions
                                if row["description_kind"] == "ambient"
                                and str(row["clip_key"]) == clip_key
                            )
                        ),
                    }
                )
            composition_fields.append(
                (
                    str(family_description["description_key"]),
                    str(family_description["description_text"]),
                )
            )
        else:
            description_components = component_rows

        for field_index, (field_key, text) in enumerate(composition_fields):
            sources = (
                component_rows if field_index == 0 else description_components
            )
            component_local_texts = [
                str(row[field])
                for row in sources
                for field in ("visual_text", "ambient_text")
            ]
            ordered_visual, ordered_rows = _ordered_component_coverage(
                text, [row["visual_text"] for row in sources]
            )
            component_coverage = [
                {
                    "ordinal": row["ordinal"],
                    "visual": _visual_component_coverage(
                        text, row["visual_text"]
                    ),
                    "ambient": _ambient_component_coverage(
                        text, row["ambient_text"]
                    ),
                }
                for row in sources
            ]
            all_visual = ordered_visual and all(
                row["visual"]["covered"] for row in component_coverage
            )
            all_ambient = all(
                row["ambient"]["covered"] for row in component_coverage
            )
            relation_only = _relation_only_text(
                text, component_local_texts
            )
            continuity = _unsupported_continuity_evidence(
                relation_only,
                [row["visual_text"] for row in sources],
                reject_agent_terms=False,
                reject_reused_entities=False,
            )
            continuity["relation_only_text"] = relation_only
            continuity["component_local_spans_removed"] = len(
                component_local_texts
            )
            passed = all_visual and all_ambient and not continuity["unsupported"]
            field_results[field_key] = {
                "status": "PASS" if passed else "FAIL",
                "ordered_visual_coverage": ordered_rows,
                "component_coverage": component_coverage,
                "all_components_visual_covered": all_visual,
                "all_components_ambient_covered": all_ambient,
                "continuity_evidence": continuity,
            }
            if not passed:
                findings.append(
                    {
                        "kind": "far_family_semantic_contract",
                        "field_key": field_key,
                        "ordered_components_present": all_visual,
                        "all_components_ambient_present": all_ambient,
                        "non_speech_relation_present": all_ambient,
                        "unsupported_patterns": continuity["pattern_matches"],
                        "unsupported_continuity": continuity,
                        "coverage": component_coverage,
                    }
                )
        if family_descriptions:
            expected_clauses = [
                {
                    "ordinal": row["ordinal"],
                    "visual_summary": row["visual_text"],
                    "ambient_summary": row["ambient_text"],
                }
                for row in description_components
            ]
            clause_sources = [
                (
                    str(family_row["query_key"]),
                    family_row.get("composition_clauses"),
                ),
                (
                    str(family_description["description_key"]),
                    family_description.get("composition_clauses"),
                ),
            ]
            for field_key, clauses in clause_sources:
                local_results = []
                binding_passed = (
                    isinstance(clauses, list)
                    and len(clauses) == len(expected_clauses)
                )
                observed_clauses = clauses if isinstance(clauses, list) else []
                for expected, clause in zip(
                    expected_clauses, observed_clauses, strict=False
                ):
                    if not isinstance(clause, Mapping):
                        binding_passed = False
                        local_results.append(
                            {
                                "expected_ordinal": expected["ordinal"],
                                "binding_status": "FAIL",
                                "coverage_status": "NOT_EVALUATED",
                                "local_reference_status": "NOT_EVALUATED",
                                "reason": "clause_not_object",
                            }
                        )
                        continue
                    visual_observed = _normalized_text(
                        str(clause.get("visual_summary", ""))
                    )
                    visual_expected = _normalized_text(
                        expected["visual_summary"]
                    )
                    ambient_observed = _normalized_text(
                        str(clause.get("ambient_summary", ""))
                    )
                    ambient_expected = _normalized_text(
                        expected["ambient_summary"]
                    )
                    ordinal_equal = (
                        clause.get("ordinal") == expected["ordinal"]
                    )
                    visual_hash_equal = semantic_hash(
                        visual_observed
                    ) == semantic_hash(visual_expected)
                    ambient_hash_equal = semantic_hash(
                        ambient_observed
                    ) == semantic_hash(ambient_expected)
                    exact_keys = set(clause) == {
                        "ordinal",
                        "visual_summary",
                        "ambient_summary",
                    }
                    binding_ok = (
                        exact_keys
                        and ordinal_equal
                        and visual_observed == visual_expected
                        and ambient_observed == ambient_expected
                        and visual_hash_equal
                        and ambient_hash_equal
                    )
                    visual_coverage = _visual_component_coverage(
                        str(clause.get("visual_summary", "")),
                        expected["visual_summary"],
                    )
                    ambient_coverage = _ambient_component_coverage(
                        str(clause.get("ambient_summary", "")),
                        expected["ambient_summary"],
                    )
                    coverage_ok = (
                        visual_coverage["covered"]
                        and ambient_coverage["covered"]
                    )
                    local_reference = _component_local_continuity_evidence(
                        " ".join(
                            (
                                str(clause.get("visual_summary", "")),
                                str(clause.get("ambient_summary", "")),
                            )
                        )
                    )
                    local_reference_ok = not local_reference["unsupported"]
                    local_results.append(
                        {
                            "expected_ordinal": expected["ordinal"],
                            "observed_ordinal": clause.get("ordinal"),
                            "binding_status": (
                                "PASS" if binding_ok else "FAIL"
                            ),
                            "coverage_status": (
                                "PASS" if coverage_ok else "FAIL"
                            ),
                            "local_reference_status": (
                                "PASS" if local_reference_ok else "FAIL"
                            ),
                            "exact_key_set": exact_keys,
                            "ordinal_equal": ordinal_equal,
                            "visual_normalized_equal": (
                                visual_observed == visual_expected
                            ),
                            "ambient_normalized_equal": (
                                ambient_observed == ambient_expected
                            ),
                            "visual_hash_equal": visual_hash_equal,
                            "ambient_hash_equal": ambient_hash_equal,
                            "expected_visual_sha256": semantic_hash(
                                visual_expected
                            ),
                            "observed_visual_sha256": semantic_hash(
                                visual_observed
                            ),
                            "expected_ambient_sha256": semantic_hash(
                                ambient_expected
                            ),
                            "observed_ambient_sha256": semantic_hash(
                                ambient_observed
                            ),
                            "coverage_source_policy": (
                                "accepted_descriptions_only"
                            ),
                            "visual_coverage": visual_coverage,
                            "ambient_coverage": ambient_coverage,
                            "local_reference": local_reference,
                        }
                    )
                    binding_passed = binding_passed and binding_ok
                coverage_passed = bool(local_results) and all(
                    row.get("coverage_status") == "PASS"
                    for row in local_results
                )
                local_reference_passed = bool(local_results) and all(
                    row.get("local_reference_status") == "PASS"
                    for row in local_results
                )
                field_results[f"{field_key}:component_local_binding"] = {
                    "status": "PASS" if binding_passed else "FAIL",
                    "error_code": (
                        None if binding_passed else "BINDING_MISMATCH"
                    ),
                    "description_projection_exact": True,
                    "clauses": local_results,
                }
                field_results[f"{field_key}:component_local_coverage"] = {
                    "status": "PASS" if coverage_passed else "FAIL",
                    "error_code": (
                        None if coverage_passed else "COVERAGE_INVALID"
                    ),
                    "source_policy": "accepted_descriptions_only",
                    "clauses": local_results,
                }
                field_results[f"{field_key}:component_local_reference"] = {
                    "status": (
                        "PASS" if local_reference_passed else "FAIL"
                    ),
                    "error_code": (
                        None
                        if local_reference_passed
                        else "LOCAL_REFERENCE_INVALID"
                    ),
                    "clauses": local_results,
                }
                if not binding_passed:
                    findings.append(
                        {
                            "kind": "far_family_component_local_binding",
                            "error_code": "BINDING_MISMATCH",
                            "family_key": family["family_key"],
                            "field_key": field_key,
                            "binding_source": (
                                "accepted_description_projection"
                            ),
                            "coverage": local_results,
                        }
                    )
                if not coverage_passed:
                    findings.append(
                        {
                            "kind": "far_family_component_local_coverage",
                            "error_code": "COVERAGE_INVALID",
                            "family_key": family["family_key"],
                            "field_key": field_key,
                            "source_policy": "accepted_descriptions_only",
                            "coverage": local_results,
                        }
                    )
                if not local_reference_passed:
                    findings.append(
                        {
                            "kind": "far_family_component_local_reference",
                            "error_code": "LOCAL_REFERENCE_INVALID",
                            "family_key": family["family_key"],
                            "field_key": field_key,
                            "clauses": local_results,
                        }
                    )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "field_results": field_results,
    }


def cross_kind_component_audit(
    queries: Sequence[Mapping[str, Any]],
    *,
    embed_visual: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    embed_ambient: Callable[[Sequence[str]], Sequence[Sequence[float]]],
) -> dict[str, Any]:
    by_component = defaultdict(dict)
    for row in queries:
        if row["query_scope"] == "handle":
            by_component[
                (str(row["family_key"]), str(row["clip_key"]))
            ][str(row["query_kind"])] = row
    findings = []
    field_results = {}
    for (family_key, clip_key), rows in sorted(by_component.items()):
        if set(rows) != {"visual", "ambient"}:
            raise AuthoringError("CROSS_KIND_COMPONENT_PAIR_MISSING")
        visual = rows["visual"]
        ambient = rows["ambient"]
        visual_text = str(visual["query_text"])
        ambient_text = str(ambient["query_text"])
        jaccard, shared = _token_jaccard(visual_text, ambient_text)
        siglip_vectors = list(embed_visual([visual_text, ambient_text]))
        clap_vectors = list(embed_ambient([visual_text, ambient_text]))
        if len(siglip_vectors) != 2 or len(clap_vectors) != 2:
            raise AuthoringError("CROSS_KIND_EMBEDDING_COUNT_MISMATCH")
        siglip = _cosine(siglip_vectors[0], siglip_vectors[1])
        clap = _cosine(clap_vectors[0], clap_vectors[1])
        embedding_fail = (
            siglip >= CROSS_KIND_EMBEDDING_THRESHOLD
            and clap >= CROSS_KIND_EMBEDDING_THRESHOLD
        ) or max(siglip, clap) >= CROSS_KIND_SINGLE_ENCODER_THRESHOLD
        lexical_fail = shared >= 4 and jaccard >= CROSS_KIND_LEXICAL_THRESHOLD
        passed = not lexical_fail and not embedding_fail
        evidence = {
            "family_key": family_key,
            "clip_key": clip_key,
            "visual_query_key": visual["query_key"],
            "ambient_query_key": ambient["query_key"],
            "jaccard": round(jaccard, 8),
            "shared_token_count": shared,
            "siglip_cosine": round(siglip, 8),
            "clap_cosine": round(clap, 8),
        }
        for query_key in (visual["query_key"], ambient["query_key"]):
            field_results[str(query_key)] = {
                "status": "PASS" if passed else "FAIL",
                **evidence,
            }
        if not passed:
            findings.append(
                {
                    "kind": "cross_kind_visual_ambient_paraphrase",
                    **evidence,
                }
            )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "field_results": field_results,
        "thresholds": {
            "lexical_jaccard": CROSS_KIND_LEXICAL_THRESHOLD,
            "lexical_min_shared_tokens": 4,
            "both_encoder_cosine": CROSS_KIND_EMBEDDING_THRESHOLD,
            "single_encoder_cosine": CROSS_KIND_SINGLE_ENCODER_THRESHOLD,
        },
        "query_embeddings_persisted": False,
    }


def query_description_identity_audit(
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    descriptions_by_key = {
        (
            str(row["family_key"]),
            str(row["clip_key"]),
            str(row["description_kind"]),
        ): row
        for row in descriptions
    }
    findings = []
    field_results = {}
    for query in queries:
        description = descriptions_by_key[
            (
                str(query["family_key"]),
                str(query["clip_key"]),
                str(query["query_kind"]),
            )
        ]
        normalized_equal = _normalized_text(
            str(query["query_text"])
        ) == _normalized_text(str(description["description_text"]))
        similarity, shared = _token_jaccard(
            str(query["query_text"]), str(description["description_text"])
        )
        token_sets_equal = (
            bool(_normalized_words(str(query["query_text"])))
            and set(_normalized_words(str(query["query_text"])))
            == set(_normalized_words(str(description["description_text"])))
        )
        failed = normalized_equal or token_sets_equal or (
            shared >= 2 and similarity >= QUERY_DESCRIPTION_IDENTITY_THRESHOLD
        )
        evidence = {
            "query_key": query["query_key"],
            "description_key": description["description_key"],
            "normalized_equal": normalized_equal,
            "token_sets_equal": token_sets_equal,
            "jaccard": round(similarity, 8),
            "shared_token_count": shared,
        }
        field_results[str(query["query_key"])] = {
            "status": "FAIL" if failed else "PASS",
            **evidence,
        }
        field_results[str(description["description_key"])] = {
            "status": "FAIL" if failed else "PASS",
            **evidence,
        }
        if failed:
            findings.append(
                {"kind": "query_description_identity", **evidence}
            )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "field_results": field_results,
        "threshold": QUERY_DESCRIPTION_IDENTITY_THRESHOLD,
        "minimum_shared_tokens": 2,
    }


def embedding_collision_findings(
    queries: Sequence[Mapping[str, Any]],
    *,
    embed_visual: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    embed_ambient: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    threshold: float = EMBEDDING_COLLISION_THRESHOLD,
) -> dict[str, Any]:
    """Audit query-only embeddings; no target or non-target vectors are read."""

    groups = {
        "visual_encoder": [
            row
            for row in queries
            if row["query_kind"] in {"visual", "family_compositional"}
        ],
        "ambient_encoder": [
            row
            for row in queries
            if row["query_kind"] in {"ambient", "family_compositional"}
        ],
    }
    encoders = {
        "visual_encoder": embed_visual,
        "ambient_encoder": embed_ambient,
    }
    findings: list[dict[str, Any]] = []
    maxima: dict[str, Any] = {}
    for encoder_name, rows in groups.items():
        vectors = list(
            encoders[encoder_name](
                [str(row["query_text"]) for row in rows]
            )
        )
        if len(vectors) != len(rows):
            raise AuthoringError("AUDIT_EMBEDDING_COUNT_MISMATCH")
        best: dict[str, Any] | None = None
        for left_index, left in enumerate(rows):
            for right_index in range(left_index + 1, len(rows)):
                right = rows[right_index]
                if left["query_kind"] != right["query_kind"]:
                    continue
                similarity = _cosine(
                    vectors[left_index], vectors[right_index]
                )
                candidate = {
                    "encoder": encoder_name,
                    "query_kind": left["query_kind"],
                    "left_query_key": left["query_key"],
                    "right_query_key": right["query_key"],
                    "cosine": round(similarity, 8),
                }
                if best is None or candidate["cosine"] > best["cosine"]:
                    best = candidate
                if similarity >= threshold:
                    findings.append(
                        {"kind": "embedding_near_collision", **candidate}
                    )
        maxima[encoder_name] = best
    return {
        "threshold": threshold,
        "findings": findings,
        "maximum_pair_by_encoder": maxima,
        "query_embeddings_persisted": False,
        "target_embeddings_read": False,
        "non_target_embeddings_read": False,
    }


def audit_authored_content(
    structural: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
    *,
    transcripts_by_clip: Mapping[str, str],
    embed_visual: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    embed_ambient: Callable[[Sequence[str]], Sequence[Sequence[float]]],
) -> dict[str, Any]:
    slot_names = {
        row["family_key"]: row["slot_names"]
        for row in structural["families"]
    }
    text_rows = [
        {
            "key": row["query_key"],
            "family_key": row["family_key"],
            "clip_key": row["clip_key"],
            "text": row["query_text"],
        }
        for row in queries
    ] + [
        {
            "key": (
                f"description:{row['family_key']}:"
                f"{row['clip_key']}:{row['description_kind']}"
            ),
            "family_key": row["family_key"],
            "clip_key": row["clip_key"],
            "text": row["description_text"],
        }
        for row in descriptions
    ]
    literal = literal_leakage_findings(
        text_rows,
        transcripts_by_clip=transcripts_by_clip,
        slot_names_by_family=slot_names,
    )
    lexical = lexical_collision_findings(queries)
    embedding = embedding_collision_findings(
        queries,
        embed_visual=embed_visual,
        embed_ambient=embed_ambient,
    )
    ambient_grounding = ambient_acoustic_grounding_audit(
        queries,
        descriptions,
        embed_ambient=embed_ambient,
    )
    asr_quarantine = asr_vocalization_quarantine_audit(
        queries,
        descriptions,
        transcripts_by_clip=transcripts_by_clip,
    )
    cross_kind = cross_kind_component_audit(
        queries,
        embed_visual=embed_visual,
        embed_ambient=embed_ambient,
    )
    standalone = standalone_reference_audit(queries)
    far_composition = far_composition_audit(
        structural, queries, descriptions
    )
    query_description = query_description_identity_audit(
        queries, descriptions
    )
    family_queries = [
        row for row in queries if row["query_scope"] == "family"
    ]
    family_normalized = [
        _normalized_text(str(row["query_text"])) for row in family_queries
    ]
    family_unique = (
        len(family_queries) == EXPECTED_FAMILIES
        and len(set(family_normalized)) == EXPECTED_FAMILIES
    )
    invalid_primary_status = [
        row["query_key"]
        for row in queries
        if row.get("template_only_control") is not False
        or row.get("human_grounded") is not False
        or row.get("machine_observation_status")
        != "PENDING_MACHINE_SEMANTIC_GATES"
        or set(row.get("field_gate_status", {})) != set(SEMANTIC_GATE_NAMES)
    ]
    failures = []
    if literal:
        failures.append("LITERAL_LEAKAGE")
    if lexical:
        failures.append("DUPLICATE_OR_LEXICAL_COLLISION")
    if embedding["findings"]:
        failures.append("EMBEDDING_COLLISION")
    if ambient_grounding["findings"]:
        failures.append("AMBIENT_ACOUSTIC_GROUNDING")
    if asr_quarantine["findings"]:
        failures.append("DEGENERATE_ASR_VOCALIZATION_QUARANTINE")
    if cross_kind["findings"]:
        failures.append("CROSS_KIND_VISUAL_AMBIENT_PARAPHRASE")
    if standalone["findings"]:
        failures.append("UNRESOLVED_HANDLE_REFERENCE")
    if far_composition["findings"]:
        failures.append("FAR_FAMILY_SEMANTIC_CONTRACT")
    if query_description["findings"]:
        failures.append("QUERY_DESCRIPTION_IDENTITY")
    if not family_unique:
        failures.append("FAMILY_QUERY_UNIQUENESS")
    if invalid_primary_status:
        failures.append("TEMPLATE_ONLY_QUERY_IN_PRIMARY_SET")
    if len(queries) != EXPECTED_QUERY_COUNT:
        failures.append("QUERY_COUNT")
    gate_audits = {
        "ambient_acoustic_grounding": ambient_grounding,
        "asr_vocalization_quarantine": asr_quarantine,
        "cross_kind_distinctness": cross_kind,
        "far_composition": far_composition,
        "standalone_reference": standalone,
        "query_description_identity": query_description,
    }
    _apply_machine_gate_statuses(
        queries,
        descriptions,
        gate_audits=gate_audits,
    )
    return {
        "schema_version": "av-trace.p23-102-query-authoring-audit/3.0",
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "failures": failures,
        "literal_leakage": {
            "status": "PASS" if not literal else "FAIL",
            "findings": literal,
            "copied_asr_ngram_size": 4,
        },
        "duplicates_and_lexical_collisions": {
            "status": "PASS" if not lexical else "FAIL",
            "findings": lexical,
            "threshold": LEXICAL_COLLISION_THRESHOLD,
        },
        "embedding_similarity": embedding,
        "semantic_authoring_gates": gate_audits,
        "family_query_uniqueness": {
            "status": "PASS" if family_unique else "FAIL",
            "family_query_count": len(family_queries),
            "unique_normalized_family_query_count": len(
                set(family_normalized)
            ),
        },
        "template_only_primary_queries": invalid_primary_status,
    }


def _apply_machine_gate_statuses(
    queries: Sequence[Mapping[str, Any]],
    descriptions: Sequence[Mapping[str, Any]],
    *,
    gate_audits: Mapping[str, Mapping[str, Any]],
) -> None:
    """Attach machine-only field status after all frozen gates have run."""

    for row in [*queries, *descriptions]:
        key = str(row.get("query_key") or row.get("description_key"))
        statuses: dict[str, str] = {}
        for gate_name in SEMANTIC_GATE_NAMES:
            field_result = gate_audits[gate_name].get(
                "field_results", {}
            ).get(key)
            statuses[gate_name] = (
                str(field_result["status"]) if field_result else "NOT_APPLICABLE"
            )
        passed = all(
            status in {"PASS", "NOT_APPLICABLE"}
            for status in statuses.values()
        )
        row["field_gate_status"] = statuses
        row["machine_observation_status"] = (
            "MACHINE_GATES_PASSED"
            if passed
            else "MACHINE_GATES_FAILED_CLOSED"
        )
        row["human_grounded"] = False


def explicit_template_baseline(structural: Mapping[str, Any]) -> dict[str, Any]:
    """Return an explicit, excluded baseline; never mix it into primary queries."""

    rows = []
    for family in structural["families"]:
        rows.append(
            {
                "family_key": family["family_key"],
                "baseline_text": (
                    "Describe the observable state transition and the "
                    "localized non-speech event that accompanies it."
                    if family["shape"] == "one_component"
                    else (
                        "Describe the ordered observable states and the "
                        "localized non-speech relation between them."
                    )
                ),
                "content_grounded": False,
                "template_only_control": True,
                "eligible_for_primary_query_set": False,
                "eligible_for_scientific_scoring": False,
            }
        )
    return {
        "schema_version": (
            "av-trace.p23-102-explicit-template-baseline/2.0"
        ),
        "baseline_id": "EXPLICIT_TEMPLATE_ONLY_BASELINE",
        "excluded_from_primary_queries": True,
        "rows": rows,
    }


def _required_snapshot_files(snapshot: Path) -> tuple[str, ...]:
    if snapshot == OMNI_SNAPSHOT:
        return (
            "LOCAL_MANIFEST.json",
            "SHA256SUMS",
            "config.json",
            "model.safetensors.index.json",
            "tokenizer.json",
            "preprocessor_config.json",
        )
    if snapshot == WHISPER_SNAPSHOT:
        return ("config.json", "preprocessor_config.json")
    if snapshot in {SIGLIP_SNAPSHOT, CLAP_SNAPSHOT}:
        return ("SHA256SUMS", "config.json", "preprocessor_config.json")
    raise AuthoringError("UNKNOWN_MODEL_SNAPSHOT")


def snapshot_availability(root: Path, snapshot: Path) -> dict[str, Any]:
    path = _repo_path(root, snapshot)
    required = _required_snapshot_files(snapshot)
    missing = [name for name in required if not (path / name).is_file()]
    weight_files = sorted(
        item.name
        for item in path.glob("*")
        if item.suffix in {".bin", ".safetensors"}
    )
    if not weight_files:
        missing.append("<model weights>")
    return {
        "path": str(snapshot),
        "available": not missing,
        "missing": missing,
        "required_files": list(required),
        "weight_file_count": len(weight_files),
        "config_sha256": (
            "sha256:" + file_sha256(path / "config.json")
            if (path / "config.json").is_file()
            else None
        ),
    }


def preflight(
    root: Path = ROOT,
    *,
    bundle: Path = DEFAULT_BUNDLE,
    media: Path = DEFAULT_MEDIA,
) -> dict[str, Any]:
    structural = load_structural_bundle(root, bundle)
    media_path = _repo_path(root, media)
    models = {
        name: snapshot_availability(root, path)
        for name, path in (
            ("authoring_omni", OMNI_SNAPSHOT),
            ("asr_leakage_whisper", WHISPER_SNAPSHOT),
            ("visual_text_audit_siglip2", SIGLIP_SNAPSHOT),
            ("ambient_text_audit_clap", CLAP_SNAPSHOT),
        )
    }
    failures = []
    if not media_path.is_file():
        failures.append("SOURCE_MEDIA_MISSING")
    if any(not row["available"] for row in models.values()):
        failures.append("LOCAL_MODEL_UNAVAILABLE")
    try:
        import av  # noqa: F401
        import numpy  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        failures.append(f"PYTHON_RUNTIME_UNAVAILABLE:{type(exc).__name__}")
    return {
        "schema_version": "av-trace.p23-102-query-authoring-preflight/2.0",
        "pipeline_id": PIPELINE_ID,
        "date": CURRENT_DATE,
        "status": "READY" if not failures else "FAIL_CLOSED",
        "failures": failures,
        "counts": structural["counts"],
        "source_media": {
            "path": str(media),
            "available": media_path.is_file(),
            "sha256": (
                "sha256:" + file_sha256(media_path)
                if media_path.is_file()
                else None
            ),
        },
        "models": models,
        "decode_backend": "PyAV exact-interval seek and decode",
        "structured_ambient_combination_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "structured_ambient_unique_pair_count": (
            EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS
        ),
        "model_calls": 0,
        "media_decodes": 0,
        "network_required": False,
        "retrieval_artifacts_opened": False,
        "full_timeline_index_opened": False,
    }


def validate_authorization(
    root: Path,
    authorization_path: Path,
    *,
    structural: Mapping[str, Any],
    output: Path,
) -> dict[str, Any]:
    path = _repo_path(root, authorization_path)
    if not path.is_file():
        raise AuthoringError("EXECUTION_AUTHORIZATION_MISSING")
    value = load_json(path)
    expected = {
        "schema_version",
        "pipeline_id",
        "pipeline_sha256",
        "decision",
        "authorization_id",
        "authorized_at",
        "single_local_run",
        "bundle_file_hashes",
        "output_path",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise AuthoringError("EXECUTION_AUTHORIZATION_SCHEMA_INVALID")
    if (
        value["schema_version"]
        != "av-trace.p23-102-query-authoring-authorization/2.0"
        or value["pipeline_id"] != PIPELINE_ID
        or value["pipeline_sha256"] != pipeline_tool_sha256(root)
        or value["decision"] != "AUTHORIZED"
        or value["single_local_run"] is not True
        or value["bundle_file_hashes"] != structural["file_hashes"]
        or value["output_path"] != str(output)
    ):
        raise AuthoringError("EXECUTION_AUTHORIZATION_SCOPE_MISMATCH")
    return dict(value)


def _offline_environment() -> None:
    os.environ.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": str(THREADS),
            "MKL_NUM_THREADS": str(THREADS),
            "OPENBLAS_NUM_THREADS": str(THREADS),
        }
    )
    for name in list(os.environ):
        if name.lower() in {
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        } or name.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(name, None)


@contextlib.contextmanager
def deny_network() -> Iterator[dict[str, int]]:
    attempts = {"count": 0}
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    def blocked(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        attempts["count"] += 1
        raise AuthoringError("NETWORK_ACCESS_DENIED")

    socket.socket = blocked  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create_connection  # type: ignore[assignment]


def _frame_time_seconds(frame: Any) -> float | None:
    if frame.time is not None:
        return float(frame.time)
    if frame.pts is None or frame.time_base is None:
        return None
    return float(frame.pts * frame.time_base)


def _scaled_dimensions(width: int, height: int, maximum_side: int = 448) -> tuple[int, int]:
    if width <= maximum_side and height <= maximum_side:
        return width, height
    scale = maximum_side / max(width, height)
    scaled_width = max(2, round(width * scale / 2.0) * 2)
    scaled_height = max(2, round(height * scale / 2.0) * 2)
    return scaled_width, scaled_height


def _decode_source_interval(
    source: Path,
    *,
    start_us: int,
    end_us: int,
    sampled_video_frames: int = 16,
) -> tuple[Any, Any, dict[str, Any]]:
    """Decode only one exact interval into sampled RGB and full 16 kHz mono."""

    import av
    import numpy as np

    start_s = start_us / 1_000_000
    end_s = end_us / 1_000_000
    duration_s = end_s - start_s
    if duration_s <= 0:
        raise AuthoringError("TARGET_INTERVAL_DURATION_INVALID")
    target_times = np.linspace(
        start_s,
        end_s,
        num=sampled_video_frames,
        endpoint=False,
        dtype=np.float64,
    ) + duration_s / (2 * sampled_video_frames)
    best_distance = np.full(sampled_video_frames, np.inf, dtype=np.float64)
    sampled: list[Any | None] = [None] * sampled_video_frames
    decoded_video_frames = 0
    with av.open(str(source)) as container:
        if not container.streams.video:
            raise AuthoringError("SOURCE_VIDEO_STREAM_MISSING")
        stream = container.streams.video[0]
        container.seek(
            max(0, start_us - 2_000_000),
            any_frame=False,
            backward=True,
        )
        for frame in container.decode(stream):
            timestamp = _frame_time_seconds(frame)
            if timestamp is None or timestamp < start_s:
                continue
            if timestamp >= end_s:
                break
            decoded_video_frames += 1
            nearest = int(np.argmin(np.abs(target_times - timestamp)))
            distance = abs(float(target_times[nearest]) - timestamp)
            if distance < float(best_distance[nearest]):
                width, height = _scaled_dimensions(frame.width, frame.height)
                sampled[nearest] = frame.reformat(
                    width=width, height=height, format="rgb24"
                ).to_ndarray()
                best_distance[nearest] = distance
    available = [index for index, value in enumerate(sampled) if value is not None]
    if not available:
        raise AuthoringError("TARGET_VIDEO_DECODE_EMPTY")
    for index, value in enumerate(sampled):
        if value is None:
            nearest = min(available, key=lambda candidate: abs(candidate - index))
            sampled[index] = sampled[nearest].copy()
    video = np.stack(sampled).astype(np.uint8, copy=False)

    sample_rate = 16_000
    expected_samples = round(duration_s * sample_rate)
    waveform = np.zeros(expected_samples, dtype=np.float32)
    written = np.zeros(expected_samples, dtype=np.bool_)
    decoded_audio_frames = 0
    with av.open(str(source)) as container:
        if not container.streams.audio:
            raise AuthoringError("SOURCE_AUDIO_STREAM_MISSING")
        stream = container.streams.audio[0]
        container.seek(
            max(0, start_us - 2_000_000),
            any_frame=False,
            backward=True,
        )
        resampler = av.AudioResampler(
            format="flt", layout="mono", rate=sample_rate
        )
        stop = False
        for frame in container.decode(stream):
            for output in resampler.resample(frame):
                frame_start = _frame_time_seconds(output)
                if frame_start is None:
                    raise AuthoringError("TARGET_AUDIO_TIMESTAMP_MISSING")
                samples = output.to_ndarray().reshape(-1).astype(
                    np.float32, copy=False
                )
                frame_end = frame_start + samples.size / sample_rate
                if frame_end <= start_s:
                    continue
                if frame_start >= end_s:
                    stop = True
                    break
                decoded_audio_frames += 1
                destination_start = round(
                    (frame_start - start_s) * sample_rate
                )
                source_start = 0
                if destination_start < 0:
                    source_start = -destination_start
                    destination_start = 0
                destination_end = min(
                    expected_samples,
                    destination_start + samples.size - source_start,
                )
                if destination_end > destination_start:
                    count = destination_end - destination_start
                    waveform[destination_start:destination_end] = samples[
                        source_start : source_start + count
                    ]
                    written[destination_start:destination_end] = True
            if stop:
                break
        if not stop:
            for output in resampler.resample(None):
                frame_start = _frame_time_seconds(output)
                if frame_start is None:
                    continue
                samples = output.to_ndarray().reshape(-1).astype(
                    np.float32, copy=False
                )
                destination_start = round(
                    (frame_start - start_s) * sample_rate
                )
                source_start = max(0, -destination_start)
                destination_start = max(0, destination_start)
                destination_end = min(
                    expected_samples,
                    destination_start + samples.size - source_start,
                )
                if destination_end > destination_start:
                    count = destination_end - destination_start
                    waveform[destination_start:destination_end] = samples[
                        source_start : source_start + count
                    ]
                    written[destination_start:destination_end] = True
    if not written.any():
        raise AuthoringError("TARGET_AUDIO_DECODE_EMPTY")
    return video, waveform, {
        "sampled_video_frames": int(video.shape[0]),
        "decoded_video_frames_in_interval": decoded_video_frames,
        "audio_sample_rate_hz": sample_rate,
        "audio_samples": int(waveform.size),
        "audio_coverage_fraction": round(float(written.mean()), 8),
        "decoded_audio_frames_in_interval": decoded_audio_frames,
    }


def _extract_exact_clips(
    source: Path,
    targets: Sequence[Mapping[str, Any]],
    output_dir: Path,
    *,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[dict[str, dict[str, Path]], list[dict[str, Any]]]:
    import numpy as np

    clips: dict[str, dict[str, Path]] = {}
    records = []
    for row in targets:
        clip_key = str(row["clip_key"])
        clip_dir = output_dir / "clips" / clip_key
        clip_dir.mkdir(parents=True, exist_ok=True)
        video_path = clip_dir / "video_rgb_uint8.npy"
        audio_path = clip_dir / "audio_mono_16khz_float32.npy"
        video, waveform, decode_metadata = _decode_source_interval(
            source,
            start_us=int(row["start_us"]),
            end_us=int(row["end_us"]),
        )
        np.save(video_path, video, allow_pickle=False)
        np.save(audio_path, waveform, allow_pickle=False)
        clips[clip_key] = {"video": video_path, "audio": audio_path}
        record = {
            "clip_key": clip_key,
            "start_us": row["start_us"],
            "end_us": row["end_us"],
            "duration_us": row["duration_us"],
            "decode_backend": "PyAV",
            "video_path": str(video_path),
            "video_sha256": "sha256:" + file_sha256(video_path),
            "video_bytes": video_path.stat().st_size,
            "video_shape": list(video.shape),
            "audio_path": str(audio_path),
            "audio_sha256": "sha256:" + file_sha256(audio_path),
            "audio_bytes": audio_path.stat().st_size,
            "audio_shape": list(waveform.shape),
            **decode_metadata,
        }
        records.append(record)
        if progress_callback is not None:
            progress_callback(record)
    return clips, records


def _decode_av(asset: Mapping[str, Path]) -> tuple[Any, Any]:
    import numpy as np

    video = np.load(asset["video"], allow_pickle=False)
    audio = np.load(asset["audio"], allow_pickle=False)
    if video.ndim != 4 or video.shape[-1] != 3 or video.dtype != np.uint8:
        raise AuthoringError("TARGET_VIDEO_ARRAY_INVALID")
    if audio.ndim != 1 or audio.dtype != np.float32 or audio.size == 0:
        raise AuthoringError("TARGET_AUDIO_ARRAY_INVALID")
    return video, audio


def _model_conversation(
    prompt: Mapping[str, Any], media_components: int | None = None
) -> list[dict[str, Any]]:
    expected_media = int(prompt.get("media_component_count", 0))
    if media_components is None:
        media_components = expected_media
    if media_components != expected_media:
        raise AuthoringError("PROMPT_MEDIA_COMPONENT_COUNT_MISMATCH")
    modalities = prompt.get("media_modalities", [])
    if not isinstance(modalities, list) or len(modalities) != expected_media:
        raise AuthoringError("PROMPT_MEDIA_MODALITY_COUNT_MISMATCH")
    content = []
    for modality in modalities:
        if modality == "visual":
            content.append(
                {"type": "video", "video": "local://exact-target-video"}
            )
        elif modality == "ambient":
            content.append(
                {"type": "audio", "audio": "local://exact-target-audio"}
            )
        else:
            raise AuthoringError("PROMPT_MEDIA_MODALITY_INVALID")
    content.append(
        {
            "type": "text",
            "text": canonical_bytes(prompt["user_payload"]).decode("utf-8"),
        }
    )
    return [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": str(prompt["system_prompt"])}
            ],
        },
        {"role": "user", "content": content},
    ]


def _load_omni(root: Path) -> tuple[Any, Any, Any]:
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    import torch
    from transformers import (
        Qwen2_5OmniProcessor,
        Qwen2_5OmniThinkerForConditionalGeneration,
    )

    torch.manual_seed(0)
    torch.set_num_threads(THREADS)
    with contextlib.suppress(RuntimeError):
        torch.set_num_interop_threads(1)
    snapshot = _repo_path(root, OMNI_SNAPSHOT)
    with deny_network():
        processor = Qwen2_5OmniProcessor.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            use_fast=False,
        )
    with deny_network():
        model = Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        ).eval()
    return processor, model, torch


def _generate_one(
    processor: Any,
    model: Any,
    torch: Any,
    *,
    conversation: Sequence[Mapping[str, Any]],
    media_present: bool,
    videos: Sequence[Any] | None = None,
    audios: Sequence[Any] | None = None,
    factor_kind: str | None = None,
) -> tuple[str, dict[str, Any]]:
    requested_prefill, _, prefill_compatibility = (
        _compatible_json_assistant_prefill(processor.tokenizer, model)
    )
    rendered, inputs, media_contract = _prepare_generation_inputs(
        processor,
        conversation=conversation,
        media_present=media_present,
        videos=videos,
        audios=audios,
        assistant_prefill=requested_prefill,
    )
    prefill = str(media_contract["assistant_prefill"])
    prefill_token_ids = list(
        processor.tokenizer.encode(prefill, add_special_tokens=False)
    )
    if requested_prefill and not prefill:
        prefill_compatibility = "disabled_for_chat_template_boundary"
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    if prompt_tokens > MAX_CONTEXT_TOKENS:
        raise AuthoringError("MODEL_CONTEXT_CAP_EXCEEDED")
    from transformers import LogitsProcessorList, StoppingCriteriaList

    ambient_constraint = None
    if factor_kind == "ambient":
        ambient_constraint = ambient_token_prefix_constraint(
            processor.tokenizer,
            model,
            assistant_prefill=prefill,
        )
        logits_boundary = _AmbientTupleTrieLogitsProcessor(
            constraint=ambient_constraint,
            generated_start=prompt_tokens,
        )
        stopping_boundary = _AmbientTupleTrieStoppingCriterion(
            constraint=ambient_constraint,
            generated_start=prompt_tokens,
        )
    else:
        logits_boundary = _JSONObjectLogitsBoundary(
            tokenizer=processor.tokenizer,
            generated_start=prompt_tokens,
            assistant_prefill=prefill,
        )
        stopping_boundary = _JSONObjectStoppingCriterion(
            tokenizer=processor.tokenizer,
            generated_start=prompt_tokens,
            assistant_prefill=prefill,
        )
    generation_kwargs = {
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": False,
        "use_cache": True,
        "pad_token_id": processor.tokenizer.eos_token_id,
        "logits_processor": LogitsProcessorList([logits_boundary]),
        "stopping_criteria": StoppingCriteriaList([stopping_boundary]),
    }
    media_mode = media_contract.get("media_mode")
    if media_mode == "video_only":
        generation_kwargs["use_audio_in_video"] = False
    started = time.monotonic()
    with torch.inference_mode(), deny_network() as attempts:
        generated = model.generate(**inputs, **generation_kwargs)
    generated_ids = generated[:, prompt_tokens:]
    decoded_ids = generated_ids
    terminal_stop_token_id = None
    if ambient_constraint is not None and int(generated_ids.shape[-1]) > 0:
        observed_last = int(generated_ids[0, -1].item())
        if observed_last in ambient_constraint.stop_token_ids:
            terminal_stop_token_id = observed_last
            decoded_ids = generated_ids[:, :-1]
    generated_text = processor.batch_decode(
        decoded_ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )[0]
    raw = prefill + generated_text
    generated_token_count = int(generated_ids.shape[-1])
    if ambient_constraint is not None:
        generated_content_ids = [
            int(token_id) for token_id in decoded_ids[0].tolist()
        ]
        if (
            terminal_stop_token_id is not None
            and ambient_constraint.path_reachable(generated_content_ids)
            and raw in ambient_constraint.token_paths
        ):
            stop_reason = "ambient_constraint_leaf_stop"
        elif generated_token_count >= MAX_NEW_TOKENS:
            stop_reason = "ambient_constraint_unclosed_at_token_cap"
        else:
            stop_reason = "ambient_constraint_invalid_generated_sequence"
    else:
        final_state = IncrementalJSONObjectState().feed(raw)
        if final_state.complete and not final_state.invalid:
            stop_reason = "first_complete_top_level_json_object"
        elif final_state.invalid:
            stop_reason = "constrained_json_invalid_generated_sequence"
        elif generated_token_count >= MAX_NEW_TOKENS:
            stop_reason = "json_object_unclosed_at_token_cap"
        else:
            stop_reason = "json_object_unclosed_before_token_cap"
    constraint_metadata = (
        ambient_constraint.metadata()
        if ambient_constraint is not None
        else {
            "constraint_kind": "json_object_boundary",
            "constraint_manifest": None,
            "constraint_manifest_sha256": None,
            "constraint_trie_sha256": None,
            "constraint_tokenizer_fingerprint_sha256": None,
            "constraint_leaf_count": None,
            "constraint_reachable_count": None,
            "constraint_stop_token_ids": [],
            "constraint_assistant_prefill": prefill,
        }
    )
    return raw, {
        "rendered_prompt": rendered,
        "rendered_prompt_sha256": (
            "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        ),
        "rendered_prompt_bytes": len(rendered.encode("utf-8")),
        "prompt_tokens": prompt_tokens,
        "prompt_tokens_excluding_prefill": (
            prompt_tokens - len(prefill_token_ids)
        ),
        "completion_tokens": generated_token_count,
        "model_generated_tokens": generated_token_count,
        "assistant_prefill": prefill,
        "assistant_prefill_tokens": len(prefill_token_ids),
        "assistant_prefill_compatibility": prefill_compatibility,
        "constrained_output_tokens": (
            len(prefill_token_ids) + int(decoded_ids.shape[-1])
        ),
        "terminal_stop_token_id": terminal_stop_token_id,
        "generation_token_cap": MAX_NEW_TOKENS,
        "stop_reason": stop_reason,
        "generation_seconds": round(time.monotonic() - started, 6),
        "network_attempts": attempts["count"],
        "media_contract": media_contract,
        **constraint_metadata,
    }


def _conversation_media_placeholders(
    conversation: Sequence[Mapping[str, Any]],
) -> tuple[int, int]:
    video_count = 0
    audio_count = 0
    for message in conversation:
        content = message.get("content")
        if not isinstance(content, Sequence) or isinstance(
            content, (str, bytes)
        ):
            continue
        for item in content:
            if not isinstance(item, Mapping):
                continue
            item_type = item.get("type")
            if item_type == "video":
                video_count += 1
            elif item_type == "audio":
                audio_count += 1
    return video_count, audio_count


def _token_count(input_ids: Any, token_id: int) -> int:
    count = input_ids == token_id
    if hasattr(count, "sum"):
        result = count.sum()
        if hasattr(result, "item"):
            return int(result.item())
        return int(result)
    return sum(
        int(token == token_id)
        for row in input_ids
        for token in (row if isinstance(row, Sequence) else [row])
    )


class IncrementalJSONObjectState:
    """Incrementally locate one complete top-level JSON object.

    The state machine tracks JSON strings, escapes, Unicode escapes, and
    nested object/array delimiters. A balanced top-level closure is accepted
    only when the entire prefix parses as one JSON object. After closure, only
    whitespace is valid.
    """

    def __init__(self) -> None:
        self.text = ""
        self.stack: list[str] = []
        self.started = False
        self.in_string = False
        self.escape = False
        self.unicode_escape_remaining = 0
        self.complete = False
        self.invalid = False
        self.completion_offset: int | None = None

    def feed(self, chunk: str) -> IncrementalJSONObjectState:
        for character in chunk:
            self.text += character
            if self.invalid:
                continue
            if self.complete:
                if not character.isspace():
                    self.invalid = True
                continue
            if not self.started:
                if character != "{":
                    self.invalid = True
                    continue
                self.started = True
                self.stack.append("}")
                continue
            if self.in_string:
                self._feed_string_character(character)
                continue
            if character == '"':
                self.in_string = True
            elif character == "{":
                self.stack.append("}")
            elif character == "[":
                self.stack.append("]")
            elif character in "}]":
                if not self.stack or self.stack[-1] != character:
                    self.invalid = True
                    continue
                self.stack.pop()
                if not self.stack:
                    self._validate_complete_prefix()
            elif ord(character) < 0x20 and not character.isspace():
                self.invalid = True
        return self

    def _feed_string_character(self, character: str) -> None:
        if self.unicode_escape_remaining:
            if character not in "0123456789abcdefABCDEF":
                self.invalid = True
                return
            self.unicode_escape_remaining -= 1
            return
        if self.escape:
            self.escape = False
            if character == "u":
                self.unicode_escape_remaining = 4
            elif character not in '"\\/bfnrt':
                self.invalid = True
            return
        if character == "\\":
            self.escape = True
        elif character == '"':
            self.in_string = False
        elif ord(character) < 0x20:
            self.invalid = True

    def _validate_complete_prefix(self) -> None:
        try:
            value = json.loads(self.text)
        except json.JSONDecodeError:
            self.invalid = True
            return
        if not isinstance(value, dict):
            self.invalid = True
            return
        self.complete = True
        self.completion_offset = len(self.text)


def _decode_token_ids(tokenizer: Any, token_ids: Sequence[int]) -> str:
    return tokenizer.decode(
        list(token_ids),
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )


def _compatible_json_assistant_prefill(
    tokenizer: Any, model: Any
) -> tuple[str, list[int], str]:
    """Use the minimal object start only for exact decoder-tokenizer support."""

    config = getattr(model, "config", None)
    if getattr(config, "is_encoder_decoder", False):
        return "", [], "disabled_for_encoder_decoder_model"
    token_ids = list(
        tokenizer.encode(JSON_ASSISTANT_PREFILL, add_special_tokens=False)
    )
    special_ids = set(getattr(tokenizer, "all_special_ids", ()) or ())
    if (
        not token_ids
        or any(token_id in special_ids for token_id in token_ids)
        or _decode_token_ids(tokenizer, token_ids) != JSON_ASSISTANT_PREFILL
    ):
        return "", [], "disabled_for_non_roundtripping_tokenizer"
    return JSON_ASSISTANT_PREFILL, token_ids, "enabled_exact_roundtrip"


class _JSONObjectLogitsBoundary:
    """Mask greedy candidates that violate the one-object output boundary."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        generated_start: int,
        assistant_prefill: str,
    ) -> None:
        self.tokenizer = tokenizer
        self.generated_start = generated_start
        self.assistant_prefill = assistant_prefill
        self.stop_token_ids = {
            token_id
            for token_id in (
                getattr(tokenizer, "eos_token_id", None),
                getattr(tokenizer, "pad_token_id", None),
            )
            if token_id is not None
        }

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        if int(input_ids.shape[0]) != 1:
            raise AuthoringError("CONSTRAINED_JSON_BATCH_SIZE_UNSUPPORTED")
        generated_ids = [
            int(token_id)
            for token_id in input_ids[0, self.generated_start :].tolist()
        ]
        current_text = self.assistant_prefill + _decode_token_ids(
            self.tokenizer, generated_ids
        )
        current_state = IncrementalJSONObjectState().feed(current_text)
        if current_state.invalid:
            raise AuthoringError("CONSTRAINED_JSON_PREFIX_INVALID")
        if current_state.complete:
            return scores

        bounded = scores.clone()
        rejected = 0
        vocabulary_size = int(bounded.shape[-1])
        while rejected < vocabulary_size:
            candidate_id = int(bounded[0].argmax().item())
            candidate_generated = [*generated_ids, candidate_id]
            candidate_text = self.assistant_prefill + _decode_token_ids(
                self.tokenizer, candidate_generated
            )
            candidate_state = IncrementalJSONObjectState().feed(
                candidate_text
            )
            candidate_is_empty_stop = (
                candidate_id in self.stop_token_ids
                and candidate_text == current_text
            )
            if not candidate_state.invalid and not candidate_is_empty_stop:
                return bounded
            bounded[0, candidate_id] = float("-inf")
            rejected += 1
        raise AuthoringError("CONSTRAINED_JSON_NO_VALID_NEXT_TOKEN")


class _JSONObjectStoppingCriterion:
    """Stop generation on the token that first completes the JSON object."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        generated_start: int,
        assistant_prefill: str,
    ) -> None:
        self.tokenizer = tokenizer
        self.generated_start = generated_start
        self.assistant_prefill = assistant_prefill

    def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> Any:
        del scores, kwargs
        decisions = []
        for row in input_ids:
            generated_ids = [
                int(token_id)
                for token_id in row[self.generated_start :].tolist()
            ]
            text = self.assistant_prefill + _decode_token_ids(
                self.tokenizer, generated_ids
            )
            state = IncrementalJSONObjectState().feed(text)
            if state.invalid:
                raise AuthoringError("CONSTRAINED_JSON_PREFIX_INVALID")
            decisions.append(state.complete)
        return input_ids.new_tensor(decisions, dtype=input_ids.dtype).bool()


def _generation_stop_token_ids(tokenizer: Any, model: Any) -> frozenset[int]:
    """Collect decoder stop IDs without treating padding as a valid leaf."""

    values = []
    for owner in (
        tokenizer,
        getattr(model, "generation_config", None),
        getattr(model, "config", None),
        getattr(getattr(model, "config", None), "thinker_config", None),
    ):
        if owner is None:
            continue
        value = getattr(owner, "eos_token_id", None)
        if isinstance(value, int):
            values.append(value)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes)
        ):
            values.extend(
                int(item) for item in value if isinstance(item, int)
            )
    if not values:
        raise AuthoringError("AMBIENT_CONSTRAINT_STOP_TOKEN_MISSING")
    return frozenset(values)


def _tokenize_ambient_constraint_suffix(
    tokenizer: Any,
    canonical_json: str,
    *,
    assistant_prefill: str,
) -> tuple[int, ...]:
    """Tokenize one legal suffix and prove exact prefill-aware roundtrip."""

    if assistant_prefill and not canonical_json.startswith(
        assistant_prefill
    ):
        raise AuthoringError("AMBIENT_CONSTRAINT_PREFILL_PREFIX_MISMATCH")
    suffix = canonical_json[len(assistant_prefill) :]
    token_ids = tuple(
        int(token_id)
        for token_id in tokenizer.encode(
            suffix, add_special_tokens=False
        )
    )
    special_ids = set(getattr(tokenizer, "all_special_ids", ()) or ())
    if (
        not token_ids
        or any(token_id in special_ids for token_id in token_ids)
        or assistant_prefill
        + _decode_token_ids(tokenizer, token_ids)
        != canonical_json
    ):
        raise AuthoringError(
            "AMBIENT_CONSTRAINT_CANONICAL_TOKENIZATION_INVALID"
        )
    return token_ids


class AmbientTokenPrefixConstraint:
    """Exact token-prefix trie over every legal canonical ambient tuple."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        assistant_prefill: str,
        stop_token_ids: Sequence[int],
        tokenizer_fingerprint_sha256: str | None = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.assistant_prefill = assistant_prefill
        self.stop_token_ids = frozenset(int(value) for value in stop_token_ids)
        if not self.stop_token_ids:
            raise AuthoringError("AMBIENT_CONSTRAINT_STOP_TOKEN_MISSING")
        self.children: list[dict[int, int]] = [{}]
        self.leaf_nodes: set[int] = set()
        self.token_paths: dict[str, tuple[int, ...]] = {}
        for canonical_json in _CANONICAL_AMBIENT_TUPLE_STRINGS:
            path = _tokenize_ambient_constraint_suffix(
                tokenizer,
                canonical_json,
                assistant_prefill=assistant_prefill,
            )
            node = 0
            for token_id in path:
                child = self.children[node].get(token_id)
                if child is None:
                    child = len(self.children)
                    self.children[node][token_id] = child
                    self.children.append({})
                node = child
            if node in self.leaf_nodes:
                raise AuthoringError("AMBIENT_CONSTRAINT_TOKEN_PATH_COLLISION")
            self.leaf_nodes.add(node)
            self.token_paths[canonical_json] = path
        if len(self.leaf_nodes) != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS:
            raise AuthoringError("AMBIENT_CONSTRAINT_LEAF_COUNT_MISMATCH")
        if any(self.children[node] for node in self.leaf_nodes):
            raise AuthoringError("AMBIENT_CONSTRAINT_LEAF_HAS_CHILDREN")
        trie_payload = {
            "assistant_prefill": assistant_prefill,
            "stop_token_ids": sorted(self.stop_token_ids),
            "paths": [
                {
                    "canonical_json": canonical_json,
                    "token_ids": list(self.token_paths[canonical_json]),
                }
                for canonical_json in _CANONICAL_AMBIENT_TUPLE_STRINGS
            ],
        }
        self.tokenizer_fingerprint_sha256 = (
            tokenizer_fingerprint_sha256
            or trusted_tokenizer_fingerprint_sha256(tokenizer)
        )
        self.trie_sha256 = semantic_hash(trie_payload)
        self.reachable_count = sum(
            self.path_reachable(path) for path in self.token_paths.values()
        )
        if self.reachable_count != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS:
            raise AuthoringError(
                "AMBIENT_CONSTRAINT_REACHABLE_COUNT_MISMATCH"
            )

    def node_for_prefix(self, token_ids: Sequence[int]) -> int | None:
        node = 0
        for token_id in token_ids:
            child = self.children[node].get(int(token_id))
            if child is None:
                return None
            node = child
        return node

    def path_reachable(self, token_ids: Sequence[int]) -> bool:
        node = self.node_for_prefix(token_ids)
        return node in self.leaf_nodes if node is not None else False

    def allowed_token_ids(self, token_ids: Sequence[int]) -> frozenset[int]:
        node = self.node_for_prefix(token_ids)
        if node is None:
            raise AuthoringError("AMBIENT_CONSTRAINT_PREFIX_UNREACHABLE")
        if node in self.leaf_nodes:
            return self.stop_token_ids
        return frozenset(self.children[node])

    def canonical_string_reachable(self, value: str) -> bool:
        try:
            path = _tokenize_ambient_constraint_suffix(
                self.tokenizer,
                value,
                assistant_prefill=self.assistant_prefill,
            )
        except AuthoringError:
            return False
        return self.path_reachable(path)

    def metadata(self) -> dict[str, Any]:
        return {
            "constraint_kind": AMBIENT_CONSTRAINT_KIND,
            "constraint_manifest": json.loads(
                canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
            ),
            "constraint_manifest_sha256": (
                AMBIENT_CONSTRAINT_MANIFEST_SHA256
            ),
            "constraint_trie_sha256": self.trie_sha256,
            "constraint_tokenizer_fingerprint_sha256": (
                self.tokenizer_fingerprint_sha256
            ),
            "constraint_leaf_count": len(self.leaf_nodes),
            "constraint_reachable_count": self.reachable_count,
            "constraint_stop_token_ids": sorted(self.stop_token_ids),
            "constraint_assistant_prefill": self.assistant_prefill,
        }


_AMBIENT_CONSTRAINT_CACHE: dict[
    tuple[int, str, tuple[int, ...]], AmbientTokenPrefixConstraint
] = {}
_TRUSTED_AMBIENT_CONSTRAINT_CONTEXT: dict[str, Any] | None = None


def _tokenizer_snapshot_path(tokenizer: Any) -> Path:
    candidate = Path(str(getattr(tokenizer, "name_or_path", "")))
    if candidate.is_dir():
        return candidate
    fixed = ROOT / OMNI_SNAPSHOT
    if fixed.is_dir():
        return fixed
    raise AuthoringError("TRUSTED_AMBIENT_TOKENIZER_SNAPSHOT_MISSING")


def trusted_tokenizer_fingerprint_sha256(tokenizer: Any) -> str:
    """Fingerprint the fixed local tokenizer files, never output metadata."""

    snapshot = _tokenizer_snapshot_path(tokenizer)
    file_hashes = {}
    for name in TRUSTED_AMBIENT_TOKENIZER_FILES:
        path = snapshot / name
        if not path.is_file():
            raise AuthoringError(
                f"TRUSTED_AMBIENT_TOKENIZER_FILE_MISSING:{name}"
            )
        file_hashes[name] = "sha256:" + file_sha256(path)
    return semantic_hash(
        {
            "schema_version": (
                "av-trace.p23-102-ambient-tokenizer-fingerprint/1.0"
            ),
            "snapshot": OMNI_SNAPSHOT.as_posix(),
            "files": file_hashes,
            "tokenizer_class": type(tokenizer).__name__,
            "vocab_size": int(getattr(tokenizer, "vocab_size", 0) or 0),
            "eos_token_id": getattr(tokenizer, "eos_token_id", None),
            "pad_token_id": getattr(tokenizer, "pad_token_id", None),
            "all_special_ids": list(
                getattr(tokenizer, "all_special_ids", ()) or ()
            ),
            "canonical_strings_sha256": AMBIENT_CONSTRAINT_MANIFEST[
                "canonical_strings_sha256"
            ],
        }
    )


def trusted_ambient_constraint_context() -> dict[str, Any]:
    """Rebuild the trusted R21 runtime constraint without loading a model.

    The tokenizer and six small tokenizer/config files come only from the
    fixed local Qwen snapshot.  The 7,680 canonical strings are regenerated
    from code and tokenized into the trie.  The result is cached per process;
    no media is decoded and no model weights are opened.
    """

    global _TRUSTED_AMBIENT_CONSTRAINT_CONTEXT
    if _TRUSTED_AMBIENT_CONSTRAINT_CONTEXT is not None:
        return _TRUSTED_AMBIENT_CONSTRAINT_CONTEXT
    started = time.monotonic()
    _validate_static_ambient_contract()
    snapshot = ROOT / OMNI_SNAPSHOT
    config_path = snapshot / "config.json"
    if not config_path.is_file():
        raise AuthoringError("TRUSTED_AMBIENT_TOKENIZER_CONFIG_MISSING")
    from transformers import AutoTokenizer

    with deny_network():
        tokenizer = AutoTokenizer.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            use_fast=False,
        )
    config_value = load_json(config_path)
    thinker = config_value.get("thinker_config")
    if not isinstance(thinker, Mapping):
        raise AuthoringError("TRUSTED_AMBIENT_THINKER_CONFIG_INVALID")
    model = SimpleNamespace(
        config=SimpleNamespace(
            is_encoder_decoder=False,
            eos_token_id=config_value.get("eos_token_id"),
            thinker_config=SimpleNamespace(
                eos_token_id=thinker.get("eos_token_id")
            ),
        )
    )
    assistant_prefill, _, compatibility = (
        _compatible_json_assistant_prefill(tokenizer, model)
    )
    if (
        assistant_prefill != JSON_ASSISTANT_PREFILL
        or compatibility != "enabled_exact_roundtrip"
    ):
        raise AuthoringError("TRUSTED_AMBIENT_PREFILL_INCOMPATIBLE")
    fingerprint = trusted_tokenizer_fingerprint_sha256(tokenizer)
    constraint = AmbientTokenPrefixConstraint(
        tokenizer=tokenizer,
        assistant_prefill=assistant_prefill,
        stop_token_ids=sorted(_generation_stop_token_ids(tokenizer, model)),
        tokenizer_fingerprint_sha256=fingerprint,
    )
    metadata = constraint.metadata()
    if (
        metadata["constraint_manifest"] != AMBIENT_CONSTRAINT_MANIFEST
        or metadata["constraint_manifest_sha256"]
        != AMBIENT_CONSTRAINT_MANIFEST_SHA256
        or metadata["constraint_leaf_count"]
        != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        or metadata["constraint_reachable_count"]
        != EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        or AMBIENT_CONSTRAINT_MANIFEST["canonical_strings_sha256"]
        != semantic_hash(list(_CANONICAL_AMBIENT_TUPLE_STRINGS))
    ):
        raise AuthoringError("TRUSTED_AMBIENT_CONSTRAINT_REBUILD_INVALID")
    _TRUSTED_AMBIENT_CONSTRAINT_CONTEXT = {
        "attempt_constraint": metadata,
        "json_boundary_constraint": {
            "constraint_kind": "json_object_boundary",
            "constraint_manifest": None,
            "constraint_manifest_sha256": None,
            "constraint_trie_sha256": None,
            "constraint_tokenizer_fingerprint_sha256": None,
            "constraint_leaf_count": None,
            "constraint_reachable_count": None,
            "constraint_stop_token_ids": [],
            "constraint_assistant_prefill": assistant_prefill,
        },
        "canonical_strings_sha256": AMBIENT_CONSTRAINT_MANIFEST[
            "canonical_strings_sha256"
        ],
        "tokenizer_snapshot": OMNI_SNAPSHOT.as_posix(),
        "tokenizer_fingerprint_sha256": fingerprint,
        "context_build_seconds": round(time.monotonic() - started, 6),
    }
    return _TRUSTED_AMBIENT_CONSTRAINT_CONTEXT


def ambient_token_prefix_constraint(
    tokenizer: Any,
    model: Any,
    *,
    assistant_prefill: str,
) -> AmbientTokenPrefixConstraint:
    """Build or reuse the exact trie for one tokenizer/prefill/stop contract."""

    stop_token_ids = tuple(
        sorted(_generation_stop_token_ids(tokenizer, model))
    )
    key = (id(tokenizer), assistant_prefill, stop_token_ids)
    constraint = _AMBIENT_CONSTRAINT_CACHE.get(key)
    if constraint is None or constraint.tokenizer is not tokenizer:
        constraint = AmbientTokenPrefixConstraint(
            tokenizer=tokenizer,
            assistant_prefill=assistant_prefill,
            stop_token_ids=stop_token_ids,
            tokenizer_fingerprint_sha256=(
                trusted_tokenizer_fingerprint_sha256(tokenizer)
            ),
        )
        _AMBIENT_CONSTRAINT_CACHE[key] = constraint
    return constraint


class _AmbientTupleTrieLogitsProcessor:
    """Mask all logits except exact outgoing trie edges or leaf stops."""

    def __init__(
        self,
        *,
        constraint: AmbientTokenPrefixConstraint,
        generated_start: int,
    ) -> None:
        self.constraint = constraint
        self.generated_start = generated_start

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        if int(input_ids.shape[0]) != 1:
            raise AuthoringError("AMBIENT_CONSTRAINT_BATCH_SIZE_UNSUPPORTED")
        generated_ids = [
            int(token_id)
            for token_id in input_ids[0, self.generated_start :].tolist()
        ]
        allowed = self.constraint.allowed_token_ids(generated_ids)
        bounded = scores.new_full(scores.shape, float("-inf"))
        valid = [
            token_id
            for token_id in allowed
            if 0 <= token_id < int(scores.shape[-1])
        ]
        if not valid:
            raise AuthoringError("AMBIENT_CONSTRAINT_NO_VALID_NEXT_TOKEN")
        bounded[0, valid] = scores[0, valid]
        return bounded


class _AmbientTupleTrieStoppingCriterion:
    """Stop only after a legal leaf emits an approved EOS/stop token."""

    def __init__(
        self,
        *,
        constraint: AmbientTokenPrefixConstraint,
        generated_start: int,
    ) -> None:
        self.constraint = constraint
        self.generated_start = generated_start

    def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> Any:
        del scores, kwargs
        decisions = []
        for row in input_ids:
            generated_ids = [
                int(token_id)
                for token_id in row[self.generated_start :].tolist()
            ]
            complete = (
                bool(generated_ids)
                and generated_ids[-1] in self.constraint.stop_token_ids
                and self.constraint.path_reachable(generated_ids[:-1])
            )
            decisions.append(complete)
        return input_ids.new_tensor(
            decisions, dtype=input_ids.dtype
        ).bool()


def _prepare_generation_inputs(
    processor: Any,
    *,
    conversation: Sequence[Mapping[str, Any]],
    media_present: bool,
    videos: Sequence[Any] | None = None,
    audios: Sequence[Any] | None = None,
    assistant_prefill: str = "",
) -> tuple[str, Any, dict[str, Any]]:
    """Render and process one prompt under an explicit media contract."""

    video_placeholders, audio_placeholders = (
        _conversation_media_placeholders(conversation)
    )
    video_values = list(videos) if videos is not None else []
    audio_values = list(audios) if audios is not None else []
    if media_present:
        if video_placeholders and audio_placeholders:
            raise AuthoringError("MIXED_MEDIA_PLACEHOLDERS_FORBIDDEN")
        if video_placeholders:
            media_mode = "video_only"
            if len(video_values) != video_placeholders:
                raise AuthoringError(
                    "VIDEO_PLACEHOLDER_TENSOR_COUNT_MISMATCH"
                )
            if audio_values:
                raise AuthoringError("VIDEO_ONLY_AUDIO_TENSORS_FORBIDDEN")
        elif audio_placeholders:
            media_mode = "audio_only"
            if len(audio_values) != audio_placeholders:
                raise AuthoringError(
                    "AUDIO_PLACEHOLDER_TENSOR_COUNT_MISMATCH"
                )
            if video_values:
                raise AuthoringError("AUDIO_ONLY_VIDEO_TENSORS_FORBIDDEN")
        else:
            raise AuthoringError("MEDIA_TENSORS_WITHOUT_PLACEHOLDERS")
    else:
        media_mode = "text_only"
        if video_placeholders:
            raise AuthoringError("VIDEO_PLACEHOLDERS_WITHOUT_MEDIA_TENSORS")
        if audio_placeholders:
            raise AuthoringError("AUDIO_PLACEHOLDERS_WITHOUT_MEDIA_TENSORS")
        if video_values or audio_values:
            raise AuthoringError("MEDIA_TENSORS_WITHOUT_PLACEHOLDERS")

    rendered_without_prefill = processor.apply_chat_template(
        conversation, add_generation_prompt=True, tokenize=False
    )
    if assistant_prefill:
        base_ids = list(
            processor.tokenizer.encode(
                rendered_without_prefill, add_special_tokens=False
            )
        )
        combined_ids = list(
            processor.tokenizer.encode(
                rendered_without_prefill + assistant_prefill,
                add_special_tokens=False,
            )
        )
        prefill_ids = list(
            processor.tokenizer.encode(
                assistant_prefill, add_special_tokens=False
            )
        )
        if combined_ids != [*base_ids, *prefill_ids]:
            assistant_prefill = ""
    rendered = rendered_without_prefill + assistant_prefill
    processor_kwargs = {
        "text": rendered,
        "return_tensors": "pt",
        "padding": True,
    }
    if media_mode == "video_only":
        processor_kwargs.update(
            {
                "videos": video_values,
                "use_audio_in_video": False,
            }
        )
    elif media_mode == "audio_only":
        processor_kwargs["audio"] = audio_values
    inputs = processor(**processor_kwargs)
    video_tokens = _token_count(
        inputs["input_ids"], processor.tokenizer.video_token_id
    )
    audio_tokens = _token_count(
        inputs["input_ids"], processor.tokenizer.audio_token_id
    )
    media_feature_keys = sorted(
        key
        for key in (
            "pixel_values_videos",
            "video_grid_thw",
            "video_second_per_grid",
            "input_features",
            "feature_attention_mask",
        )
        if key in inputs
    )
    if media_mode == "video_only":
        if video_tokens == 0 or audio_tokens != 0:
            raise AuthoringError("PROCESSOR_VIDEO_ONLY_TOKENS_INVALID")
        required_features = {"pixel_values_videos", "video_grid_thw"}
        if not required_features <= set(media_feature_keys):
            raise AuthoringError("PROCESSOR_VIDEO_FEATURES_MISSING")
        if {"input_features", "feature_attention_mask"} & set(
            media_feature_keys
        ):
            raise AuthoringError("PROCESSOR_VIDEO_ONLY_AUDIO_FEATURE_LEAK")
    elif media_mode == "audio_only":
        if audio_tokens == 0 or video_tokens != 0:
            raise AuthoringError("PROCESSOR_AUDIO_ONLY_TOKENS_INVALID")
        required_features = {"input_features", "feature_attention_mask"}
        if not required_features <= set(media_feature_keys):
            raise AuthoringError("PROCESSOR_AUDIO_FEATURES_MISSING")
        if {"pixel_values_videos", "video_grid_thw"} & set(
            media_feature_keys
        ):
            raise AuthoringError("PROCESSOR_AUDIO_ONLY_VIDEO_FEATURE_LEAK")
    elif video_tokens or audio_tokens or media_feature_keys:
        raise AuthoringError("PROCESSOR_TEXT_ONLY_MEDIA_LEAK")
    prefill_token_ids = list(
        processor.tokenizer.encode(
            assistant_prefill, add_special_tokens=False
        )
    )
    if assistant_prefill:
        observed_suffix = [
            int(token_id)
            for token_id in inputs["input_ids"][0, -len(prefill_token_ids) :]
        ]
        if (
            not prefill_token_ids
            or observed_suffix != prefill_token_ids
            or _decode_token_ids(
                processor.tokenizer, prefill_token_ids
            )
            != assistant_prefill
        ):
            raise AuthoringError("ASSISTANT_JSON_PREFILL_PROCESSOR_MISMATCH")
    return rendered, inputs, {
        "media_present": media_present,
        "media_mode": media_mode,
        "video_placeholders": video_placeholders,
        "audio_placeholders": audio_placeholders,
        "video_tensors": len(video_values),
        "audio_tensors": len(audio_values),
        "video_placeholder_tokens": video_tokens,
        "audio_placeholder_tokens": audio_tokens,
        "media_feature_keys": media_feature_keys,
        "use_audio_in_video": False if media_mode == "video_only" else None,
        "assistant_prefill": assistant_prefill,
        "assistant_prefill_tokens": len(prefill_token_ids),
    }


def _strict_json_output(raw: str) -> Any:
    state = IncrementalJSONObjectState().feed(raw)
    if state.invalid or not state.complete:
        raise AuthoringError("MODEL_OUTPUT_NOT_STRICT_JSON")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthoringError("MODEL_OUTPUT_JSON_INVALID") from exc


REPAIRABLE_OUTPUT_ERRORS = frozenset(
    {
        "MODEL_OUTPUT_NOT_STRICT_JSON",
        "MODEL_OUTPUT_JSON_INVALID",
        "MODEL_OUTPUT_NOT_OBJECT",
        "MODEL_VISUAL_FACTOR_FIELD_SET_MISMATCH",
        "MODEL_AMBIENT_FACTOR_FIELD_SET_MISMATCH",
        "MODEL_COMPOSITION_FACTOR_FIELD_SET_MISMATCH",
    }
)
SEMANTIC_OUTPUT_FIELDS = frozenset(
    {
        "visual_description",
        "visual_query",
        "ambient_description",
        "ambient_query",
        "relation_kind",
    }
)


def _error_code(exc: BaseException) -> str:
    return str(exc).split(":", 1)[0]


def _raw_evidence(raw: str) -> dict[str, Any]:
    raw_bytes = raw.encode("utf-8")
    return {
        "raw_output": raw,
        "raw_output_bytes": len(raw_bytes),
        "raw_output_base64": base64.b64encode(raw_bytes).decode("ascii"),
        "raw_output_sha256": (
            "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
        ),
    }


def _semantic_scalar_multiset(value: Any) -> Counter[tuple[str, str]]:
    """Collect exact scalar content independent of JSON wrappers and keys."""

    scalars: Counter[tuple[str, str]] = Counter()

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif item is None:
            scalars[("null", "null")] += 1
        elif isinstance(item, bool):
            scalars[("bool", str(item).lower())] += 1
        elif isinstance(item, (int, float)):
            scalars[("number", repr(float(item)))] += 1
        elif isinstance(item, str):
            scalars[("string", item)] += 1

    visit(value)
    return scalars


def _all_object_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_all_object_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_object_keys(child))
    return keys


def _recover_semantic_json_for_guard(
    raw: str, semantic_fields: frozenset[str]
) -> Any | None:
    """Load only the whole constrained output for the scalar repair guard."""

    try:
        candidate = _strict_json_output(raw)
    except AuthoringError:
        return None
    if not isinstance(candidate, Mapping):
        return None
    if semantic_fields == AMBIENT_SEMANTIC_SCALAR_FIELDS:
        if "source_hint" in _all_object_keys(candidate):
            return None
        stack = [candidate]
        valid_tuples = []
        while stack:
            item = stack.pop()
            if isinstance(item, Mapping):
                if {
                    "event_kind",
                    "acoustic_properties",
                } <= set(item):
                    projected = {
                        "event_kind": item["event_kind"],
                        "acoustic_properties": item["acoustic_properties"],
                    }
                    try:
                        valid_tuples.append(
                            validate_ambient_semantic_tuple(projected)
                        )
                    except AuthoringError:
                        pass
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        if len(valid_tuples) != 1:
            return None
    elif not semantic_fields <= _all_object_keys(candidate):
        return None
    return candidate


def _schema_repair_candidate(
    raw: str,
    parser_error: str,
    semantic_fields: frozenset[str] = SEMANTIC_OUTPUT_FIELDS,
) -> Any | None:
    if _error_code(AuthoringError(parser_error)) not in REPAIRABLE_OUTPUT_ERRORS:
        return None
    return _recover_semantic_json_for_guard(raw, semantic_fields)


def _schema_repair_conversation(
    prompt: Mapping[str, Any],
    *,
    prior_raw: str,
    validation_error: str,
) -> list[dict[str, Any]]:
    payload = {
        "task": "schema_only_repair",
        "required_output_schema": prompt["user_payload"][
            "required_output_schema"
        ],
        "prior_validation_error": validation_error,
        "prior_raw_output": prior_raw,
        "constraints": {
            "preserve_every_semantic_scalar_value_exactly": True,
            "change_only_json_or_schema_form": True,
            "new_or_substituted_semantics_forbidden": True,
            "prose_or_markdown_forbidden": True,
            "return_exactly_one_json_object": True,
        },
    }
    instruction = (
        "This is the sole schema-only repair attempt. Preserve every semantic "
        "scalar value from the prior raw output exactly, including wording, "
        "numbers, booleans, and nulls. Change only JSON/schema representation "
        "to match the supplied schema. Do not add, remove, rewrite, normalize, "
        "or substitute semantic content. If exact content preservation is "
        "impossible, return the prior content unchanged. Return one strict JSON "
        "object and no prose or markdown."
    )
    return [
        {
            "role": "system",
            "content": [{"type": "text", "text": instruction}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            ],
        },
    ]


def _attempt_record(
    *,
    family_key: str,
    factor_key: str,
    factor_kind: str,
    component_ordinal: int | None,
    attempt: int,
    attempt_kind: str,
    raw: str,
    conversation: Sequence[Mapping[str, Any]],
    prompt: Mapping[str, Any],
    clip_records: Sequence[Mapping[str, Any]],
    model_identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    parser_error: str | None,
    prior_parser_error: str | None = None,
    prior_raw_output_sha256: str | None = None,
) -> dict[str, Any]:
    media_contract = metadata.get("media_contract")
    media_present = (
        media_contract.get("media_present")
        if isinstance(media_contract, Mapping)
        else None
    )
    if factor_kind == "visual":
        clip_hash_fields = ("video_sha256",)
    elif factor_kind == "ambient":
        clip_hash_fields = ("audio_sha256",)
    elif factor_kind == "family_composition":
        clip_hash_fields = ()
    else:
        raise AuthoringError("ATTEMPT_FACTOR_KIND_INVALID")
    expected_constraint_kind = (
        AMBIENT_CONSTRAINT_KIND
        if factor_kind == "ambient"
        else "json_object_boundary"
    )
    if metadata.get("constraint_kind") not in (
        None,
        expected_constraint_kind,
    ):
        raise AuthoringError("ATTEMPT_CONSTRAINT_KIND_MISMATCH")
    record = {
        "family_key": family_key,
        "factor_key": factor_key,
        "factor_kind": factor_kind,
        "component_ordinal": component_ordinal,
        "attempt": attempt,
        "attempt_kind": attempt_kind,
        **_raw_evidence(raw),
        "exact_conversation": list(conversation),
        "exact_conversation_sha256": semantic_hash(list(conversation)),
        "rendered_prompt": metadata.get("rendered_prompt"),
        "rendered_prompt_sha256": metadata.get("rendered_prompt_sha256"),
        "rendered_prompt_bytes": metadata.get("rendered_prompt_bytes"),
        "parser_error": parser_error,
        "prior_parser_error": prior_parser_error,
        "prior_raw_output_sha256": prior_raw_output_sha256,
        "system_prompt_sha256": prompt["system_prompt_sha256"],
        "user_payload_sha256": prompt["user_payload_sha256"],
        "combined_prompt_sha256": prompt["combined_prompt_sha256"],
        "media_present": media_present,
        "media_modality": (
            factor_kind
            if factor_kind in {"visual", "ambient"}
            else None
        ),
        "media_contract_sha256": (
            semantic_hash(media_contract)
            if isinstance(media_contract, Mapping)
            else None
        ),
        "clip_keys": [row["clip_key"] for row in clip_records],
        "clip_manifest_hashes": [
            {
                "clip_key": row["clip_key"],
                "start_us": row.get("start_us"),
                "end_us": row.get("end_us"),
                "duration_us": row.get("duration_us"),
                **{key: row.get(key) for key in clip_hash_fields},
            }
            for row in clip_records
        ],
        "model_identity": dict(model_identity),
        "schema_only_repair": attempt == 2,
        "semantic_repair_used": False,
        "retry_used": attempt == 2,
        "constraint_kind": expected_constraint_kind,
        "constraint_manifest": (
            json.loads(canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST))
            if factor_kind == "ambient"
            else None
        ),
        "constraint_manifest_sha256": (
            AMBIENT_CONSTRAINT_MANIFEST_SHA256
            if factor_kind == "ambient"
            else None
        ),
        "constraint_leaf_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            if factor_kind == "ambient"
            else None
        ),
        "constraint_reachable_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            if factor_kind == "ambient"
            else None
        ),
        **{
            key: value
            for key, value in metadata.items()
            if key
            not in {
                "rendered_prompt",
                "rendered_prompt_sha256",
                "rendered_prompt_bytes",
            }
        },
    }
    _validate_attempt_constraint_binding(record)
    return record


def _constrained_generation_error(
    metadata: Mapping[str, Any],
) -> str | None:
    stop_reason = metadata.get("stop_reason")
    if stop_reason in (
        None,
        "first_complete_top_level_json_object",
        "ambient_constraint_leaf_stop",
    ):
        return None
    if stop_reason == "ambient_constraint_unclosed_at_token_cap":
        return "MODEL_OUTPUT_AMBIENT_CONSTRAINT_UNCLOSED_AT_TOKEN_CAP"
    if stop_reason == "ambient_constraint_invalid_generated_sequence":
        return "MODEL_OUTPUT_AMBIENT_CONSTRAINT_INVALID_SEQUENCE"
    if stop_reason == "json_object_unclosed_at_token_cap":
        return "MODEL_OUTPUT_JSON_UNCLOSED_AT_TOKEN_CAP"
    if stop_reason == "json_object_unclosed_before_token_cap":
        return "MODEL_OUTPUT_JSON_UNCLOSED_BEFORE_TOKEN_CAP"
    return "MODEL_OUTPUT_CONSTRAINED_JSON_INVALID_SEQUENCE"


def _resolved_composition_prompt(
    family: Mapping[str, Any],
    component_factors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = composition_model_visible_prompt(
        str(family["shape"]), component_factors
    )
    return _prompt_record(
        factor_kind="family_composition",
        user_payload=payload,
        system_prompt=COMPOSITION_SYSTEM_PROMPT,
        family_key=str(family["family_key"]),
    )


def author_factor(
    processor: Any,
    model: Any,
    torch: Any,
    *,
    family_key: str,
    factor_key: str,
    factor_kind: str,
    component_ordinal: int | None,
    prompt: Mapping[str, Any],
    validator: Callable[[Any], dict[str, Any]],
    semantic_fields: frozenset[str],
    videos: Sequence[Any] | None,
    audios: Sequence[Any] | None,
    clip_records: Sequence[Mapping[str, Any]],
    model_identity: Mapping[str, Any],
    attempts: list[dict[str, Any]],
    attempts_path: Path,
) -> tuple[dict[str, Any], int]:
    """Author one fixed-schema factor with one bounded structural retry."""

    media_present = int(prompt.get("media_component_count", 0)) == 1
    conversation = _model_conversation(prompt)
    raw, metadata = _generate_one(
        processor,
        model,
        torch,
        conversation=conversation,
        media_present=media_present,
        videos=videos,
        audios=audios,
        factor_kind=factor_kind,
    )
    generation_error = _constrained_generation_error(metadata)
    initial = _attempt_record(
        family_key=family_key,
        factor_key=factor_key,
        factor_kind=factor_kind,
        component_ordinal=component_ordinal,
        attempt=1,
        attempt_kind="initial",
        raw=raw,
        conversation=conversation,
        prompt=prompt,
        clip_records=clip_records,
        model_identity=model_identity,
        metadata=metadata,
        parser_error=generation_error,
    )
    attempts.append(initial)
    atomic_jsonl(attempts_path, attempts)
    if generation_error is not None:
        raise AuthoringError(generation_error)
    try:
        parsed_value = _strict_json_output(raw)
        parsed = validator(parsed_value)
    except AuthoringError as exc:
        error = str(exc)
        initial["parser_error"] = error
        if factor_kind == "ambient":
            initial["schema_only_repair_eligible"] = False
            atomic_jsonl(attempts_path, attempts)
            raise
        candidate = _schema_repair_candidate(
            raw, error, semantic_fields=semantic_fields
        )
        repairable = candidate is not None
        initial["schema_only_repair_eligible"] = repairable
        atomic_jsonl(attempts_path, attempts)
        if not repairable:
            raise
    else:
        initial["schema_only_repair_eligible"] = False
        initial["parsed_output_sha256"] = _parsed_output_binding_hash(
            factor_kind, parsed
        )
        atomic_jsonl(attempts_path, attempts)
        return parsed, 1

    repair_conversation = _schema_repair_conversation(
        prompt,
        prior_raw=raw,
        validation_error=error,
    )
    repair_raw, repair_metadata = _generate_one(
        processor,
        model,
        torch,
        conversation=repair_conversation,
        media_present=False,
        factor_kind=factor_kind,
    )
    repair_generation_error = _constrained_generation_error(repair_metadata)
    repair = _attempt_record(
        family_key=family_key,
        factor_key=factor_key,
        factor_kind=factor_kind,
        component_ordinal=component_ordinal,
        attempt=2,
        attempt_kind="schema_only_repair",
        raw=repair_raw,
        conversation=repair_conversation,
        prompt=prompt,
        clip_records=clip_records,
        model_identity=model_identity,
        metadata=repair_metadata,
        parser_error=repair_generation_error,
        prior_parser_error=error,
        prior_raw_output_sha256=initial["raw_output_sha256"],
    )
    attempts.append(repair)
    atomic_jsonl(attempts_path, attempts)
    if repair_generation_error is not None:
        raise AuthoringError(
            f"SCHEMA_ONLY_REPAIR_FAILED:{repair_generation_error}"
        )
    try:
        repair_value = _strict_json_output(repair_raw)
        if _semantic_scalar_multiset(candidate) != _semantic_scalar_multiset(
            repair_value
        ):
            repair["parser_error"] = "SCHEMA_REPAIR_CHANGED_SEMANTIC_CONTENT"
            repair["content_preserving_guard_passed"] = False
            atomic_jsonl(attempts_path, attempts)
            raise AuthoringError("SCHEMA_REPAIR_CHANGED_SEMANTIC_CONTENT")
        repair_parsed = validator(repair_value)
    except AuthoringError as exc:
        repair["parser_error"] = str(exc)
        atomic_jsonl(attempts_path, attempts)
        if _error_code(exc) == "SCHEMA_REPAIR_CHANGED_SEMANTIC_CONTENT":
            raise
        raise AuthoringError(
            f"SCHEMA_ONLY_REPAIR_FAILED:{_error_code(exc)}"
        ) from exc
    repair["content_preserving_guard_passed"] = True
    repair["parsed_output_sha256"] = _parsed_output_binding_hash(
        factor_kind, repair_parsed
    )
    atomic_jsonl(attempts_path, attempts)
    return repair_parsed, 2


def author_one_family(
    processor: Any,
    model: Any,
    torch: Any,
    *,
    family: Mapping[str, Any],
    visual_prompts: Sequence[Mapping[str, Any]],
    ambient_prompts: Sequence[Mapping[str, Any]],
    videos: Sequence[Any],
    audios: Sequence[Any],
    clip_records: Sequence[Mapping[str, Any]],
    model_identity: Mapping[str, Any],
    attempts: list[dict[str, Any]],
    attempts_path: Path,
    prompt_manifest: dict[str, Any] | None = None,
    prompt_manifest_path: Path | None = None,
) -> tuple[dict[str, Any], int]:
    """Author independent video/audio factors, then text-only composition."""

    family_key = str(family["family_key"])
    component_count = len(family["intervals"])
    if not (
        len(visual_prompts)
        == len(ambient_prompts)
        == len(videos)
        == len(audios)
        == len(clip_records)
        == component_count
    ):
        raise AuthoringError("FAMILY_FACTOR_INPUT_COUNT_MISMATCH")

    visual_factors: list[dict[str, str]] = []
    ambient_factors: list[dict[str, Any]] = []
    total_calls = 0
    for ordinal, (
        visual_prompt,
        ambient_prompt,
        video,
        audio,
        clip_record,
    ) in enumerate(
        zip(
            visual_prompts,
            ambient_prompts,
            videos,
            audios,
            clip_records,
            strict=True,
        ),
        1,
    ):
        if (
            visual_prompt.get("factor_kind") != "visual"
            or ambient_prompt.get("factor_kind") != "ambient"
            or visual_prompt.get("family_key") != family_key
            or ambient_prompt.get("family_key") != family_key
            or visual_prompt.get("component_ordinal") != ordinal
            or ambient_prompt.get("component_ordinal") != ordinal
            or visual_prompt.get("media_modalities") != ["visual"]
            or ambient_prompt.get("media_modalities") != ["ambient"]
            or visual_prompt.get("media_component_clip_keys")
            != [clip_record["clip_key"]]
            or ambient_prompt.get("media_component_clip_keys")
            != [clip_record["clip_key"]]
        ):
            raise AuthoringError("COMPONENT_PROMPT_BINDING_MISMATCH")
        visual_factor, calls = author_factor(
            processor,
            model,
            torch,
            family_key=family_key,
            factor_key=f"{family_key}:component:{ordinal}:visual",
            factor_kind="visual",
            component_ordinal=ordinal,
            prompt=visual_prompt,
            validator=validate_visual_factor_output,
            semantic_fields=frozenset(VISUAL_OUTPUT_SCHEMA),
            videos=[video],
            audios=None,
            clip_records=[clip_record],
            model_identity=model_identity,
            attempts=attempts,
            attempts_path=attempts_path,
        )
        visual_factors.append(visual_factor)
        total_calls += calls
        ambient_factor, calls = author_factor(
            processor,
            model,
            torch,
            family_key=family_key,
            factor_key=f"{family_key}:component:{ordinal}:ambient",
            factor_kind="ambient",
            component_ordinal=ordinal,
            prompt=ambient_prompt,
            validator=validate_ambient_factor_output,
            semantic_fields=AMBIENT_SEMANTIC_SCALAR_FIELDS,
            videos=None,
            audios=[audio],
            clip_records=[clip_record],
            model_identity=model_identity,
            attempts=attempts,
            attempts_path=attempts_path,
        )
        ambient_factors.append(ambient_factor)
        total_calls += calls

    component_factors = [
        {**visual, **ambient}
        for visual, ambient in zip(
            visual_factors, ambient_factors, strict=True
        )
    ]

    composition_prompt = _resolved_composition_prompt(
        family, component_factors
    )
    if prompt_manifest is not None:
        prompt_manifest.setdefault("resolved_composition_prompts", []).append(
            composition_prompt
        )
        for contract in prompt_manifest.get("composition_contracts", []):
            if contract.get("family_key") == family_key:
                contract["resolved"] = True
                contract["resolved_user_payload_sha256"] = composition_prompt[
                    "user_payload_sha256"
                ]
                contract["resolved_combined_prompt_sha256"] = (
                    composition_prompt["combined_prompt_sha256"]
                )
                break
        if prompt_manifest_path is not None:
            atomic_json(prompt_manifest_path, prompt_manifest)

    composition_factor, calls = author_factor(
        processor,
        model,
        torch,
        family_key=family_key,
        factor_key=f"{family_key}:family_composition",
        factor_kind="family_composition",
        component_ordinal=None,
        prompt=composition_prompt,
        validator=lambda value: validate_composition_factor_output(
            value,
            component_count=component_count,
            family_shape=str(family["shape"]),
        ),
        semantic_fields=frozenset(COMPOSITION_OUTPUT_SCHEMA),
        videos=None,
        audios=None,
        clip_records=[],
        model_identity=model_identity,
        attempts=attempts,
        attempts_path=attempts_path,
    )
    total_calls += calls
    return (
        assemble_family_factors(
            family, visual_factors, ambient_factors, composition_factor
        ),
        total_calls,
    )


def _run_asr(
    root: Path,
    clips: Mapping[str, Mapping[str, Path]],
    *,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    import numpy as np
    import torch
    from transformers import pipeline

    snapshot = _repo_path(root, WHISPER_SNAPSHOT)
    with deny_network():
        transcriber = pipeline(
            "automatic-speech-recognition",
            model=str(snapshot),
            tokenizer=str(snapshot),
            feature_extractor=str(snapshot),
            device=-1,
            torch_dtype=torch.float32,
        )
    transcripts: dict[str, str] = {}
    rows = []
    for clip_key in sorted(clips):
        waveform = np.load(clips[clip_key]["audio"], allow_pickle=False)
        started = time.monotonic()
        with deny_network() as attempts:
            result = transcriber(
                {"raw": waveform, "sampling_rate": 16_000}
            )
        text = " ".join(str(result.get("text", "")).split())
        transcripts[clip_key] = text
        row = {
            "clip_key": clip_key,
            "raw_output": result,
            "normalized_transcript": text,
            "normalized_transcript_sha256": semantic_hash(text),
            "degeneracy_analysis": degenerate_asr_analysis(text),
            "latency_seconds": round(time.monotonic() - started, 6),
            "network_attempts": attempts["count"],
            "model_visible_to_authoring": False,
            "audit_only": True,
        }
        rows.append(row)
        if progress_callback is not None:
            progress_callback(row)
    return transcripts, rows


def _text_embedder(root: Path, snapshot: Path) -> Callable[
    [Sequence[str]], Sequence[Sequence[float]]
]:
    import torch
    from transformers import AutoModel, AutoProcessor

    model_path = _repo_path(root, snapshot)
    with deny_network():
        processor = AutoProcessor.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False
        )
        model = AutoModel.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=False,
            low_cpu_mem_usage=True,
        ).eval()

    def embed(texts: Sequence[str]) -> Sequence[Sequence[float]]:
        vectors = []
        batch_size = 16
        for offset in range(0, len(texts), batch_size):
            batch = list(texts[offset : offset + batch_size])
            inputs = processor(
                text=batch, return_tensors="pt", padding=True, truncation=True
            )
            with torch.inference_mode(), deny_network():
                features = model.get_text_features(**inputs)
            if hasattr(features, "pooler_output"):
                features = features.pooler_output
            features = features / features.norm(dim=-1, keepdim=True)
            vectors.extend(features.float().cpu().tolist())
        return vectors

    return embed


def _seal_output(output_dir: Path) -> dict[str, Any]:
    _validate_static_ambient_contract()
    files = {
        name: {
            "sha256": "sha256:" + file_sha256(output_dir / name),
            "bytes": (output_dir / name).stat().st_size,
        }
        for name in OUTPUT_FILES
    }
    seal = {
        "schema_version": SEAL_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "sealed_at": CURRENT_DATE,
        "status": "SEALED_AUTHORING_COMPLETE_SCORING_NOT_RUN",
        "files": files,
        "ambient_constraint": ambient_constraint_contract(),
        "scoring_stage_executed": False,
        "retrieval_rankings_read": False,
        "retrieval_outcomes_read": False,
        "non_target_vectors_read": False,
    }
    atomic_json(output_dir / "seal.json", seal, mode=0o400)
    for name in OUTPUT_FILES:
        os.chmod(output_dir / name, 0o400)
    return seal


def _peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


@contextlib.contextmanager
def timed_stage(
    stage_times: dict[str, float], key: str
) -> Iterator[None]:
    """Record completed or partial wall time without losing failure work."""

    started = time.monotonic()
    try:
        yield
    except BaseException:
        stage_times[f"{key}_partial_seconds"] = round(
            time.monotonic() - started, 6
        )
        raise
    else:
        stage_times[f"{key}_seconds"] = round(
            time.monotonic() - started, 6
        )


def retained_runtime_counts(
    staging: Path,
    provided: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Recover monotonic work counts from retained records on any failure."""

    counts = {
        "authoring_model_calls": 0,
        "initial_authoring_calls": 0,
        "visual_initial_authoring_calls": 0,
        "ambient_initial_authoring_calls": 0,
        "composition_initial_authoring_calls": 0,
        "schema_only_repair_calls": 0,
        "asr_model_calls": 0,
        "target_clip_decodes": 0,
    }
    for key, value in dict(provided or {}).items():
        if key in counts:
            counts[key] = max(counts[key], int(value))
    attempts_path = staging / "raw_attempts.jsonl"
    if attempts_path.is_file():
        attempts = []
        for line in attempts_path.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                attempts.append(json.loads(line))
        counts["authoring_model_calls"] = max(
            counts["authoring_model_calls"], len(attempts)
        )
        counts["initial_authoring_calls"] = max(
            counts["initial_authoring_calls"],
            sum(row.get("attempt_kind") == "initial" for row in attempts),
        )
        counts["visual_initial_authoring_calls"] = max(
            counts["visual_initial_authoring_calls"],
            sum(
                row.get("attempt_kind") == "initial"
                and row.get("factor_kind") == "visual"
                for row in attempts
            ),
        )
        counts["ambient_initial_authoring_calls"] = max(
            counts["ambient_initial_authoring_calls"],
            sum(
                row.get("attempt_kind") == "initial"
                and row.get("factor_kind") == "ambient"
                for row in attempts
            ),
        )
        counts["composition_initial_authoring_calls"] = max(
            counts["composition_initial_authoring_calls"],
            sum(
                row.get("attempt_kind") == "initial"
                and row.get("factor_kind") == "family_composition"
                for row in attempts
            ),
        )
        counts["schema_only_repair_calls"] = max(
            counts["schema_only_repair_calls"],
            sum(
                row.get("attempt_kind") == "schema_only_repair"
                for row in attempts
            ),
        )
    target_path = staging / "target_manifest.json"
    if target_path.is_file():
        with contextlib.suppress(
            OSError, json.JSONDecodeError, TypeError, ValueError
        ):
            target = load_json(target_path)
            retained = int(
                target.get("target_count", len(target.get("targets", [])))
            )
            counts["target_clip_decodes"] = max(
                counts["target_clip_decodes"], retained
            )
    asr_path = staging / "asr_audit_inventory.json"
    if asr_path.is_file():
        with contextlib.suppress(
            OSError, json.JSONDecodeError, TypeError, ValueError
        ):
            asr = load_json(asr_path)
            counts["asr_model_calls"] = max(
                counts["asr_model_calls"], len(asr.get("rows", []))
            )
    return counts


def failure_capsule_path(
    output_path: Path, authorization_id: str
) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", authorization_id).strip("-")
    if not safe_id:
        safe_id = "unknown-authorization"
    return output_path.with_name(f"{output_path.name}.failure-{safe_id}")


def install_failure_capsule(
    staging: Path,
    *,
    output_path: Path,
    authorization_id: str,
    exc: BaseException,
    wall_started: float,
    stage_times: Mapping[str, float],
    failed_stage: str | None,
    runtime_counts: Mapping[str, int] | None = None,
    capsule_kind: str = "full_pipeline",
    pipeline_id: str = PIPELINE_ID,
) -> Path:
    """Atomically preserve fail-closed evidence while deleting clip arrays."""

    shutil.rmtree(staging / "clips", ignore_errors=True)
    capsule_path = failure_capsule_path(output_path, authorization_id)
    if capsule_path.exists():
        raise AuthoringError("FAILURE_CAPSULE_ALREADY_EXISTS") from exc
    stderr_summary = {
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        "traceback_tail": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-16_384:],
    }
    recovered_counts = retained_runtime_counts(staging, runtime_counts)
    runtime = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-failure-runtime/1.0"
        ),
        "pipeline_id": pipeline_id,
        "capsule_kind": capsule_kind,
        "status": "FAIL_CLOSED_EVIDENCE_PRESERVED",
        "wall_seconds": round(time.monotonic() - wall_started, 6),
        "peak_rss_bytes": _peak_rss_bytes(),
        "stage_wall_seconds": dict(stage_times),
        "failed_stage": failed_stage,
        "threads": THREADS,
        "network_requests": 0,
        "ephemeral_clip_arrays_removed": True,
        **recovered_counts,
        "runtime_counts_recovered_from_retained_evidence": True,
    }
    atomic_json(staging / "resource_runtime.failed.json", runtime)
    preserved_files = {}
    for path in sorted(staging.iterdir()):
        if path.is_file():
            preserved_files[path.name] = {
                "sha256": "sha256:" + file_sha256(path),
                "bytes": path.stat().st_size,
            }
    failure = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-failure-capsule/1.0"
        ),
        "pipeline_id": pipeline_id,
        "capsule_kind": capsule_kind,
        "status": "FAIL_CLOSED_EVIDENCE_PRESERVED",
        "authorization_id": authorization_id,
        "failure_error": str(exc),
        "failure_error_code": _error_code(exc),
        "stderr_summary": stderr_summary,
        "ephemeral_clip_arrays_removed": True,
        "raw_model_evidence_retained": (
            staging / "raw_attempts.jsonl"
        ).is_file(),
        "preserved_files_before_capsule_manifest": preserved_files,
        "installed_output": False,
    }
    atomic_json(staging / "failure_capsule.json", failure)
    os.replace(staging, capsule_path)
    return capsule_path


def execute(
    root: Path,
    *,
    bundle: Path,
    media: Path,
    output: Path,
    authorization: Path,
    emit_explicit_baseline: bool = False,
) -> dict[str, Any]:
    """Execute once into a staging directory, then seal atomically."""

    _offline_environment()
    structural = load_structural_bundle(root, bundle)
    preflight_result = preflight(root, bundle=bundle, media=media)
    if preflight_result["status"] != "READY":
        raise AuthoringError(
            "PREFLIGHT_FAIL_CLOSED:"
            + ",".join(preflight_result["failures"])
        )
    authorization_value = validate_authorization(
        root,
        authorization,
        structural=structural,
        output=output,
    )
    output_path = _repo_path(root, output)
    if output_path.exists():
        raise AuthoringError("OUTPUT_ALREADY_EXISTS")
    prompt_manifest = build_prompt_manifest(structural)
    media_path = _repo_path(root, media)
    staging_parent = output_path.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_path.name}.staging-", dir=staging_parent
        )
    )
    os.chmod(staging, 0o700)
    started = time.monotonic()
    rss_started = _peak_rss_bytes()
    stage_times: dict[str, float] = {}
    failed_stage: str | None = "exact_clip_extraction"
    runtime_counts = {
        "authoring_model_calls": 0,
        "initial_authoring_calls": 0,
        "schema_only_repair_calls": 0,
        "asr_model_calls": 0,
        "target_clip_decodes": 0,
    }
    try:
        partial_clip_records: list[dict[str, Any]] = []

        def retain_clip_record(record: Mapping[str, Any]) -> None:
            partial_clip_records.append(dict(record))
            atomic_json(
                staging / "target_manifest.json",
                {
                    "schema_version": (
                        "av-trace.p23-102-query-target-manifest/3.0"
                    ),
                    "pipeline_id": PIPELINE_ID,
                    "source_media": {
                        "path": str(media),
                        "sha256": "sha256:" + file_sha256(media_path),
                    },
                    "target_count": len(partial_clip_records),
                    "targets": partial_clip_records,
                    "decode_scope": "EXACT_TARGET_INTERVALS_ONLY",
                    "partial_progress": True,
                },
            )

        with timed_stage(stage_times, "exact_clip_extraction"):
            clips, clip_records = _extract_exact_clips(
                media_path,
                structural["targets"],
                staging,
                progress_callback=retain_clip_record,
            )
        runtime_counts["target_clip_decodes"] = len(clip_records)
        target_manifest = {
            "schema_version": (
                "av-trace.p23-102-query-target-manifest/3.0"
            ),
            "pipeline_id": PIPELINE_ID,
            "source_media": {
                "path": str(media),
                "sha256": "sha256:" + file_sha256(media_path),
            },
            "target_count": len(clip_records),
            "targets": clip_records,
            "decode_scope": "EXACT_TARGET_INTERVALS_ONLY",
            "video_sampling": "16 evenly spaced frames per exact interval",
            "audio_sampling": "full exact interval resampled to mono 16 kHz",
            "full_source_scan": False,
            "non_target_media_decoded": False,
            "ephemeral_arrays_removed_before_seal": True,
        }
        atomic_json(staging / "target_manifest.json", target_manifest)
        atomic_json(staging / "prompt_manifest.json", prompt_manifest)
        contract = {
            "schema_version": (
                AUTHORING_CONTRACT_SCHEMA_VERSION
            ),
            "pipeline_id": PIPELINE_ID,
            "date": CURRENT_DATE,
            "authorization": authorization_value,
            "pipeline_sha256": pipeline_tool_sha256(root),
            "bundle_file_hashes": structural["file_hashes"],
            "counts": structural["counts"],
            "factorization": {
                "visual_initial_calls": EXPECTED_VISUAL_FACTORS,
                "ambient_initial_calls": EXPECTED_AMBIENT_FACTORS,
                "composition_initial_calls": EXPECTED_COMPOSITION_FACTORS,
                "total_initial_factor_calls": EXPECTED_INITIAL_FACTORS,
                "maximum_schema_only_repair_calls": (
                    EXPECTED_MAX_SCHEMA_ONLY_REPAIRS
                ),
                "maximum_authoring_model_calls": (
                    EXPECTED_INITIAL_FACTORS
                    + EXPECTED_MAX_SCHEMA_ONLY_REPAIRS
                ),
                "visual_schema": dict(VISUAL_OUTPUT_SCHEMA),
                "ambient_schema": dict(AMBIENT_OUTPUT_SCHEMA),
                "ambient_registry_sha256": (
                    STRUCTURED_AMBIENT_REGISTRY_SHA256
                ),
                "ambient_generator_sha256": AMBIENT_GENERATOR_SHA256,
                "ambient_template_sha256": AMBIENT_TEMPLATE_SHA256,
                "ambient_constraint_kind": AMBIENT_CONSTRAINT_KIND,
                "ambient_constraint_manifest": json.loads(
                    canonical_bytes(AMBIENT_CONSTRAINT_MANIFEST)
                ),
                "ambient_constraint_manifest_sha256": (
                    AMBIENT_CONSTRAINT_MANIFEST_SHA256
                ),
                "ambient_constraint_leaf_count": (
                    EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
                ),
                "ambient_constraint_reachable_count": (
                    EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
                ),
                "ambient_schema_repair_permitted": False,
                "ambient_model_authored_natural_language": False,
                "ambient_derived_text_model_calls": 0,
                "composition_schema": dict(COMPOSITION_OUTPUT_SCHEMA),
                "composition_relation_kind_by_shape": dict(
                    RELATION_KIND_BY_SHAPE
                ),
                "composition_frozen_shape_and_count_bound": True,
                "composition_direction_generated_mechanically": True,
                "composition_relation_text_generated_mechanically": True,
                "composition_model_authored_natural_language": False,
                "ordinals_assigned_mechanically": True,
                "visual_media_contract": "video_only_audio_none",
                "ambient_media_contract": "audio_only_video_none",
                "composition_media_present": False,
                "component_assembly": (
                    "exact_same_clip_visual_and_ambient_factor_pair"
                ),
                "accepted_factor_manifest_sealed": True,
                "final_rows_bind_exact_accepted_factor": True,
                "cross_factor_fill_or_substitution_permitted": False,
                "ambient_semantic_tuple_duplicate_gate": {
                    "same_family_duplicate": "FAIL_CLOSED",
                    "global_collision_ledger_emitted": True,
                    "automatic_rewrite_permitted": False,
                    "authoring_retry_permitted": False,
                    "replacement_governance": "outer_R22_selection_only",
                },
            },
            "model_identities": {
                "authoring": {
                    "repo_id": "Qwen/Qwen2.5-Omni-7B",
                    "revision": (
                        "ae9e1690543ffd5c0221dc27f79834d0294cba00"
                    ),
                    "snapshot": str(OMNI_SNAPSHOT),
                    "generation": {
                        "do_sample": False,
                        "max_new_tokens": MAX_NEW_TOKENS,
                        "temperature": None,
                        "seed": 0,
                        "constrained_json": True,
                        "ambient_constraint_kind": (
                            AMBIENT_CONSTRAINT_KIND
                        ),
                        "ambient_constraint_manifest_sha256": (
                            AMBIENT_CONSTRAINT_MANIFEST_SHA256
                        ),
                        "ambient_constraint_leaf_count": (
                            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
                        ),
                        "ambient_constraint_reachable_count": (
                            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
                        ),
                        "assistant_prefill": JSON_ASSISTANT_PREFILL,
                        "stop_boundary": (
                            "ambient leaf plus EOS/stop; JSON boundary for "
                            "visual/composition"
                        ),
                    },
                },
                "asr_leakage_audit": {
                    "repo_id": "openai/whisper-tiny.en",
                    "revision": (
                        "87c7102498dcde7456f24cfd30239ca606ed9063"
                    ),
                    "snapshot": str(WHISPER_SNAPSHOT),
                },
                "visual_text_collision_audit": {
                    "repo_id": "google/siglip2-base-patch16-224",
                    "revision": (
                        "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
                    ),
                    "snapshot": str(SIGLIP_SNAPSHOT),
                },
                "ambient_text_collision_audit": {
                    "repo_id": "laion/clap-htsat-unfused",
                    "revision": (
                        "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
                    ),
                    "snapshot": str(CLAP_SNAPSHOT),
                },
            },
            "separation": {
                "retrieval_rankings_visible": False,
                "retrieval_scores_visible": False,
                "retrieval_outcomes_visible": False,
                "non_target_vectors_visible": False,
                "human_semantic_labels_visible": False,
                "answer_keys_visible": False,
                "scoring_stage": "SEALED_LATER_STAGE",
            },
        }
        atomic_json(staging / "authoring_contract.json", contract)

        failed_stage = "omni_model_load"
        with timed_stage(stage_times, "omni_load"):
            processor, model, torch = _load_omni(root)
        parsed_by_family: dict[str, Mapping[str, Any]] = {}
        attempts: list[dict[str, Any]] = []
        visual_prompts_by_family: dict[str, list[Mapping[str, Any]]] = (
            defaultdict(list)
        )
        ambient_prompts_by_family: dict[str, list[Mapping[str, Any]]] = (
            defaultdict(list)
        )
        for row in prompt_manifest["visual_prompts"]:
            visual_prompts_by_family[str(row["family_key"])].append(row)
        for row in prompt_manifest["ambient_prompts"]:
            ambient_prompts_by_family[str(row["family_key"])].append(row)
        for rows in [
            *visual_prompts_by_family.values(),
            *ambient_prompts_by_family.values(),
        ]:
            rows.sort(key=lambda row: int(row["component_ordinal"]))
        clip_records_by_key = {
            row["clip_key"]: row for row in clip_records
        }
        failed_stage = "omni_authoring"
        with timed_stage(stage_times, "omni_authoring"):
            for family in structural["families"]:
                family_key = family["family_key"]
                media_assets = [
                    clips[row["clip_key"]] for row in family["intervals"]
                ]
                videos = []
                audios = []
                for asset in media_assets:
                    video, audio = _decode_av(asset)
                    videos.append(video)
                    audios.append(audio)
                parsed, calls = author_one_family(
                    processor,
                    model,
                    torch,
                    family=family,
                    visual_prompts=visual_prompts_by_family[family_key],
                    ambient_prompts=ambient_prompts_by_family[family_key],
                    videos=videos,
                    audios=audios,
                    clip_records=[
                        clip_records_by_key[row["clip_key"]]
                        for row in family["intervals"]
                    ],
                    model_identity=contract["model_identities"]["authoring"],
                    attempts=attempts,
                    attempts_path=staging / "raw_attempts.jsonl",
                    prompt_manifest=prompt_manifest,
                    prompt_manifest_path=staging / "prompt_manifest.json",
                )
                parsed_by_family[family_key] = parsed
                runtime_counts["authoring_model_calls"] += calls
                initial_calls = 2 * len(family["intervals"]) + 1
                runtime_counts["initial_authoring_calls"] += initial_calls
                runtime_counts["schema_only_repair_calls"] += (
                    calls - initial_calls
                )

        accepted_factor_manifest = build_accepted_factor_manifest(
            structural, parsed_by_family, attempts
        )
        atomic_json(
            staging / "accepted_factor_manifest.json",
            accepted_factor_manifest,
        )
        queries, descriptions = materialize_query_records(
            structural,
            parsed_by_family,
            accepted_factor_manifest,
        )
        validate_accepted_factor_provenance(
            accepted_factor_manifest,
            attempts,
            queries,
            descriptions,
        )
        tuple_collisions = ambient_semantic_tuple_duplicate_audit(
            accepted_factor_manifest,
            queries,
            scope="full_authoring",
        )
        atomic_json(
            staging / "ambient_semantic_tuple_collisions.json",
            tuple_collisions,
        )
        if tuple_collisions["status"] != "PASS":
            raise AuthoringError(
                "AMBIENT_SEMANTIC_TUPLE_DUPLICATE_FAIL_CLOSED"
            )
        failed_stage = "whisper_leakage_audit"
        partial_asr_rows: list[dict[str, Any]] = []

        def retain_asr_row(row: Mapping[str, Any]) -> None:
            partial_asr_rows.append(dict(row))
            atomic_json(
                staging / "asr_audit_inventory.json",
                {
                    "schema_version": (
                        "av-trace.p23-102-query-asr-audit-inventory/2.0"
                    ),
                    "model_identity": contract["model_identities"][
                        "asr_leakage_audit"
                    ],
                    "authoring_model_visible": False,
                    "exact_target_clips_only": True,
                    "partial_progress": True,
                    "rows": partial_asr_rows,
                },
            )

        with timed_stage(stage_times, "whisper_leakage_audit"):
            transcripts, asr_rows = _run_asr(
                root, clips, progress_callback=retain_asr_row
            )
        runtime_counts["asr_model_calls"] = len(asr_rows)
        atomic_json(
            staging / "asr_audit_inventory.json",
            asr_inventory := {
                "schema_version": (
                    "av-trace.p23-102-query-asr-audit-inventory/2.0"
                ),
                "model_identity": contract["model_identities"][
                    "asr_leakage_audit"
                ],
                "authoring_model_visible": False,
                "exact_target_clips_only": True,
                "rows": asr_rows,
            },
        )
        failed_stage = "query_collision_audits"
        with timed_stage(stage_times, "query_collision_audits"):
            visual_embed = _text_embedder(root, SIGLIP_SNAPSHOT)
            ambient_embed = _text_embedder(root, CLAP_SNAPSHOT)
            audits = audit_authored_content(
                structural,
                queries,
                descriptions,
                transcripts_by_clip=transcripts,
                embed_visual=visual_embed,
                embed_ambient=ambient_embed,
            )
        audits["input_digest"] = _audit_input_digest(
            structural,
            queries,
            descriptions,
            asr_inventory,
        )
        audits["input_hashes"] = {
            "prompt_manifest": semantic_hash(prompt_manifest),
            "accepted_factor_manifest": (
                accepted_factor_manifest["manifest_payload_sha256"]
            ),
            "asr_inventory": semantic_hash(asr_inventory),
            "queries": semantic_hash(queries),
            "descriptions": semantic_hash(descriptions),
        }
        if audits["status"] != "PASS":
            atomic_json(staging / "audits.failed.json", audits)
            raise AuthoringError(
                "AUTHORING_AUDIT_FAIL_CLOSED:"
                + ",".join(audits["failures"])
            )
        atomic_json(staging / "audits.json", audits)
        authored = {
            "schema_version": AUTHORED_QUERIES_SCHEMA_VERSION,
            "pipeline_id": PIPELINE_ID,
            "status": "MACHINE_AUTHORED_AUDITED_NOT_SCORED",
            "query_count": len(queries),
            "description_count": len(descriptions),
            "accepted_factor_manifest_sha256": (
                accepted_factor_manifest["manifest_payload_sha256"]
            ),
            "prompt_manifest_sha256": semantic_hash(prompt_manifest),
            "audits_input_digest": audits["input_digest"],
            "audits_payload_sha256": semantic_hash(audits),
            "queries": queries,
            "descriptions": descriptions,
            "human_semantic_labels": [],
            "retrieval_results": [],
            "scoring_results": [],
        }
        atomic_json(staging / "authored_queries.json", authored)
        if emit_explicit_baseline:
            atomic_json(
                staging / "explicit_template_baseline.json",
                explicit_template_baseline(structural),
            )
        failed_stage = "seal_output"
        shutil.rmtree(staging / "clips", ignore_errors=True)
        runtime = {
            "schema_version": (
                RUNTIME_SCHEMA_VERSION
            ),
            "wall_seconds": round(time.monotonic() - started, 6),
            "peak_rss_bytes": _peak_rss_bytes(),
            "peak_rss_at_start_bytes": rss_started,
            "stage_wall_seconds": stage_times,
            "threads": THREADS,
            "network_requests": 0,
            "ambient_constraint": ambient_constraint_contract(),
            **runtime_counts,
            "visual_initial_authoring_calls": EXPECTED_VISUAL_FACTORS,
            "ambient_initial_authoring_calls": EXPECTED_AMBIENT_FACTORS,
            "composition_initial_authoring_calls": (
                EXPECTED_COMPOSITION_FACTORS
            ),
            "full_pipeline_executed": False,
            "retrieval_scoring_executed": False,
            "ephemeral_clip_arrays_removed": True,
        }
        atomic_json(staging / "resource_runtime.json", runtime)
        _seal_output(staging)
        os.replace(staging, output_path)
        return load_json(output_path / "seal.json")
    except Exception as exc:
        install_failure_capsule(
            staging,
            output_path=output_path,
            authorization_id=str(authorization_value["authorization_id"]),
            exc=exc,
            wall_started=started,
            stage_times=stage_times,
            failed_stage=failed_stage,
            runtime_counts=runtime_counts,
        )
        raise


def validate_output_integrity_only(
    root: Path, output: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    """Validate sealed internal consistency without claiming external trust.

    This compatibility validator is intentionally integrity-only: the main
    full pipeline's historical authorization receipt is embedded in its
    output contract, so an output writer can coordinate a reseal.  Callers
    must not interpret this result as execution attestation.
    """

    trusted_constraint_context = trusted_ambient_constraint_context()
    output_path = _repo_path(root, output)
    seal_path = output_path / "seal.json"
    if not seal_path.is_file():
        raise AuthoringError("OUTPUT_SEAL_MISSING")
    seal = load_json(seal_path)
    if seal.get("status") != "SEALED_AUTHORING_COMPLETE_SCORING_NOT_RUN":
        raise AuthoringError("OUTPUT_SEAL_STATUS_INVALID")
    if (
        seal.get("schema_version") != SEAL_SCHEMA_VERSION
        or seal.get("ambient_constraint") != ambient_constraint_contract()
    ):
        raise AuthoringError("OUTPUT_SEAL_R20_CONSTRAINT_INVALID")
    if set(seal.get("files", {})) != set(OUTPUT_FILES):
        raise AuthoringError("OUTPUT_SEAL_FILE_SET_INVALID")
    for name, record in seal.get("files", {}).items():
        path = output_path / name
        if (
            not path.is_file()
            or "sha256:" + file_sha256(path) != record.get("sha256")
            or path.stat().st_size != record.get("bytes")
        ):
            raise AuthoringError(f"SEALED_FILE_MISMATCH:{name}")
    authored = load_json(output_path / "authored_queries.json")
    audits = load_json(output_path / "audits.json")
    contract = load_json(output_path / "authoring_contract.json")
    target_manifest = load_json(output_path / "target_manifest.json")
    prompt_manifest = load_json(output_path / "prompt_manifest.json")
    asr_inventory = load_json(output_path / "asr_audit_inventory.json")
    runtime = load_json(output_path / "resource_runtime.json")
    accepted = load_json(output_path / "accepted_factor_manifest.json")
    tuple_collisions = load_json(
        output_path / "ambient_semantic_tuple_collisions.json"
    )
    if (
        contract.get("schema_version") != AUTHORING_CONTRACT_SCHEMA_VERSION
        or prompt_manifest.get("schema_version")
        != PROMPT_MANIFEST_SCHEMA_VERSION
        or accepted.get("schema_version")
        != ACCEPTED_FACTOR_MANIFEST_SCHEMA_VERSION
        or authored.get("schema_version") != AUTHORED_QUERIES_SCHEMA_VERSION
        or runtime.get("schema_version") != RUNTIME_SCHEMA_VERSION
        or runtime.get("ambient_constraint")
        != ambient_constraint_contract()
    ):
        raise AuthoringError("SEALED_R20_SCHEMA_OR_CONSTRAINT_INVALID")
    factorization = contract.get("factorization")
    if not isinstance(factorization, Mapping):
        raise AuthoringError("SEALED_R20_SCHEMA_OR_CONSTRAINT_INVALID")
    _validate_ambient_derivation_contract(
        factorization,
        error="SEALED_R20_SCHEMA_OR_CONSTRAINT_INVALID",
    )
    attempts = [
        json.loads(line)
        for line in (output_path / "raw_attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if authored.get("query_count") != EXPECTED_QUERY_COUNT:
        raise AuthoringError("SEALED_QUERY_COUNT_MISMATCH")
    if audits.get("status") != "PASS":
        raise AuthoringError("SEALED_AUDIT_NOT_PASS")
    structural = _structural_from_sealed_contract(
        contract, target_manifest, prompt_manifest
    )
    expected = derive_expected_factor_specs(structural, prompt_manifest)
    if len(expected) != EXPECTED_INITIAL_FACTORS:
        raise AuthoringError("SEALED_INITIAL_FACTOR_COUNT_MISMATCH")
    if target_manifest.get("target_count") != EXPECTED_TARGET_CLIPS:
        raise AuthoringError("SEALED_TARGET_COUNT_MISMATCH")
    initial_attempts = sum(
        row.get("attempt_kind") == "initial" for row in attempts
    )
    repair_attempts = sum(
        row.get("attempt_kind") == "schema_only_repair" for row in attempts
    )
    if (
        initial_attempts != EXPECTED_INITIAL_FACTORS
        or repair_attempts > EXPECTED_MAX_SCHEMA_ONLY_REPAIRS
        or any(
            row.get("attempt_kind") == "schema_only_repair"
            and row.get("factor_kind") == "ambient"
            for row in attempts
        )
        or len(attempts) != initial_attempts + repair_attempts
    ):
        raise AuthoringError("SEALED_ATTEMPT_BUDGET_INVALID")
    if (
        runtime.get("initial_authoring_calls") != initial_attempts
        or runtime.get("schema_only_repair_calls") != repair_attempts
        or runtime.get("authoring_model_calls") != len(attempts)
        or runtime.get("visual_initial_authoring_calls")
        != EXPECTED_VISUAL_FACTORS
        or runtime.get("ambient_initial_authoring_calls")
        != EXPECTED_AMBIENT_FACTORS
        or runtime.get("composition_initial_authoring_calls")
        != EXPECTED_COMPOSITION_FACTORS
    ):
        raise AuthoringError("SEALED_RUNTIME_BUDGET_MISMATCH")
    validate_accepted_factor_provenance(
        accepted,
        attempts,
        authored.get("queries", []),
        authored.get("descriptions", []),
        structural=structural,
        prompt_manifest=prompt_manifest,
        trusted_constraint_context=trusted_constraint_context,
    )
    expected_tuple_collisions = ambient_semantic_tuple_duplicate_audit(
        accepted,
        authored.get("queries", []),
        scope="full_authoring",
    )
    if (
        tuple_collisions != expected_tuple_collisions
        or tuple_collisions.get("status") != "PASS"
    ):
        raise AuthoringError(
            "SEALED_AMBIENT_SEMANTIC_TUPLE_COLLISION_LEDGER_INVALID"
        )
    if (
        authored.get("accepted_factor_manifest_sha256")
        != accepted.get("manifest_payload_sha256")
    ):
        raise AuthoringError("SEALED_ACCEPTED_FACTOR_BINDING_MISMATCH")
    if authored.get("prompt_manifest_sha256") != semantic_hash(
        prompt_manifest
    ):
        raise AuthoringError("SEALED_PROMPT_MANIFEST_BINDING_MISMATCH")
    transcripts = _transcripts_from_asr_inventory(asr_inventory)
    expected_digest = _audit_input_digest(
        structural,
        authored.get("queries", []),
        authored.get("descriptions", []),
        asr_inventory,
    )
    if (
        audits.get("input_digest") != expected_digest
        or authored.get("audits_input_digest") != expected_digest
    ):
        raise AuthoringError("SEALED_AUDIT_INPUT_DIGEST_MISMATCH")
    if authored.get("audits_payload_sha256") != semantic_hash(audits):
        raise AuthoringError("SEALED_AUDIT_PAYLOAD_BINDING_MISMATCH")
    with _temporary_expected_counts(
        families=len(structural["families"]),
        queries=EXPECTED_QUERY_COUNT,
    ):
        replay_queries, replay_descriptions = _queries_for_audit_replay(
            authored.get("queries", []),
            authored.get("descriptions", []),
        )
        rerun = audit_authored_content(
            structural,
            replay_queries,
            replay_descriptions,
            transcripts_by_clip=transcripts,
            embed_visual=_synthetic_embed,
            embed_ambient=_synthetic_embed,
        )
    if _model_free_audit_projection(
        rerun
    ) != _model_free_audit_projection(audits):
        raise AuthoringError("SEALED_MODEL_FREE_AUDIT_REPLAY_MISMATCH")
    return {
        "passed": True,
        "validation_level": "INTEGRITY_ONLY_NOT_EXECUTION_ATTESTED",
        "input_authorization_verified": False,
        "execution_attested": False,
        "externally_attested": False,
        "status": seal["status"],
        "query_count": authored["query_count"],
        "trusted_constraint_context_build_seconds": (
            trusted_constraint_context["context_build_seconds"]
        ),
    }


def validate_output(root: Path, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Refuse an execution-attested GO for the historical full pipeline.

    Canary2 has exact current-input authorization revalidation.  That still
    does not attest model execution.  The full pipeline remains explicitly
    integrity-only and does not even provide that current-input binding.
    """

    validate_output_integrity_only(root, output)
    raise AuthoringError(
        "OUTPUT_EXECUTION_ATTESTATION_UNAVAILABLE:"
        "USE_VALIDATE_OUTPUT_INTEGRITY_ONLY"
    )


@contextlib.contextmanager
def _temporary_expected_counts(
    *, families: int, queries: int
) -> Iterator[None]:
    global EXPECTED_FAMILIES, EXPECTED_QUERY_COUNT
    original = EXPECTED_FAMILIES, EXPECTED_QUERY_COUNT
    EXPECTED_FAMILIES, EXPECTED_QUERY_COUNT = families, queries
    try:
        yield
    finally:
        EXPECTED_FAMILIES, EXPECTED_QUERY_COUNT = original


def validate_plan(root: Path = ROOT, plan: Path = DEFAULT_PLAN) -> dict[str, Any]:
    path = _repo_path(root, plan)
    value = load_json(path)
    if value.get("pipeline_id") != PIPELINE_ID:
        raise AuthoringError("PLAN_PIPELINE_ID_MISMATCH")
    if (
        value.get("schema_version") != PLAN_SCHEMA_VERSION
        or value.get("created_date") != CURRENT_DATE
        or value.get("decision") != READY
        or value.get("scope", {}).get("old_authorization_receipts_valid")
        is not False
        or value.get("scope", {}).get("plan_status_current") is not True
    ):
        raise AuthoringError("PLAN_R21_CONTRACT_INVALID")
    observed = value.get("plan_payload_sha256")
    expected = semantic_hash(
        {k: v for k, v in value.items() if k != "plan_payload_sha256"}
    )
    if observed != expected:
        raise AuthoringError("PLAN_PAYLOAD_HASH_MISMATCH")
    if value.get("pipeline_sha256") != pipeline_tool_sha256(root):
        raise AuthoringError("PLAN_PIPELINE_HASH_STALE")
    route = value.get("authoring_route")
    if not isinstance(route, Mapping):
        raise AuthoringError("PLAN_AUTHORING_ROUTE_MISSING")
    constraint = route.get("ambient_token_constraint")
    if constraint != ambient_constraint_contract():
        raise AuthoringError("PLAN_AMBIENT_CONSTRAINT_BINDING_INVALID")
    return value


def _synthetic_structural() -> dict[str, Any]:
    families = []
    targets = []
    clip_index = 0
    for family_index in range(1, EXPECTED_FAMILIES + 1):
        count = 1 if family_index <= EXPECTED_NEAR_FAMILIES else 2
        intervals = []
        for ordinal in range(count):
            clip_index += 1
            intervals.append(
                {
                    "clip_key": f"clip-{clip_index:03d}",
                    "start_us": clip_index * 10_000_000,
                    "end_us": clip_index * 10_000_000 + 8_000_000,
                    "private_evidence_handle_ids": [
                        f"eh.synthetic.{clip_index}.v",
                        f"eh.synthetic.{clip_index}.a",
                    ],
                }
            )
            targets.append(
                {
                    "clip_key": f"clip-{clip_index:03d}",
                    "start_us": clip_index * 10_000_000,
                    "end_us": clip_index * 10_000_000 + 8_000_000,
                    "duration_us": 8_000_000,
                    "family_keys": [f"family-{family_index:03d}"],
                }
            )
        families.append(
            {
                "family_key": f"family-{family_index:03d}",
                "private_family_id": f"mpf.synthetic.{family_index}",
                "shape": (
                    "one_component"
                    if count == 1
                    else "two_component_ordered"
                ),
                "slot_names": ["OBJECT_OR_STATE", "NON_SPEECH_EVENT"],
                "private_template_hashes": {},
                "intervals": intervals,
            }
        )
    return {
        "families": families,
        "targets": targets,
        "counts": {
            "families": EXPECTED_FAMILIES,
            "handles": EXPECTED_HANDLES,
            "target_clips": EXPECTED_TARGET_CLIPS,
            "near_families": EXPECTED_NEAR_FAMILIES,
            "far_families": EXPECTED_FAR_FAMILIES,
            "queries": EXPECTED_QUERY_COUNT,
        },
    }


def _synthetic_parsed(structural: Mapping[str, Any]) -> dict[str, Any]:
    parsed = {}
    for family_index, family in enumerate(structural["families"], 1):
        components = []
        for ordinal, _interval in enumerate(family["intervals"], 1):
            object_names = (
                "ladle",
                "tray",
                "cup",
                "plate",
                "spoon",
                "bottle",
                "pan",
                "basket",
                "jar",
                "board",
                "kettle",
                "tongs",
                "utensil",
                "vessel",
                "strainer",
                "pitcher",
                "bowl",
                "mug",
                "lid",
                "container",
            )
            object_name = object_names[
                (family_index + ordinal - 2) % len(object_names)
            ]
            event_kinds = (
                "tap",
                "click",
                "scrape",
                "knock",
                "clank",
                "hiss",
                "throat_clear",
                "beep",
                "creak",
                "rustle",
            )
            semantic_index = (family_index - 1) * 2 + ordinal - 1
            ambient = _accepted_ambient_factor(
                {
                    "event_kind": event_kinds[
                        semantic_index % len(event_kinds)
                    ],
                    "acoustic_properties": {
                        "timbre": STRUCTURED_AMBIENT_TIMBRES[
                            1
                            + (
                                semantic_index
                                // len(event_kinds)
                            )
                            % (len(STRUCTURED_AMBIENT_TIMBRES) - 1)
                        ],
                        "loudness": STRUCTURED_AMBIENT_LOUDNESS[
                            1
                            + (
                                semantic_index
                                // (
                                    len(event_kinds)
                                    * (
                                        len(
                                            STRUCTURED_AMBIENT_TIMBRES
                                        )
                                        - 1
                                    )
                                )
                            )
                            % (len(STRUCTURED_AMBIENT_LOUDNESS) - 1)
                        ],
                        "temporal_pattern": (
                            STRUCTURED_AMBIENT_TEMPORAL_PATTERNS[
                                1
                                + semantic_index
                                % (
                                    len(
                                        STRUCTURED_AMBIENT_TEMPORAL_PATTERNS
                                    )
                                    - 1
                                )
                            ]
                        ),
                    },
                }
            )
            components.append(
                {
                    "ordinal": ordinal,
                    "visual_description": (
                        f"Numbered {object_name} {family_index} "
                        "moves across a wooden surface."
                    ),
                    "visual_query": (
                        f"moving numbered {object_name} {family_index} "
                        "across a wooden surface"
                    ),
                    **ambient,
                }
            )
        composition = {
            "relation_kind": (
                "local_cooccurrence"
                if len(components) == 1
                else "ordered_1_then_2"
            )
        }
        parsed[family["family_key"]] = {
            "components": components,
            **composition,
            **_mechanical_composition_texts(
                components,
                composition,
                family_shape=str(family["shape"]),
            ),
        }
    return parsed


def _synthetic_embed(texts: Sequence[str]) -> Sequence[Sequence[float]]:
    vectors = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [
            (digest[index] - 127.5) / 127.5 for index in range(16)
        ]
        vectors.append(vector)
    return vectors


def synthetic_self_test() -> dict[str, Any]:
    structured_generator = structured_ambient_generator_self_audit()
    structural = _synthetic_structural()
    manifest = build_prompt_manifest(structural)
    if manifest["prompt_count"] != EXPECTED_INITIAL_FACTORS:
        raise AuthoringError("SYNTHETIC_PROMPT_COUNT")
    serialized = canonical_bytes(manifest).decode("utf-8")
    if PRIVATE_ID_RE.search(serialized) or TIMESTAMP_RE.search(serialized):
        raise AuthoringError("SYNTHETIC_PROMPT_FIREWALL")
    queries, descriptions = materialize_query_records(
        structural, _synthetic_parsed(structural)
    )
    audits = audit_authored_content(
        structural,
        queries,
        descriptions,
        transcripts_by_clip={row["clip_key"]: "" for row in structural["targets"]},
        embed_visual=_synthetic_embed,
        embed_ambient=_synthetic_embed,
    )
    if audits["status"] != "PASS":
        raise AuthoringError(
            "SYNTHETIC_AUDIT_FAILED:" + ",".join(audits["failures"])
        )
    local_family = {
        "family_key": "synthetic-r6-local",
        "shape": "one_component",
        "intervals": [{"clip_key": "synthetic-r6-local-clip"}],
    }
    local_factor = {
        "visual_description": (
            "A person is crumpling a plastic bag on a table."
        ),
        "visual_query": "person crumpling a plastic bag on a table",
        "ambient_description": (
            "The sound of crumpling plastic is heard."
        ),
        "ambient_query": "sound of crumpling plastic",
    }
    validate_legacy_ambient_factor_output(
        {
            "ambient_description": local_factor["ambient_description"],
            "ambient_query": local_factor["ambient_query"],
        }
    )
    assemble_family_factors(
        local_family,
        [
            {
                key: local_factor[key]
                for key in VISUAL_OUTPUT_SCHEMA
            }
        ],
        [
            validate_ambient_factor_output(
                {
                    "event_kind": "crinkle",
                    "acoustic_properties": {
                        "timbre": "crisp",
                        "loudness": "soft",
                        "temporal_pattern": "repeated",
                    },
                }
            )
        ],
        {"relation_kind": "local_cooccurrence"},
    )
    invalid_r7_audio = {
        "ambient_description": "A metal pot is placed on a counter.",
        "ambient_query": "metal pot placed on a counter",
    }
    try:
        validate_legacy_ambient_factor_output(invalid_r7_audio)
    except AuthoringError as exc:
        if _error_code(exc) != (
            "MODEL_AMBIENT_SPECIFIC_ACOUSTIC_EVENT_REQUIRED"
        ):
            raise
    else:
        raise AuthoringError("SYNTHETIC_R9_ACTION_ONLY_AUDIO_NOT_CAUGHT")
    for ambiguous_visual_text in (
        "color choice impacts appearance",
        "person taps a button",
        "clicks a menu button",
        "hand scratches a label",
        "sound menu button click",
    ):
        if _specific_acoustic_terms(ambiguous_visual_text):
            raise AuthoringError(
                "SYNTHETIC_R9_AMBIGUOUS_ACTION_BYPASS_NOT_CAUGHT"
            )
    for rejected_r10_ambient in (
        "color choice impacts sound quality",
        "click sound menu button",
        "a beep sounds while a person taps a button",
        "a beep sounds while the design echoes a theme",
        "echo button",
    ):
        try:
            validate_legacy_ambient_factor_output(
                {
                    "ambient_description": rejected_r10_ambient,
                    "ambient_query": rejected_r10_ambient,
                }
            )
        except AuthoringError:
            pass
        else:
            raise AuthoringError(
                "SYNTHETIC_R10_MIXED_AMBIGUOUS_BYPASS_NOT_CAUGHT"
            )
    for valid_acoustic_text in (
        "a sharp tap is heard",
        "metallic clicking sounds",
        "scraping noise",
        "a knock echoes",
        "a brief clank",
        "a low hiss",
        "throat clearing",
    ):
        if not _specific_acoustic_terms(valid_acoustic_text):
            raise AuthoringError(
                "SYNTHETIC_R9_VALID_ACOUSTIC_EVENT_REJECTED"
            )
    validate_legacy_ambient_factor_output(
        {
            "ambient_description": (
                "A sharp metallic clank is followed by a brief scrape."
            ),
            "ambient_query": "sharp metallic clank with a brief scrape",
        }
    )
    for valid_r10_description, valid_r10_query in (
        ("scraping noise", "which scraping noise is audible"),
        ("throat clearing", "which throat clearing is audible"),
        ("sound of a button click", "which button click is heard"),
        ("audible clicking", "which clicking is audible"),
        ("a knock echoes", "which knock echoes"),
        ("an echo is heard", "which echo is heard"),
        ("single beep", "which single beep is audible"),
        ("ready beep", "which ready beep is audible"),
        ("a bell rings audibly", "which bell rings audibly"),
    ):
        validate_legacy_ambient_factor_output(
            {
                "ambient_description": valid_r10_description,
                "ambient_query": valid_r10_query,
            }
        )
    for accepted_r15_visual_query in (
        "Which metal bowl is a hand lifting from the counter?",
        "Which metal bowl is being lifted from the counter?",
        "metal bowl lifting from the counter",
    ):
        validate_visual_factor_output(
            {
                "visual_description": (
                    "A hand lifts a metal bowl from a counter."
                ),
                "visual_query": accepted_r15_visual_query,
            }
        )
    validate_visual_factor_output(
        {
            "visual_description": (
                "A hand lifts a nearby metal bowl from a counter."
            ),
            "visual_query": (
                "Which nearby metal bowl is a hand lifting from the counter?"
            ),
        }
    )
    for rejected_r15_visual_pair in (
        (
            "A hand lifts a metal bowl from a counter.",
            "Which metal bowl is lifted by the hand from the counter?",
        ),
        (
            "A hand lifts a metal bowl from a counter.",
            "Which metal bowl is lifted by a worker from the counter?",
        ),
        (
            "A hand lifts a metal bowl from a counter.",
            (
                "Which metal bowl is dropped then lifted by the hand "
                "from the counter?"
            ),
        ),
        (
            "A worker and a sealed box stand nearby.",
            "Which sealed box is sealed by the worker?",
        ),
        (
            "A covered bowl sits while a hand rests nearby.",
            "Which covered bowl is covered by the hand?",
        ),
        (
            "A red bowl sits while a hand rests nearby.",
            "Which red bowl is red by the hand?",
        ),
    ):
        try:
            validate_visual_factor_output(
                {
                    "visual_description": rejected_r15_visual_pair[0],
                    "visual_query": rejected_r15_visual_pair[1],
                }
            )
        except AuthoringError as exc:
            if _error_code(exc) != "MODEL_VISUAL_QUERY_SEMANTIC_ADDITION":
                raise
        else:
            raise AuthoringError(
                "SYNTHETIC_R15_VISUAL_BY_FAIL_CLOSED_BYPASS_NOT_CAUGHT"
            )
    for rejected_r13_ambient in (
        "A bell rings near a label that is audibly scratched.",
        "A bell rings while a person audibly taps a button.",
        "A bell rings in a room with the sound of a button click.",
    ):
        try:
            validate_legacy_ambient_factor_output(
                {
                    "ambient_description": rejected_r13_ambient,
                    "ambient_query": "which bell rings audibly",
                }
            )
        except AuthoringError as exc:
            if _error_code(exc) != (
                "MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID"
            ):
                raise
        else:
            raise AuthoringError(
                "SYNTHETIC_R13_DISTANT_AUDITORY_BINDING_NOT_CAUGHT"
            )
    for rejected_r10_speech in (
        "a beep sounds while a person asks a question",
        "a beep sounds while a person answers",
        "a beep sounds during questioning",
    ):
        try:
            validate_legacy_ambient_factor_output(
                {
                    "ambient_description": rejected_r10_speech,
                    "ambient_query": (
                        f"which {rejected_r10_speech} is audible"
                    ),
                }
            )
        except AuthoringError as exc:
            if _error_code(exc) != "MODEL_AMBIENT_LEXICAL_SPEECH_FORBIDDEN":
                raise
        else:
            raise AuthoringError(
                "SYNTHETIC_R10_LEXICAL_SPEECH_NOT_CAUGHT"
            )
    try:
        validate_legacy_ambient_factor_output(
            {
                "ambient_description": "sound quiet",
                "ambient_query": "which quiet sound is audible",
            }
        )
    except AuthoringError as exc:
        if _error_code(exc) != (
            "MODEL_AMBIENT_SPECIFIC_ACOUSTIC_EVENT_REQUIRED"
        ):
            raise
    else:
        raise AuthoringError("SYNTHETIC_R10_GENERIC_SOUND_NOT_CAUGHT")
    r7_ambient = (
        "A person clears their throat and then places a pot lid on the counter."
    )
    r7_local = _component_local_continuity_evidence(r7_ambient)
    if r7_local["unsupported"] or _acoustic_concepts(r7_ambient) != {
        "throat-clearing"
    }:
        raise AuthoringError("SYNTHETIC_R7_LOCAL_THROAT_CLEARING_FAILED")
    for rejected_r7_text in (
        "Their throat clearing is audible.",
        "The same person clears their throat again.",
    ):
        if not _component_local_continuity_evidence(rejected_r7_text)[
            "unsupported"
        ]:
            raise AuthoringError(
                "SYNTHETIC_R7_LOCAL_POSSESSIVE_BRIDGE_NOT_CAUGHT"
            )
    if not _unsupported_continuity_evidence(
        (
            "A person clears their throat, then their hand places a pot lid "
            "on the counter."
        ),
        reject_agent_terms=False,
        reject_reused_entities=False,
    )["unsupported"]:
        raise AuthoringError("SYNTHETIC_R7_CROSS_COMPONENT_BRIDGE_NOT_CAUGHT")
    if _human_vocalization_policy(
        "A person clears their throat and speaks several words."
    )["clearly_nonlexical_non_speech"]:
        raise AuthoringError("SYNTHETIC_R7_LEXICAL_SPEECH_NOT_CAUGHT")
    for rejected_local_text in (
        "The same person continues crumpling plastic.",
        "A person crumples the plastic bag again.",
        "The bag moves because the person crumples it.",
    ):
        if not _component_local_continuity_evidence(
            rejected_local_text
        )["unsupported"]:
            raise AuthoringError("SYNTHETIC_R6_LOCAL_BRIDGE_NOT_CAUGHT")
    if not _unsupported_continuity_evidence(
        (
            "The same person slices vegetables with chopping impacts, then "
            "transfers them into a pot with a metallic clank."
        ),
        reject_agent_terms=False,
        reject_reused_entities=False,
    )["unsupported"]:
        raise AuthoringError("SYNTHETIC_R6_CROSS_COMPONENT_BRIDGE_NOT_CAUGHT")
    bad = [dict(row) for row in queries]
    bad[1]["query_text"] = bad[0]["query_text"]
    if not lexical_collision_findings(bad):
        raise AuthoringError("SYNTHETIC_DUPLICATE_NOT_CAUGHT")
    leakage = literal_leakage_findings(
        [
            {
                "key": "bad",
                "family_key": "family-001",
                "clip_key": "clip-001",
                "text": (
                    "P23_102 visual clip at 00:12 says turn on the water now"
                ),
            }
        ],
        transcripts_by_clip={"clip-001": "please turn on the water now"},
        slot_names_by_family={"family-001": ["OBJECT_OR_STATE"]},
    )
    kinds = {row["kind"] for row in leakage}
    if not {"source_name", "timestamp", "modality_label", "copied_asr_ngram"} <= kinds:
        raise AuthoringError("SYNTHETIC_LITERAL_LEAK_NOT_CAUGHT")
    baseline = explicit_template_baseline(structural)
    if any(
        row["eligible_for_primary_query_set"]
        for row in baseline["rows"]
    ):
        raise AuthoringError("SYNTHETIC_BASELINE_NOT_EXCLUDED")
    return {
        "passed": True,
        "status": READY,
        "repair_status": SEMANTIC_GATES_READY,
        "constrained_json_status": CONSTRAINED_JSON_READY,
        "factorized_status": FACTORIZED_V2_READY,
        "counts": structural["counts"],
        "model_calls": 0,
        "media_decodes": 0,
        "network_requests": 0,
        "structured_ambient_generator": structured_generator,
    }


def plan_status(root: Path) -> dict[str, Any]:
    plan = validate_plan(root)
    current_pipeline_sha256 = pipeline_tool_sha256(root)
    current = plan.get("pipeline_sha256") == current_pipeline_sha256
    structural = load_structural_bundle(root)
    return {
        "status": READY,
        "repair_status": SEMANTIC_GATES_READY,
        "constrained_json_status": CONSTRAINED_JSON_READY,
        "factorized_status": FACTORIZED_V2_READY,
        "plan_payload_sha256": plan["plan_payload_sha256"],
        "current": current,
        "plan_pipeline_hash_current": current,
        "current_pipeline_sha256": current_pipeline_sha256,
        "old_authorization_receipts_valid": False,
        "ambient_registry_sha256": STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "ambient_generator_sha256": AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": AMBIENT_TEMPLATE_SHA256,
        "ambient_constraint_kind": AMBIENT_CONSTRAINT_KIND,
        "ambient_constraint_manifest_sha256": (
            AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "ambient_constraint_leaf_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_constraint_reachable_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "structured_ambient_combination_count": (
            EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "structured_ambient_unique_pair_count": (
            EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS
        ),
        "ambient_derived_text_model_calls": 0,
        "counts": structural["counts"],
        "execution_performed": False,
        "authorization_receipt_created": False,
        "model_calls": 0,
        "media_decodes": 0,
        "scoring_executed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--validate-output", action="store_true")
    modes.add_argument("--synthetic-self-test", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--media", type=Path, default=DEFAULT_MEDIA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--emit-explicit-template-baseline", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.synthetic_self_test:
            result = synthetic_self_test()
        elif args.plan:
            result = plan_status(root)
        elif args.preflight:
            result = preflight(root, bundle=args.bundle, media=args.media)
            if result["status"] != "READY":
                print(json.dumps(result, indent=2, sort_keys=True))
                return 2
        elif args.execute:
            if args.authorization is None:
                raise AuthoringError(
                    "EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION_RECEIPT"
                )
            result = execute(
                root,
                bundle=args.bundle,
                media=args.media,
                output=args.output,
                authorization=args.authorization,
                emit_explicit_baseline=(
                    args.emit_explicit_template_baseline
                ),
            )
        else:
            result = validate_output(root, args.output)
    except AuthoringError as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "error": str(exc),
                    "model_calls_substituted": False,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
