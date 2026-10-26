"""Build the frozen, fail-closed source exposure alias manifest v2.

The builder reads repository text evidence only.  It never opens media and it
excludes semantic annotation bodies, transcript/caption bodies, model payloads,
and generated observation bodies.  The first successful build freezes the
eligible text-file path/hash inventory.  Later builds use that committed
inventory exclusively and report newly discovered eligible files as a
supplemental post-freeze audit; such files cannot redefine v2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.source-exposure-alias-manifest/2.0"
MANIFEST_ID = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2"
FINAL_READY = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_READY"
CREATED_DATE = "2026-10-14"

OUTPUT_REL = Path("data/rehearsal_plan/source_exposure_alias_manifest_v2.json")
REVIEW_REL = Path("docs/review/source_exposure_alias_manifest_v2.md")
LEDGER_V2_REL = Path("data/rehearsal_plan/untouched_test_group_ledger_v2.json")

SCAN_ROOTS = ("data", "docs", "orchestration", "mvp")
ALLOWLISTED_EXTENSIONS = {
    ".csv",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".prompt",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_FILE_BYTES = 4_000_000
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    "__pycache__",
    "annotation",
    "annotations",
    "checkpoints",
    "families",
    "media",
    "models",
    "node_modules",
    "snapshots",
    "trajectories",
}
SEMANTIC_BODY_NAME_TOKENS = {
    "caption",
    "full_timeline_index",
    "learned_index",
    "narration",
    "provisional_audio_facts",
    "rankings.json",
    "transcript",
    "window_index",
}
SELF_OUTPUTS = {OUTPUT_REL.as_posix(), REVIEW_REL.as_posix()}

EVENT_ORDER = (
    "frozen_primary_pool",
    "candidate_pool_member",
    "candidate_route",
    "candidate_selection_rank",
    "selection_rationale",
    "semantic_routing_target",
    "semantic_prompt",
    "semantic_dossier_description",
    "transcript_or_page_content_observation",
    "candidate_queue_review_or_mining",
    "learned_ranking",
    "media_acquired",
    "media_indexed",
)
CONTAMINATING_EVENTS = set(EVENT_ORDER)

EPIC_VIDEO_RE = re.compile(r"\bP(?P<participant>\d{2})_(?P<session>\d{2,3})\b")
EPIC_PARTICIPANT_RE = re.compile(r"\bP(?P<participant>\d{2})\b")
CC4D_RECORDING_RE = re.compile(r"(?<!\d)(?P<recording>\d{1,2}_\d{1,3})(?!\d)")
CC4D_GROUP_RE = re.compile(
    r"\bcc4d_p(?P<person>\d{2})_e(?P<environment>\d{2})\b",
    re.IGNORECASE,
)
ASSEMBLY_GROUP_RE = re.compile(r"\bassembly101_p(?P<participant>\d{4})\b", re.I)
ASSEMBLY_SESSION_RE = re.compile(
    r"\bnusar-[A-Za-z0-9_-]*_(?P<participant>9\d{3})(?:[-_][A-Za-z0-9_-]+)?\b",
    re.I,
)
CANDIDATE_RE = re.compile(r"\bcand-\d{3}\b", re.I)
EC_RE = re.compile(r"\bEC-[A-Z0-9][A-Z0-9-]*\b")
NAID_RE = re.compile(r"\bNAID[: -]?(?P<id>\d+)\b", re.I)
NASA_POST_RE = re.compile(r"\bNASA\+\s*post\s*(?P<id>\d+)\b", re.I)
NASA_CONTENT_RE = re.compile(r"\bcontent[-_ ]?id\s*(?P<id>\d+)\b", re.I)
NASA_ASSET_RE = re.compile(r"\bHLS\s+asset\s*(?P<id>\d+)\b", re.I)
LECTURE_GROUP_RE = re.compile(r"\bSG-(?:MIT|YALE|OXFORD)-[A-Z0-9-]+\b", re.I)
LECTURE_REPLACEMENT_RE = re.compile(
    r"\brepl-(?:mit|yale|oxford)-[a-z0-9-]+\b", re.I
)


class ManifestError(ValueError):
    """Raised when v2 cannot be built or verified fail-closed."""


@dataclass(frozen=True)
class Evidence:
    path: str
    locator: str
    sha256: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "detail": self.detail,
            "locator": self.locator,
            "path": self.path,
            "sha256": self.sha256,
        }


class AliasGraph:
    def __init__(self) -> None:
        self.parents: dict[str, str] = {}
        self.edge_evidence: dict[tuple[str, str], set[Evidence]] = defaultdict(set)
        self.edge_kinds: dict[tuple[str, str], set[str]] = defaultdict(set)

    def add(self, alias: str) -> None:
        alias = normalize_alias(alias)
        if alias and alias not in self.parents:
            self.parents[alias] = alias

    def find(self, alias: str) -> str:
        alias = normalize_alias(alias)
        self.add(alias)
        parent = self.parents[alias]
        if parent != alias:
            self.parents[alias] = self.find(parent)
        return self.parents[alias]

    def union(
        self,
        left: str,
        right: str,
        *,
        kind: str,
        evidence: Evidence,
    ) -> None:
        left = normalize_alias(left)
        right = normalize_alias(right)
        if not left or not right:
            return
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            root, child = sorted((left_root, right_root))
            self.parents[child] = root
        edge = tuple(sorted((left, right)))
        self.edge_evidence[edge].add(evidence)
        self.edge_kinds[edge].add(kind)

    def components(self) -> list[dict[str, Any]]:
        by_parent: dict[str, set[str]] = defaultdict(set)
        for alias in self.parents:
            by_parent[self.find(alias)].add(alias)
        rows = []
        for aliases in by_parent.values():
            root = choose_closure_root(aliases)
            edges = []
            for edge in sorted(self.edge_evidence):
                if edge[0] in aliases and edge[1] in aliases:
                    edges.append(
                        {
                            "aliases": list(edge),
                            "evidence": [
                                item.as_dict()
                                for item in sorted(
                                    self.edge_evidence[edge], key=evidence_key
                                )
                            ],
                            "kinds": sorted(self.edge_kinds[edge]),
                        }
                    )
            rows.append(
                {
                    "aliases": sorted(aliases),
                    "closure_root": root,
                    "supporting_edges": edges,
                }
            )
        return sorted(rows, key=lambda row: row["closure_root"])


def evidence_key(value: Evidence) -> tuple[str, str, str, str]:
    return (value.path, value.locator, value.detail, value.sha256)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_alias(value: str) -> str:
    value = str(value).strip().strip("`'\"")
    if CANDIDATE_RE.fullmatch(value) or LECTURE_REPLACEMENT_RE.fullmatch(value):
        return value.lower()
    if EC_RE.fullmatch(value) or LECTURE_GROUP_RE.fullmatch(value):
        return value.upper()
    match = NAID_RE.fullmatch(value)
    if match:
        return f"NAID:{match.group('id')}"
    return value


def choose_closure_root(aliases: Iterable[str]) -> str:
    values = sorted(set(aliases))
    priorities = (
        r"^EPIC:P\d{2}$",
        r"^CC4D:P\d{2}$",
        r"^ASSEMBLY101:\d{4}$",
        r"^EC-",
        r"^SG-(?!CAND-)",
        r"^SG-",
        r"^NOAA:",
        r"^NARA:",
        r"^NASA:",
    )
    for pattern in priorities:
        matches = [value for value in values if re.search(pattern, value)]
        if matches:
            return matches[0]
    return values[0]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(read_text(path))
    if not isinstance(value, dict):
        raise ManifestError(f"JSON_OBJECT_REQUIRED:{path.as_posix()}")
    return value


def json_pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def walk_json(value: Any, pointer: str = "") -> Iterator[tuple[str, Any]]:
    yield pointer or "/", value
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{json_pointer_escape(str(key))}"
            yield from walk_json(child, child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, f"{pointer}/{index}")


def semantic_body_reason(relative: Path) -> str | None:
    lower_name = relative.name.lower()
    if relative.suffix.lower() == ".body":
        return "semantic_body_extension"
    if any(token in lower_name for token in SEMANTIC_BODY_NAME_TOKENS):
        return "semantic_body_name"
    return None


def discover_inventory(root: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            relative_text = relative.as_posix()
            if relative_text in SELF_OUTPUTS:
                skipped["self_output"] += 1
                continue
            if set(relative.parts) & EXCLUDED_DIRECTORY_NAMES:
                skipped["excluded_directory"] += 1
                continue
            body_reason = semantic_body_reason(relative)
            if body_reason:
                skipped[body_reason] += 1
                continue
            if path.suffix.lower() not in ALLOWLISTED_EXTENSIONS:
                skipped["extension_not_allowlisted"] += 1
                continue
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                skipped["over_size_limit"] += 1
                continue
            rows.append(
                {
                    "bytes": size,
                    "path": relative_text,
                    "sha256": sha256_file(path),
                }
            )
    rows.sort(key=lambda row: row["path"])
    return rows, dict(sorted(skipped.items()))


def frozen_inventory(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    committed_path = root / OUTPUT_REL
    discovered, skipped = discover_inventory(root)
    if not committed_path.is_file():
        return discovered, [], skipped
    committed = load_json(committed_path)
    freeze = committed.get("scan_freeze", {})
    pinned = freeze.get("pinned_files")
    if not isinstance(pinned, list) or not pinned:
        raise ManifestError("COMMITTED_PINNED_INVENTORY_MISSING")
    pinned = sorted(pinned, key=lambda row: row["path"])
    current_by_path = {row["path"]: row for row in discovered}
    for row in pinned:
        current = current_by_path.get(row["path"])
        if current is None:
            raise ManifestError(f"PINNED_FILE_MISSING:{row['path']}")
        if current != row:
            raise ManifestError(f"PINNED_FILE_HASH_MISMATCH:{row['path']}")
    pinned_paths = {row["path"] for row in pinned}
    supplemental = [
        row for row in discovered if row["path"] not in pinned_paths
    ]
    frozen_skipped = freeze.get("skipped_by_reason")
    if isinstance(frozen_skipped, dict):
        skipped = frozen_skipped
    return pinned, supplemental, skipped


def evidence_for(
    root: Path, relative: str, locator: str, detail: str
) -> Evidence:
    path = root / relative
    return Evidence(
        path=relative,
        locator=locator,
        sha256=sha256_file(path),
        detail=detail,
    )


def add_edge(
    graph: AliasGraph,
    root: Path,
    relative: str,
    left: str,
    right: str,
    *,
    kind: str,
    locator: str,
    detail: str,
) -> None:
    graph.union(
        left,
        right,
        kind=kind,
        evidence=evidence_for(root, relative, locator, detail),
    )


def canonical_lecture_group(candidate_row: dict[str, Any]) -> str | None:
    source_group = str(candidate_row.get("candidate_source_group_id", ""))
    if source_group.startswith("SG-CAND-"):
        return "SG-" + source_group.removeprefix("SG-CAND-")
    candidate = str(candidate_row.get("candidate_id", ""))
    if not LECTURE_REPLACEMENT_RE.fullmatch(candidate):
        return None
    body = candidate.removeprefix("repl-").upper()
    body = re.sub(r"-LECTURE-(\d+)$", lambda m: f"-L{int(m.group(1)):02d}", body)
    body = body.replace("PHYS-200", "PHYS200").replace("HIST-202", "HIST202")
    return f"SG-{body}"


def extract_alias_graph(
    root: Path, pinned_paths: set[str]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    graph = AliasGraph()

    epic_rel = (
        "data/source_recon/assembly_epic_access_v2/metadata/epic/"
        "EPIC_100_video_info.csv"
    )
    if epic_rel in pinned_paths:
        with (root / epic_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                video = row.get("video_id", "")
                match = EPIC_VIDEO_RE.fullmatch(video)
                if not match:
                    continue
                participant = f"P{match.group('participant')}"
                closure = f"EPIC:{participant}"
                add_edge(
                    graph,
                    root,
                    epic_rel,
                    closure,
                    participant,
                    kind="official_epic_participant",
                    locator=f"line:{line_number}",
                    detail=f"official participant row for {video}",
                )
                add_edge(
                    graph,
                    root,
                    epic_rel,
                    closure,
                    video,
                    kind="official_epic_participant_video",
                    locator=f"line:{line_number}",
                    detail="official participant/video membership",
                )

    cc_rel = "data/source_recon/captaincook4d_access_v1/video_information.csv"
    if cc_rel in pinned_paths:
        with (root / cc_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                recording = row.get("recording_id", "")
                if not recording:
                    continue
                person = int(row["person_id"])
                environment = int(row["environment_id"])
                closure = f"CC4D:P{person:02d}"
                group = f"cc4d_p{person:02d}_e{environment:02d}"
                for alias, kind in (
                    (group, "official_cc4d_person_environment"),
                    (recording, "official_cc4d_person_recording"),
                ):
                    add_edge(
                        graph,
                        root,
                        cc_rel,
                        closure,
                        alias,
                        kind=kind,
                        locator=f"line:{line_number}",
                        detail=(
                            f"official person {person}, environment "
                            f"{environment}, recording {recording}"
                        ),
                    )

    assembly_rel = (
        "data/source_recon/assembly_epic_access_v2/derived/"
        "assembly_sessions.csv"
    )
    if assembly_rel in pinned_paths:
        with (root / assembly_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                participant = row.get("participant_id", "")
                session = row.get("session_id", "")
                if not participant or not session:
                    continue
                closure = f"ASSEMBLY101:{participant}"
                add_edge(
                    graph,
                    root,
                    assembly_rel,
                    closure,
                    f"assembly101_p{participant}",
                    kind="official_assembly_participant",
                    locator=f"line:{line_number}",
                    detail="official participant membership",
                )
                add_edge(
                    graph,
                    root,
                    assembly_rel,
                    closure,
                    session,
                    kind="official_assembly_participant_session",
                    locator=f"line:{line_number}",
                    detail="official participant/session membership",
                )

    candidate_rel = "data/candidates/source_candidates.csv"
    if candidate_rel in pinned_paths:
        with (root / candidate_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                candidate = row.get("candidate_id", "")
                stable = row.get("stable_source_id", "")
                family = row.get("source_family", "")
                if not candidate or not stable:
                    continue
                if family == "NARA":
                    add_edge(
                        graph,
                        root,
                        candidate_rel,
                        candidate,
                        stable,
                        kind="official_candidate_catalog_alias",
                        locator=f"line:{line_number}",
                        detail=row.get("title", "NARA candidate"),
                    )
                elif family in {"NASA", "NOAA"}:
                    add_edge(
                        graph,
                        root,
                        candidate_rel,
                        f"{family}:{candidate.lower()}",
                        candidate,
                        kind="official_candidate_catalog_alias",
                        locator=f"line:{line_number}",
                        detail=row.get("title", f"{family} candidate"),
                    )
                    add_edge(
                        graph,
                        root,
                        candidate_rel,
                        f"{family}:{candidate.lower()}",
                        stable,
                        kind="official_candidate_catalog_alias",
                        locator=f"line:{line_number}",
                        detail="stable source identifier",
                    )

    nara_rel = "data/rehearsal_plan/nara_event_source_dossiers_v1.json"
    if nara_rel in pinned_paths:
        document = load_json(root / nara_rel)
        for index, row in enumerate(document.get("sources", [])):
            group = row.get("source_group_id")
            for field in ("candidate_id", "catalog_id"):
                alias = row.get(field)
                if group and alias:
                    add_edge(
                        graph,
                        root,
                        nara_rel,
                        group,
                        alias,
                        kind="nara_production_alias",
                        locator=f"/sources/{index}/{field}",
                        detail=row.get("title", "NARA production"),
                    )

    event_rel = "data/rehearsal_plan/event_centric_source_dossiers_v1.json"
    if event_rel in pinned_paths:
        document = load_json(root / event_rel)
        for index, row in enumerate(document.get("candidates", [])):
            group = row.get("source_group_id")
            canonical = row.get("canonical_id")
            if group and canonical:
                add_edge(
                    graph,
                    root,
                    event_rel,
                    group,
                    canonical,
                    kind="production_alias",
                    locator=f"/candidates/{index}/canonical_id",
                    detail=row.get("title", "event production"),
                )

    lecture_rel = "data/rehearsal_plan/mini_pilot_replacement_candidates.json"
    if lecture_rel in pinned_paths:
        document = load_json(root / lecture_rel)
        for index, row in enumerate(document.get("candidates", [])):
            group = canonical_lecture_group(row)
            candidate = row.get("candidate_id")
            if not group or not candidate:
                continue
            for field, kind in (
                ("candidate_id", "lecture_candidate_alias"),
                ("candidate_source_group_id", "lecture_candidate_alias"),
                ("course_or_series", "lecture_course_alias"),
                ("title", "lecture_title_alias"),
            ):
                alias = row.get(field)
                if alias:
                    add_edge(
                        graph,
                        root,
                        lecture_rel,
                        group,
                        alias,
                        kind=kind,
                        locator=f"/candidates/{index}/{field}",
                        detail=f"lecture {field} alias",
                    )

    for relative, container in (
        (LEDGER_V2_REL.as_posix(), "test_groups"),
        ("data/rehearsal_plan/source_disjoint_scaleup_wave_v1.json", None),
    ):
        if relative not in pinned_paths:
            continue
        document = load_json(root / relative)
        collections: list[tuple[str, list[Any]]] = []
        if container:
            collections.append((f"/{container}", document.get(container, [])))
        else:
            for split_name, rows in document.get("split_pools", {}).items():
                collections.append((f"/split_pools/{split_name}", rows))
            for pool_name, pool in document.get("reserve_pools", {}).items():
                collections.append(
                    (
                        f"/reserve_pools/{pool_name}/same_split_replacements",
                        pool.get("same_split_replacements", []),
                    )
                )
        for base_pointer, rows in collections:
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                closure = row.get("closure_root") or row.get("participant_block_id")
                if not closure:
                    continue
                for field in (
                    "source_group_id",
                    "exact_object_or_session_id",
                    "participant_block_id",
                    "production_lineage_id",
                ):
                    alias = row.get(field)
                    if alias:
                        add_edge(
                            graph,
                            root,
                            relative,
                            closure,
                            alias,
                            kind="frozen_participant_or_production_closure",
                            locator=f"{base_pointer}/{index}/{field}",
                            detail="frozen participant/person/production membership",
                        )

    components = graph.components()
    lookup = {
        alias: row["closure_root"]
        for row in components
        for alias in row["aliases"]
    }
    return components, lookup


def aliases_in_value(value: Any, lookup: dict[str, str]) -> set[str]:
    aliases: set[str] = set()
    if isinstance(value, (int, float, bool)) or value is None:
        return aliases
    text = str(value)
    whole = normalize_alias(text)
    if whole in lookup:
        aliases.add(whole)
    for match in EPIC_VIDEO_RE.finditer(text):
        aliases.update(
            {
                match.group(),
                f"P{match.group('participant')}",
                f"EPIC:P{match.group('participant')}",
            }
        )
    aliases.update(normalize_alias(x) for x in CANDIDATE_RE.findall(text))
    aliases.update(normalize_alias(x) for x in EC_RE.findall(text))
    aliases.update(normalize_alias(x) for x in LECTURE_GROUP_RE.findall(text))
    aliases.update(
        normalize_alias(x) for x in LECTURE_REPLACEMENT_RE.findall(text)
    )
    aliases.update(f"NAID:{m.group('id')}" for m in NAID_RE.finditer(text))
    for match in CC4D_GROUP_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"CC4D:P{int(match.group('person')):02d}")
    for match in ASSEMBLY_GROUP_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"ASSEMBLY101:{match.group('participant')}")
    for match in ASSEMBLY_SESSION_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"ASSEMBLY101:{match.group('participant')}")
    for regex, prefix in (
        (NASA_POST_RE, "NASA:POST:"),
        (NASA_CONTENT_RE, "NASA:CONTENT:"),
        (NASA_ASSET_RE, "NASA:ASSET:"),
    ):
        aliases.update(f"{prefix}{m.group('id')}" for m in regex.finditer(text))
    for match in CC4D_RECORDING_RE.finditer(text):
        candidate = match.group("recording")
        if candidate in lookup:
            aliases.add(candidate)
    return {alias for alias in aliases if alias in lookup}


def event_row(
    *,
    closure_root: str,
    event_type: str,
    evidence: Evidence,
    seed_aliases: Iterable[str],
    propagation: str,
) -> dict[str, Any]:
    return {
        "closure_root": closure_root,
        "eligibility_effect": "CONTAMINATED",
        "event_type": event_type,
        "evidence": evidence.as_dict(),
        "seed_aliases": sorted(set(seed_aliases)),
        "propagation": propagation,
    }


def add_events_for_aliases(
    events: dict[tuple[str, str, str, str, str], dict[str, Any]],
    *,
    aliases: Iterable[str],
    lookup: dict[str, str],
    event_type: str,
    evidence: Evidence,
    propagation: str = "FULL_ALIAS_CLOSURE",
) -> None:
    by_root: dict[str, set[str]] = defaultdict(set)
    for alias in aliases:
        normalized = normalize_alias(alias)
        closure = lookup.get(normalized)
        if closure:
            by_root[closure].add(normalized)
    for closure, seed_aliases in by_root.items():
        key = (
            closure,
            event_type,
            evidence.path,
            evidence.locator,
            evidence.detail,
        )
        events[key] = event_row(
            closure_root=closure,
            event_type=event_type,
            evidence=evidence,
            seed_aliases=seed_aliases,
            propagation=propagation,
        )


def structured_exposure_events(
    root: Path,
    pinned_paths: set[str],
    lookup: dict[str, str],
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    events: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}

    def add_rows(
        relative: str,
        rows: list[Any],
        base_pointer: str,
        event_type: str,
        detail: str,
        locator_field: str | None = None,
    ) -> None:
        if relative not in pinned_paths:
            return
        for index, row in enumerate(rows):
            aliases: set[str] = set()
            for _, value in walk_json(row):
                if not isinstance(value, (dict, list)):
                    aliases.update(aliases_in_value(value, lookup))
            if aliases:
                locator = f"{base_pointer}/{index}"
                if locator_field:
                    locator = f"{locator}/{locator_field}"
                add_events_for_aliases(
                    events,
                    aliases=aliases,
                    lookup=lookup,
                    event_type=event_type,
                    evidence=evidence_for(
                        root,
                        relative,
                        locator,
                        detail,
                    ),
                )

    ledger_rel = LEDGER_V2_REL.as_posix()
    if ledger_rel in pinned_paths:
        document = load_json(root / ledger_rel)
        add_rows(
            ledger_rel,
            document.get("test_groups", []),
            "/test_groups",
            "frozen_primary_pool",
            "v2 ledger frozen test-group member",
        )

    scale_rel = "data/rehearsal_plan/source_disjoint_scaleup_wave_v1.json"
    if scale_rel in pinned_paths:
        document = load_json(root / scale_rel)
        for split, rows in document.get("split_pools", {}).items():
            add_rows(
                scale_rel,
                rows,
                f"/split_pools/{split}",
                "frozen_primary_pool",
                f"frozen {split} primary pool member",
            )
        for pool_name, pool in document.get("reserve_pools", {}).items():
            add_rows(
                scale_rel,
                pool.get("same_split_replacements", []),
                f"/reserve_pools/{pool_name}/same_split_replacements",
                "candidate_pool_member",
                f"named same-split reserve in {pool_name}",
            )

    assembly_rel = "data/rehearsal_plan/assembly101_authenticated_registry_v1.json"
    assembly_selected: list[dict[str, Any]] = []
    if assembly_rel in pinned_paths:
        document = load_json(root / assembly_rel)
        assembly_selected = document.get("deterministic_selection", {}).get(
            "selected_groups", []
        )
        add_rows(
            assembly_rel,
            assembly_selected,
            "/deterministic_selection/selected_groups",
            "frozen_primary_pool",
            "Assembly101 deterministic primary/replacement pool member",
        )

    epic_rel = "data/rehearsal_plan/assembly_epic_access_registry_v2.json"
    if epic_rel in pinned_paths:
        document = load_json(root / epic_rel)
        add_rows(
            epic_rel,
            document.get("epic", {})
            .get("provisional_candidate_pool", {})
            .get("candidates", []),
            "/epic/provisional_candidate_pool/candidates",
            "candidate_pool_member",
            "EPIC provisional candidate/replacement pool member",
        )

    cc_rel = "data/rehearsal_plan/captaincook4d_access_registry_v1.json"
    if cc_rel in pinned_paths:
        document = load_json(root / cc_rel)
        pool = document.get("candidate_pool", {})
        for role in ("primary", "replacement"):
            add_rows(
                cc_rel,
                pool.get(role, []),
                f"/candidate_pool/{role}",
                "candidate_pool_member",
                f"CaptainCook4D frozen {role} person/environment pool member",
            )

    prospect_rel = "data/rehearsal_plan/pilot_v5_targeted_source_prospecting.json"
    if prospect_rel in pinned_paths:
        document = load_json(root / prospect_rel)
        routes = document.get("candidate_routes", [])
        add_rows(
            prospect_rel,
            routes,
            "/candidate_routes",
            "candidate_route",
            "ranked pilot-v5 candidate route or routed pool",
            "source_ids_or_pool",
        )
        for index, row in enumerate(routes):
            pool_values = row.get("source_ids_or_pool", [])
            if not isinstance(pool_values, list):
                continue
            joined = " ".join(map(str, pool_values)).lower()
            if "frozen primary participant-blocked sessions" in joined:
                aliases: set[str] = set()
                for selected in assembly_selected:
                    for _, value in walk_json(selected):
                        if not isinstance(value, (dict, list)):
                            aliases.update(aliases_in_value(value, lookup))
                add_events_for_aliases(
                    events,
                    aliases=aliases,
                    lookup=lookup,
                    event_type="candidate_route",
                    evidence=evidence_for(
                        root,
                        prospect_rel,
                        f"/candidate_routes/{index}/source_ids_or_pool",
                        "resolved symbolic Assembly101 frozen primary/replacement pool",
                    ),
                    propagation="RESOLVED_NAMED_POOL_THEN_FULL_ALIAS_CLOSURE",
                )

    route_rel = "data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json"
    if route_rel in pinned_paths:
        document = load_json(root / route_rel)
        add_rows(
            route_rel,
            document.get("routes", []),
            "/routes",
            "candidate_route",
            "ranked primary/secondary/reserve acquisition route",
            "exact_ids_or_pool",
        )

    lecture_rel = "data/rehearsal_plan/mini_pilot_replacement_candidates.json"
    if lecture_rel in pinned_paths:
        document = load_json(root / lecture_rel)
        rows = document.get("candidates", [])
        for index, row in enumerate(rows):
            aliases: set[str] = set()
            for field in (
                "candidate_id",
                "candidate_source_group_id",
                "course_or_series",
                "title",
            ):
                aliases.update(aliases_in_value(row.get(field), lookup))
            for event_type, field, detail in (
                (
                    "candidate_selection_rank",
                    "rank",
                    "ranked replacement candidate",
                ),
                (
                    "selection_rationale",
                    "ranking_rationale",
                    "semantic ranking rationale",
                ),
                (
                    "semantic_routing_target",
                    "selection_tier",
                    "primary/reserve candidate routing tier",
                ),
            ):
                add_events_for_aliases(
                    events,
                    aliases=aliases,
                    lookup=lookup,
                    event_type=event_type,
                    evidence=evidence_for(
                        root,
                        lecture_rel,
                        f"/candidates/{index}/{field}",
                        detail,
                    ),
                )
    return events


def path_event_types(relative: str) -> set[str]:
    lower = relative.lower()
    events: set[str] = set()
    if lower.startswith("orchestration/prompts/") or lower.endswith(".prompt"):
        events.add("semantic_prompt")
    if "selection_rationale" in lower:
        events.add("selection_rationale")
    if "dossier" in lower:
        events.add("semantic_dossier_description")
    if any(
        token in lower
        for token in (
            "candidate_queue",
            "candidate_review",
            "candidate_pool",
            "candidate_funnel",
            "candidate_matrix",
            "family_candidates",
            "family_mining",
            "source_candidates",
        )
    ):
        events.add("candidate_queue_review_or_mining")
    if any(token in lower for token in ("ranking", "ranked", "learned_model")):
        events.add("learned_ranking")
    if any(
        token in lower
        for token in (
            "targeted_source_prospecting",
            "acquisition_routes",
            "source_disjoint_scaleup",
        )
    ):
        events.add("semantic_routing_target")
    if lower.startswith("data/restricted/") and (
        "acquisition_manifest" in lower or ".source_manifest.json" in lower
    ):
        events.add("media_acquired")
    if lower.startswith("data/restricted/") and (
        "index_v1/" in lower
        or "index_v1_smoke/" in lower
        or "observation_manifest" in lower
        or "segment_manifest" in lower
    ):
        events.add("media_indexed")
    if any(
        token in lower
        for token in (
            "observation_manifest",
            "content_recon",
            "machine_review",
            "manual_review",
            "page_observation",
        )
    ):
        events.add("transcript_or_page_content_observation")
    return events


def line_exposure_events(
    root: Path,
    pinned_files: list[dict[str, Any]],
    lookup: dict[str, str],
    events: dict[tuple[str, str, str, str, str], dict[str, Any]],
) -> None:
    for inventory_row in pinned_files:
        relative = inventory_row["path"]
        event_types = path_event_types(relative)
        if not event_types:
            continue
        path = root / relative
        for line_number, line in enumerate(read_text(path).splitlines(), 1):
            aliases = aliases_in_value(line, lookup)
            if not aliases:
                continue
            detail = line.strip()
            if len(detail) > 240:
                detail = detail[:237] + "..."
            for event_type in event_types:
                add_events_for_aliases(
                    events,
                    aliases=aliases,
                    lookup=lookup,
                    event_type=event_type,
                    evidence=Evidence(
                        path=relative,
                        locator=f"line:{line_number}",
                        sha256=inventory_row["sha256"],
                        detail=detail or event_type,
                    ),
                )


def finalize_events(
    events: dict[tuple[str, str, str, str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = sorted(
        events.values(),
        key=lambda row: (
            row["closure_root"],
            EVENT_ORDER.index(row["event_type"]),
            row["evidence"]["path"],
            row["evidence"]["locator"],
            row["evidence"]["detail"],
        ),
    )
    for index, row in enumerate(rows, 1):
        row["event_id"] = f"MXE2-{index:05d}"
    return rows


def summarize_contamination(
    components: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    component_by_root = {row["closure_root"]: row for row in components}
    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_root[event["closure_root"]].append(event)
    rows = []
    for closure in sorted(by_root):
        component = component_by_root[closure]
        closure_events = by_root[closure]
        rows.append(
            {
                "aliases": component["aliases"],
                "closure_root": closure,
                "contaminated": True,
                "event_ids": [row["event_id"] for row in closure_events],
                "event_types": sorted(
                    {row["event_type"] for row in closure_events},
                    key=EVENT_ORDER.index,
                ),
                "eligibility": "INELIGIBLE_CONTAMINATED",
            }
        )
    return rows


def neutral_candidate_universe(
    root: Path,
    pinned_paths: set[str],
    lookup: dict[str, str],
    contaminated_roots: set[str],
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    epic_rel = (
        "data/source_recon/assembly_epic_access_v2/metadata/epic/"
        "EPIC_100_video_info.csv"
    )
    if epic_rel in pinned_paths:
        by_root: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
        with (root / epic_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                video = row.get("video_id", "")
                match = EPIC_VIDEO_RE.fullmatch(video)
                if not match:
                    continue
                duration = float(row.get("duration", row.get("duration_seconds", 0)))
                if 1200 <= duration <= 5400:
                    closure = lookup.get(
                        f"EPIC:P{match.group('participant')}", ""
                    )
                    by_root[closure].append((video, duration, line_number))
        for closure, rows in by_root.items():
            if not closure or closure in contaminated_roots:
                continue
            video, duration, line_number = min(
                rows,
                key=lambda item: (
                    hashlib.sha256(item[0].encode()).hexdigest(),
                    item[0],
                ),
            )
            candidates[(closure, video)] = {
                "closure_root": closure,
                "derivation_rule": (
                    "official EPIC metadata only; 1200-5400 seconds; "
                    "minimum SHA-256(video_id), then video_id"
                ),
                "exact_object_or_session_id": video,
                "family": "EPIC",
                "neutral_evidence": evidence_for(
                    root,
                    epic_rel,
                    f"line:{line_number}",
                    f"official video metadata; duration_seconds={duration}",
                ).as_dict(),
                "semantic_routing_event_count": 0,
            }

    assembly_rel = (
        "data/source_recon/assembly_epic_access_v2/derived/"
        "assembly_sessions.csv"
    )
    if assembly_rel in pinned_paths:
        by_root: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        with (root / assembly_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                participant = row.get("participant_id", "")
                session = row.get("session_id", "")
                if not participant or not session:
                    continue
                view_count = int(row.get("view_file_count", row.get("mp4_count", 0)))
                if view_count and view_count != 12:
                    continue
                closure = lookup.get(f"ASSEMBLY101:{participant}", "")
                by_root[closure].append((session, view_count, line_number))
        for closure, rows in by_root.items():
            if not closure or closure in contaminated_roots:
                continue
            session, view_count, line_number = min(
                rows,
                key=lambda item: (
                    hashlib.sha256(item[0].encode()).hexdigest(),
                    item[0],
                ),
            )
            candidates[(closure, session)] = {
                "closure_root": closure,
                "derivation_rule": (
                    "official Assembly101 session metadata only; complete "
                    "12-view session when view count is available; minimum "
                    "SHA-256(session_id), then session_id"
                ),
                "exact_object_or_session_id": session,
                "family": "ASSEMBLY101",
                "neutral_evidence": evidence_for(
                    root,
                    assembly_rel,
                    f"line:{line_number}",
                    f"official participant/session metadata; view_count={view_count}",
                ).as_dict(),
                "semantic_routing_event_count": 0,
            }

    cc_rel = "data/source_recon/captaincook4d_access_v1/video_information.csv"
    if cc_rel in pinned_paths:
        by_root: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
        with (root / cc_rel).open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                duration = float(row.get("duration(sec)", 0))
                if not 1200 <= duration <= 5400:
                    continue
                closure = lookup.get(f"CC4D:P{int(row['person_id']):02d}", "")
                by_root[closure].append(
                    (row["recording_id"], duration, line_number)
                )
        for closure, rows in by_root.items():
            if not closure or closure in contaminated_roots:
                continue
            recording, duration, line_number = min(
                rows,
                key=lambda item: (
                    hashlib.sha256(item[0].encode()).hexdigest(),
                    item[0],
                ),
            )
            candidates[(closure, recording)] = {
                "closure_root": closure,
                "derivation_rule": (
                    "official CaptainCook4D recording metadata only; "
                    "1200-5400 seconds; minimum SHA-256(recording_id), "
                    "then recording_id"
                ),
                "exact_object_or_session_id": recording,
                "family": "CAPTAINCOOK4D",
                "neutral_evidence": evidence_for(
                    root,
                    cc_rel,
                    f"line:{line_number}",
                    f"official recording metadata; duration_seconds={duration}",
                ).as_dict(),
                "semantic_routing_event_count": 0,
            }
    return sorted(
        candidates.values(),
        key=lambda row: (row["closure_root"], row["exact_object_or_session_id"]),
    )


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("SCHEMA_VERSION_MISMATCH")
    if manifest.get("final_marker") != FINAL_READY:
        raise ManifestError("FINAL_MARKER_MISMATCH")
    freeze = manifest.get("scan_freeze", {})
    pinned = freeze.get("pinned_files", [])
    if not pinned:
        raise ManifestError("PINNED_INVENTORY_EMPTY")
    if freeze.get("pinned_inventory_sha256") != sha256_value(pinned):
        raise ManifestError("PINNED_INVENTORY_HASH_MISMATCH")
    events = manifest.get("contamination_events", [])
    if not events:
        raise ManifestError("CONTAMINATION_EVENTS_EMPTY")
    touched = {
        row["closure_root"] for row in manifest.get("contaminated_closures", [])
    }
    ledger_roots = set(manifest["ledger_v2_audit"]["closure_roots"])
    missing = ledger_roots - touched
    if missing:
        raise ManifestError(f"LEDGER_V2_CLOSURES_NOT_CONTAMINATED:{sorted(missing)}")
    components = [
        set(row["aliases"]) for row in manifest["alias_graph"]["components"]
    ]
    required_sets = (
        {"cand-042", "EC-NARA-CITY-UNDER-ICE", "NAID:2569752"},
        {"EPIC:P23", "P23", "P23_102"},
    )
    for required in required_sets:
        if not any(required <= aliases for aliases in components):
            raise ManifestError(f"REQUIRED_ALIAS_CLOSURE_MISSING:{sorted(required)}")
    for root, expected in (
        (
            "SG-MIT-2-003J-L01",
            {"repl-mit-2-003j-lecture-1", "2.003J Dynamics and Control I"},
        ),
        (
            "SG-YALE-HIST202-L01",
            {
                "repl-yale-hist-202-lecture-1",
                "HIST-202 European Civilization, 1648-1945",
            },
        ),
    ):
        row = next(
            (
                component
                for component in manifest["alias_graph"]["components"]
                if component["closure_root"] == root
            ),
            None,
        )
        if not row or not expected <= set(row["aliases"]):
            raise ManifestError(f"LECTURE_TITLE_COURSE_ALIAS_MISSING:{root}")
    for row in manifest["candidate_universe"]:
        if row["closure_root"] in touched:
            raise ManifestError("CONTAMINATED_CANDIDATE_IN_UNIVERSE")
        if row["semantic_routing_event_count"] != 0:
            raise ManifestError("SEMANTICALLY_ROUTED_CANDIDATE_IN_UNIVERSE")


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    pinned_files, supplemental, skipped = frozen_inventory(root)
    pinned_paths = {row["path"] for row in pinned_files}
    components, lookup = extract_alias_graph(root, pinned_paths)
    events_map = structured_exposure_events(root, pinned_paths, lookup)
    line_exposure_events(root, pinned_files, lookup, events_map)
    events = finalize_events(events_map)
    contaminated = summarize_contamination(components, events)
    contaminated_roots = {row["closure_root"] for row in contaminated}
    universe = neutral_candidate_universe(
        root, pinned_paths, lookup, contaminated_roots
    )
    ledger = load_json(root / LEDGER_V2_REL)
    ledger_roots = sorted(
        row["closure_root"] for row in ledger.get("test_groups", [])
    )
    manifest = {
        "alias_graph": {
            "component_count": len(components),
            "components": components,
            "closure_rule": (
                "Exact repository evidence closes all participant recordings, "
                "CaptainCook4D person/environments, Assembly101 participant "
                "sessions/views, and complete production aliases. Any event "
                "on one member contaminates the full closure."
            ),
        },
        "candidate_universe": universe,
        "candidate_universe_policy": {
            "allowed_sources": [
                "neutral official EPIC video metadata",
                "neutral official CaptainCook4D recording metadata",
                "neutral official Assembly101 participant/session metadata",
            ],
            "decision_rule": (
                "Derive exact candidates mechanically from neutral official "
                "metadata, then remove every closure with any semantic-routing, "
                "selection, prompt, dossier, review, ranking, acquisition, or "
                "index event. Candidate IDs are not hardcoded."
            ),
            "semantic_routing_exclusion_is_fail_closed": True,
        },
        "contaminated_closures": contaminated,
        "contamination_events": events,
        "contamination_policy": {
            "contaminating_event_types": list(EVENT_ORDER),
            "decision_rule": (
                "Every named modality/yield/role target, candidate contribution/"
                "selection/rank/reserve/primary pool, selection rationale, "
                "prompt, semantic dossier description, transcript/page-content "
                "observation, candidate queue/review/mining record, learned "
                "ranking, and acquired/indexed-media record contaminates its "
                "entire participant/person/production alias closure."
            ),
        },
        "created_date": CREATED_DATE,
        "final_marker": FINAL_READY,
        "ledger_v2_audit": {
            "all_contaminated": set(ledger_roots) <= contaminated_roots,
            "closure_count": len(ledger_roots),
            "closure_roots": ledger_roots,
            "ledger_path": LEDGER_V2_REL.as_posix(),
            "ledger_sha256": sha256_file(root / LEDGER_V2_REL),
        },
        "manifest_id": MANIFEST_ID,
        "safety_boundary": {
            "media_opened": False,
            "network_used": False,
            "semantic_annotation_bodies_opened": False,
            "excluded_directory_names": sorted(EXCLUDED_DIRECTORY_NAMES),
            "semantic_body_name_tokens": sorted(SEMANTIC_BODY_NAME_TOKENS),
        },
        "scan_freeze": {
            "allowlisted_extensions": sorted(ALLOWLISTED_EXTENSIONS),
            "freeze_rule": (
                "Committed pinned paths and hashes are authoritative. Files "
                "discovered later are supplemental audit entries only and do "
                "not contribute aliases, events, contamination, or candidates."
            ),
            "max_file_bytes": MAX_FILE_BYTES,
            "pinned_file_count": len(pinned_files),
            "pinned_files": pinned_files,
            "pinned_inventory_sha256": sha256_value(pinned_files),
            "roots": list(SCAN_ROOTS),
            "skipped_by_reason": skipped,
            "supplemental_post_freeze_file_count": len(supplemental),
            "supplemental_post_freeze_files": supplemental,
        },
        "schema_version": SCHEMA_VERSION,
    }
    validate_manifest(manifest)
    return manifest


def render_markdown(manifest: dict[str, Any]) -> str:
    counts = Counter(
        row["event_type"] for row in manifest["contamination_events"]
    )
    ledger = manifest["ledger_v2_audit"]
    freeze = manifest["scan_freeze"]
    lines = [
        "# Source exposure alias manifest v2",
        "",
        f"- Final marker: `{manifest['final_marker']}`",
        f"- Date: `{manifest['created_date']}`",
        f"- Pinned scanned files: {freeze['pinned_file_count']}",
        f"- Pinned inventory SHA-256: `{freeze['pinned_inventory_sha256']}`",
        (
            "- Supplemental post-freeze files: "
            f"{freeze['supplemental_post_freeze_file_count']}"
        ),
        f"- Alias closures: {manifest['alias_graph']['component_count']}",
        f"- Contamination events: {len(manifest['contamination_events'])}",
        f"- Contaminated closures: {len(manifest['contaminated_closures'])}",
        f"- Neutral-only candidate closures: {len(manifest['candidate_universe'])}",
        "",
        "## Safety and freeze boundary",
        "",
        (
            "The generator uses repository text evidence only. It does not use "
            "network access, open media, or inspect semantic annotation, "
            "transcript/caption, checkpoint, trajectory, or generated "
            "observation bodies."
        ),
        "",
        (
            "The committed path/hash inventory is authoritative. New eligible "
            "files are listed only in the supplemental post-freeze audit and "
            "cannot redefine v2."
        ),
        "",
        "## Contamination policy",
        "",
        manifest["contamination_policy"]["decision_rule"],
        "",
        "Participant/person/production membership is resolved before exposure "
        "propagation, including symbolic pools and cases where only one member "
        "was routed.",
        "",
        "## Event counts",
        "",
        "| Event type | Exact evidence rows |",
        "|---|---:|",
    ]
    for event_type in EVENT_ORDER:
        lines.append(f"| `{event_type}` | {counts[event_type]} |")
    lines.extend(
        [
            "",
            "## v2 ledger audit",
            "",
            f"- Ledger closures checked: {ledger['closure_count']}",
            f"- All contaminated: `{str(ledger['all_contaminated']).lower()}`",
            "",
            "| Closure | Event types |",
            "|---|---|",
        ]
    )
    contaminated_by_root = {
        row["closure_root"]: row for row in manifest["contaminated_closures"]
    }
    for root in ledger["closure_roots"]:
        event_types = ", ".join(
            f"`{event}`" for event in contaminated_by_root[root]["event_types"]
        )
        lines.append(f"| `{root}` | {event_types} |")
    lines.extend(
        [
            "",
            "## Neutral-only derived candidate universe",
            "",
            (
                "These rows are mechanically derived from neutral official "
                "metadata/access registries and have zero prior semantic-routing "
                "events. They are discovery output, not acquisition authority."
            ),
            "",
            "| Closure | Exact object/session | Family |",
            "|---|---|---|",
        ]
    )
    for row in manifest["candidate_universe"]:
        lines.append(
            f"| `{row['closure_root']}` | "
            f"`{row['exact_object_or_session_id']}` | `{row['family']}` |"
        )
    lines.extend(
        [
            "",
            "## Required closure checks",
            "",
            "- `cand-042`, `EC-NARA-CITY-UNDER-ICE`, and `NAID:2569752` close together.",
            "- `P23`, `P23_102`, and all official P23 videos close to `EPIC:P23`.",
            "- EPIC routed pools propagate to every named participant closure.",
            "- CaptainCook4D routed recordings propagate to full person closures.",
            "- Assembly101 symbolic frozen-primary pools resolve to exact participant closures.",
            "- MIT and Yale lecture candidate IDs close with exact course and title aliases.",
            "",
            f"`{FINAL_READY}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(root: Path, manifest: dict[str, Any]) -> None:
    output = root / OUTPUT_REL
    review = root / REVIEW_REL
    output.parent.mkdir(parents=True, exist_ok=True)
    review.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review.write_text(render_markdown(manifest), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed outputs instead of writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    manifest = build_manifest(root)
    expected_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    expected_markdown = render_markdown(manifest)
    if args.check:
        if (root / OUTPUT_REL).read_text(encoding="utf-8") != expected_json:
            raise ManifestError("COMMITTED_JSON_IS_STALE")
        if (root / REVIEW_REL).read_text(encoding="utf-8") != expected_markdown:
            raise ManifestError("COMMITTED_MARKDOWN_IS_STALE")
    else:
        write_outputs(root, manifest)
    print(FINAL_READY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
