"""Build a deterministic repository-wide source exposure and alias manifest.

The scanner is deliberately non-semantic: it reads bounded text, JSON, CSV,
prompt, log, index, and manifest artifacts, but never opens media, model
weights, or paths whose directory names identify annotation bodies.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.source-exposure-alias-manifest/1.0"
MANIFEST_ID = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V1"
FINAL_READY = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V1_READY"
CREATED_DATE = "2026-10-14"

OUTPUT_REL = Path("data/rehearsal_plan/source_exposure_alias_manifest_v1.json")
REVIEW_REL = Path("docs/review/source_exposure_alias_manifest_v1.md")

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
    "media",
    "models",
    "node_modules",
}
# These artifacts are downstream products of this manifest. Scanning them
# back into v1 would make the frozen exposure evidence self-referential and
# would change it whenever a ledger/disposition is added.
DOWNSTREAM_EXCLUDED_NAMES = {
    "source_exposure_alias_manifest_v1.json",
    "source_exposure_alias_manifest_v1.md",
    "untouched_test_group_ledger_v1.json",
    "untouched_test_group_ledger_v1.md",
    "untouched_test_group_ledger_v1_disposition.json",
    "untouched_test_group_ledger_v1_disposition.md",
    "untouched_test_group_ledger_v2.json",
    "untouched_test_group_ledger_v2.md",
}

EVENT_ORDER = (
    "metadata_catalog_only",
    "rights/access_preflight",
    "failed_zero_byte_probe",
    "media_acquired",
    "media_indexed",
    "learned_model_ranked",
    "candidate_mined",
    "semantic_prompt_exposed",
    "human_prescreened",
    "annotation_opened",
)
CONDITIONAL_EVENTS = {
    "metadata_catalog_only",
    "rights/access_preflight",
    "failed_zero_byte_probe",
}
CONTAMINATING_EVENTS = set(EVENT_ORDER) - CONDITIONAL_EVENTS

EPIC_VIDEO_RE = re.compile(r"\bP(?P<participant>\d{2})_(?P<session>\d{2,3})\b")
EPIC_PARTICIPANT_RE = re.compile(r"\bP(?P<participant>\d{2})\b")
CC4D_RECORDING_RE = re.compile(r"(?<!\d)(?P<environment>\d{1,2})_(?P<person>\d{1,2})(?!\d)")
CC4D_GROUP_RE = re.compile(
    r"\bcc4d_p(?P<person>\d{2})_e(?P<environment>\d{2})\b",
    re.IGNORECASE,
)
ASSEMBLY_GROUP_RE = re.compile(r"\bassembly101_p(?P<participant>\d{4})\b", re.IGNORECASE)
ASSEMBLY_SESSION_RE = re.compile(
    r"\bnusar-[A-Za-z0-9_-]*_(?P<participant>9\d{3})(?:[-_][A-Za-z0-9_-]+)?\b",
    re.IGNORECASE,
)
CANDIDATE_RE = re.compile(r"\bcand-\d{3}\b", re.IGNORECASE)
EC_RE = re.compile(r"\bEC-[A-Z0-9][A-Z0-9-]*\b")
NAID_RE = re.compile(r"\bNAID[: -]?(?P<id>\d+)\b", re.IGNORECASE)
NASA_POST_RE = re.compile(r"\bNASA\+\s*post\s*(?P<id>\d+)\b", re.IGNORECASE)
NASA_CONTENT_RE = re.compile(r"\bcontent[-_ ]?id\s*(?P<id>\d+)\b", re.IGNORECASE)
NASA_ASSET_RE = re.compile(r"\bHLS\s+asset\s*(?P<id>\d+)\b", re.IGNORECASE)
LECTURE_GROUP_RE = re.compile(r"\bSG-(?:MIT|YALE|OXFORD)-[A-Z0-9-]+\b", re.IGNORECASE)
LECTURE_REPLACEMENT_RE = re.compile(
    r"\brepl-(?:mit|yale|oxford)-[a-z0-9-]+\b",
    re.IGNORECASE,
)


class ManifestError(ValueError):
    """Raised when evidence cannot be converted into a safe manifest."""


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
        self._parents: dict[str, str] = {}
        self._members: dict[str, set[str]] = defaultdict(set)
        self._kinds: dict[str, set[str]] = defaultdict(set)
        self._evidence: dict[tuple[str, str], set[Evidence]] = defaultdict(set)

    def _add(self, alias: str) -> None:
        if alias not in self._parents:
            self._parents[alias] = alias
            self._members[alias].add(alias)

    def find(self, alias: str) -> str:
        self._add(alias)
        parent = self._parents[alias]
        if parent != alias:
            self._parents[alias] = self.find(parent)
        return self._parents[alias]

    def union(
        self,
        left: str,
        right: str,
        *,
        kind: str,
        evidence: Evidence,
    ) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            root, child = sorted((left_root, right_root))
            self._parents[child] = root
            self._members[root].update(self._members.pop(child))
            self._kinds[root].update(self._kinds.pop(child, set()))
        root = self.find(left)
        self._kinds[root].add(kind)
        edge = tuple(sorted((left, right)))
        self._evidence[edge].add(evidence)

    def components(self) -> list[dict[str, Any]]:
        roots: dict[str, set[str]] = defaultdict(set)
        for alias in self._parents:
            roots[self.find(alias)].add(alias)
        rows = []
        for aliases in sorted(roots.values(), key=min):
            closure_root = choose_closure_root(aliases)
            edges = []
            for edge, evidence in sorted(self._evidence.items()):
                if edge[0] in aliases and edge[1] in aliases:
                    edges.append(
                        {
                            "aliases": list(edge),
                            "evidence": [
                                item.as_dict() for item in sorted(evidence, key=evidence_key)
                            ],
                        }
                    )
            kind_set: set[str] = set()
            for alias in aliases:
                kind_set.update(self._kinds[self.find(alias)])
            rows.append(
                {
                    "aliases": sorted(aliases),
                    "closure_root": closure_root,
                    "kinds": sorted(kind_set),
                    "supporting_edges": edges,
                }
            )
        return sorted(rows, key=lambda row: row["closure_root"])


def evidence_key(value: Evidence) -> tuple[str, str, str, str]:
    return (value.path, value.locator, value.detail, value.sha256)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def normalize_alias(value: str) -> str:
    value = value.strip().strip("`'\"")
    if CANDIDATE_RE.fullmatch(value):
        return value.lower()
    if LECTURE_REPLACEMENT_RE.fullmatch(value):
        return value.lower()
    if EC_RE.fullmatch(value):
        return value.upper()
    if LECTURE_GROUP_RE.fullmatch(value):
        return value.upper()
    naid = NAID_RE.fullmatch(value)
    if naid:
        return f"NAID:{naid.group('id')}"
    return value


def choose_closure_root(aliases: Iterable[str]) -> str:
    values = sorted(set(aliases))
    priority_patterns = (
        r"^EPIC:P\d{2}$",
        r"^CC4D:P\d{2}$",
        r"^ASSEMBLY101:\d{4}$",
        r"^EC-",
        r"^SG-",
        r"^NOAA:",
        r"^NARA:",
        r"^NASA:",
    )
    for pattern in priority_patterns:
        matches = [value for value in values if re.search(pattern, value)]
        if matches:
            return matches[0]
    return values[0]


def scan_inventory(root: Path) -> tuple[list[Path], dict[str, Any]]:
    files: list[Path] = []
    skipped_by_reason: Counter[str] = Counter()
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if relative in {OUTPUT_REL, REVIEW_REL}:
                skipped_by_reason["self_output"] += 1
                continue
            if path.name in DOWNSTREAM_EXCLUDED_NAMES:
                skipped_by_reason["downstream_product"] += 1
                continue
            if set(relative.parts) & EXCLUDED_DIRECTORY_NAMES:
                skipped_by_reason["excluded_directory"] += 1
                continue
            if path.suffix.lower() not in ALLOWLISTED_EXTENSIONS:
                skipped_by_reason["extension_not_allowlisted"] += 1
                continue
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                skipped_by_reason["over_size_limit"] += 1
                continue
            files.append(path)
    inventory = {
        "allowlisted_extensions": sorted(ALLOWLISTED_EXTENSIONS),
        "excluded_directory_names": sorted(EXCLUDED_DIRECTORY_NAMES),
        "max_file_bytes": MAX_FILE_BYTES,
        "roots": list(SCAN_ROOTS),
        "scanned_file_count": len(files),
        "scanned_total_bytes": sum(path.stat().st_size for path in files),
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
    }
    return files, inventory


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def file_evidence(root: Path, path: Path, locator: str, detail: str) -> Evidence:
    return Evidence(
        path=path.relative_to(root).as_posix(),
        locator=locator,
        sha256=sha256_file(path),
        detail=detail,
    )


def line_number_for(path: Path, needle: str) -> int:
    for number, line in enumerate(read_text(path).splitlines(), 1):
        if needle in line:
            return number
    return 1


def add_edge(
    graph: AliasGraph,
    root: Path,
    path: Path,
    left: str,
    right: str,
    *,
    kind: str,
    locator: str,
    detail: str,
) -> None:
    graph.union(
        normalize_alias(left),
        normalize_alias(right),
        kind=kind,
        evidence=file_evidence(root, path, locator, detail),
    )


def extract_aliases(root: Path, files: set[Path]) -> AliasGraph:
    graph = AliasGraph()

    epic_csv = root / "data/source_recon/assembly_epic_access_v2/metadata/epic/EPIC_100_video_info.csv"
    if epic_csv in files:
        with epic_csv.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                source_id = row.get("video_id", "")
                match = EPIC_VIDEO_RE.fullmatch(source_id)
                if not match:
                    continue
                participant = match.group("participant")
                add_edge(
                    graph,
                    root,
                    epic_csv,
                    f"EPIC:P{participant}",
                    f"P{participant}",
                    kind="epic_participant",
                    locator=f"line:{line_number}",
                    detail=f"participant closure for {source_id}",
                )
                add_edge(
                    graph,
                    root,
                    epic_csv,
                    f"EPIC:P{participant}",
                    source_id,
                    kind="epic_participant",
                    locator=f"line:{line_number}",
                    detail="official EPIC participant/video row",
                )

    cc4d_csv = root / "data/source_recon/captaincook4d_access_v1/video_information.csv"
    if cc4d_csv in files:
        with cc4d_csv.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                recording = row.get("recording_id", "")
                if not recording:
                    continue
                person = int(row["person_id"])
                environment = int(row["environment_id"])
                person_root = f"CC4D:P{person:02d}"
                group = f"cc4d_p{person:02d}_e{environment:02d}"
                add_edge(
                    graph,
                    root,
                    cc4d_csv,
                    person_root,
                    group,
                    kind="captaincook_person_environment",
                    locator=f"line:{line_number}",
                    detail=f"person {person}, environment {environment}",
                )
                add_edge(
                    graph,
                    root,
                    cc4d_csv,
                    person_root,
                    recording,
                    kind="captaincook_person_environment",
                    locator=f"line:{line_number}",
                    detail="official recording/person/environment row",
                )
                add_edge(
                    graph,
                    root,
                    cc4d_csv,
                    group,
                    recording,
                    kind="captaincook_person_environment",
                    locator=f"line:{line_number}",
                    detail="recording belongs to exact person/environment group",
                )

    assembly_csv = root / "data/source_recon/assembly_epic_access_v2/derived/assembly_sessions.csv"
    if assembly_csv in files:
        with assembly_csv.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                participant = row.get("participant_id", "")
                session = row.get("session_id", "")
                if not participant or not session:
                    continue
                root_alias = f"ASSEMBLY101:{participant}"
                add_edge(
                    graph,
                    root,
                    assembly_csv,
                    root_alias,
                    f"assembly101_p{participant}",
                    kind="assembly_participant",
                    locator=f"line:{line_number}",
                    detail="Assembly101 participant closure",
                )
                add_edge(
                    graph,
                    root,
                    assembly_csv,
                    root_alias,
                    session,
                    kind="assembly_participant",
                    locator=f"line:{line_number}",
                    detail="official participant/session row",
                )

    candidate_csv = root / "data/candidates/source_candidates.csv"
    if candidate_csv in files:
        with candidate_csv.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), 2):
                candidate = row.get("candidate_id", "")
                stable = row.get("stable_source_id", "")
                family = row.get("source_family", "")
                if not candidate or not stable:
                    continue
                if family == "NARA" and NAID_RE.fullmatch(stable):
                    add_edge(
                        graph,
                        root,
                        candidate_csv,
                        candidate,
                        stable,
                        kind="nara_candidate_naid",
                        locator=f"line:{line_number}",
                        detail=row.get("title", "NARA candidate"),
                    )
                elif family == "NOAA":
                    add_edge(
                        graph,
                        root,
                        candidate_csv,
                        f"NOAA:{candidate.lower()}",
                        candidate,
                        kind="noaa_candidate",
                        locator=f"line:{line_number}",
                        detail=row.get("title", "NOAA candidate"),
                    )
                elif family == "NASA":
                    add_edge(
                        graph,
                        root,
                        candidate_csv,
                        f"NASA:{candidate.lower()}",
                        candidate,
                        kind="nasa_candidate",
                        locator=f"line:{line_number}",
                        detail=row.get("title", "NASA candidate"),
                    )
                    add_edge(
                        graph,
                        root,
                        candidate_csv,
                        f"NASA:{candidate.lower()}",
                        stable,
                        kind="nasa_content_asset",
                        locator=f"line:{line_number}",
                        detail="candidate stable source identifier",
                    )

    event_path = root / "data/rehearsal_plan/event_centric_source_dossiers_v1.json"
    if event_path in files:
        document = load_json(event_path)
        for index, row in enumerate(document.get("candidates", [])):
            group = row.get("source_group_id")
            canonical = row.get("canonical_id")
            if group and canonical:
                add_edge(
                    graph,
                    root,
                    event_path,
                    group,
                    canonical,
                    kind="event_centric_alias",
                    locator=f"/candidates/{index}/canonical_id",
                    detail=row.get("title", "event-centric candidate"),
                )

    nara_path = root / "data/rehearsal_plan/nara_event_source_dossiers_v1.json"
    if nara_path in files:
        document = load_json(nara_path)
        for index, row in enumerate(document.get("sources", [])):
            group = row.get("source_group_id")
            candidate = row.get("candidate_id")
            catalog = row.get("catalog_id")
            if group and candidate:
                add_edge(
                    graph,
                    root,
                    nara_path,
                    group,
                    candidate,
                    kind="nara_candidate_naid",
                    locator=f"/sources/{index}/candidate_id",
                    detail=row.get("title", "NARA source"),
                )
            if group and catalog:
                add_edge(
                    graph,
                    root,
                    nara_path,
                    group,
                    catalog,
                    kind="nara_candidate_naid",
                    locator=f"/sources/{index}/catalog_id",
                    detail=row.get("title", "NARA source"),
                )

    live_path = root / "data/rehearsal_plan/event_centric_live_preflight_v1.json"
    if live_path in files:
        document = load_json(live_path)
        for index, row in enumerate(document.get("candidates", [])):
            group = row.get("source_group_id")
            stable = row.get("stable_item_id", "")
            if not group or not stable:
                continue
            stable_alias = f"EVENT-STABLE:{stable}"
            add_edge(
                graph,
                root,
                live_path,
                group,
                stable_alias,
                kind="event_centric_alias",
                locator=f"/candidates/{index}/stable_item_id",
                detail=row.get("title", "live preflight source"),
            )
            candidate = CANDIDATE_RE.search(stable)
            if candidate:
                add_edge(
                    graph,
                    root,
                    live_path,
                    group,
                    candidate.group(),
                    kind="noaa_candidate",
                    locator=f"/candidates/{index}/stable_item_id",
                    detail="embedded NOAA candidate identifier",
                )
            for regex, prefix, kind in (
                (NASA_POST_RE, "NASA:POST:", "nasa_content_asset"),
                (NASA_CONTENT_RE, "NASA:CONTENT:", "nasa_content_asset"),
                (NASA_ASSET_RE, "NASA:ASSET:", "nasa_content_asset"),
            ):
                match = regex.search(stable)
                if match:
                    add_edge(
                        graph,
                        root,
                        live_path,
                        group,
                        f"{prefix}{match.group('id')}",
                        kind=kind,
                        locator=f"/candidates/{index}/stable_item_id",
                        detail=stable,
                    )

    untouched_path = root / "data/rehearsal_plan/untouched_test_group_ledger_v1.json"
    if untouched_path in files:
        document = load_json(untouched_path)
        for index, row in enumerate(document.get("test_groups", [])):
            source_group = row.get("source_group_id")
            participant = row.get("participant_block_id")
            exact = row.get("exact_object_or_session_id")
            if source_group and participant:
                add_edge(
                    graph,
                    root,
                    untouched_path,
                    participant,
                    source_group,
                    kind="frozen_group_closure",
                    locator=f"/test_groups/{index}/source_group_id",
                    detail="frozen prospective untouched group closure",
                )
            if source_group and exact:
                add_edge(
                    graph,
                    root,
                    untouched_path,
                    source_group,
                    exact,
                    kind="frozen_group_closure",
                    locator=f"/test_groups/{index}/exact_object_or_session_id",
                    detail="frozen exact object/session alias",
                )

    replacement_path = root / "data/rehearsal_plan/mini_pilot_replacement_candidates.json"
    if replacement_path in files:
        document = load_json(replacement_path)
        for index, row in enumerate(document.get("candidates", [])):
            candidate = row.get("candidate_id", "")
            title = row.get("title", "")
            mapped = lecture_group_for_candidate(candidate)
            if mapped:
                add_edge(
                    graph,
                    root,
                    replacement_path,
                    mapped,
                    candidate,
                    kind="public_lecture",
                    locator=f"/candidates/{index}/candidate_id",
                    detail=title,
                )

    return graph


def lecture_group_for_candidate(candidate: str) -> str | None:
    mappings = {
        "repl-oxford-qm-001": "SG-OXFORD-QM-001",
        "repl-mit-res12-003-lecture-1": "SG-MIT-RES12-003-L01",
        "repl-yale-phys-200-lecture-1": "SG-YALE-PHYS200-L01",
        "repl-mit-2-003j-lecture-1": "SG-MIT-2-003J-L01",
        "repl-yale-hist-202-lecture-1": "SG-YALE-HIST202-L01",
    }
    return mappings.get(candidate)


def classify_path(path: Path, text: str) -> set[str]:
    relative = path.as_posix().lower()
    lower = text.lower()
    events: set[str] = set()

    if any(token in relative for token in ("source_recon", "access_registry", "dossier")):
        events.add("metadata_catalog_only")
    # Candidate queues/reviews and event-centric dossiers contain semantic
    # suitability hypotheses, not merely catalog metadata. They therefore
    # contaminate an untouched-test closure even when no media was acquired.
    if (
        relative.startswith("data/candidates/")
        or "candidate_pool_review" in relative
        or "top30_review_queue" in relative
        or "event_centric_source_dossiers" in relative
    ):
        events.add("candidate_mined")
    if any(token in relative for token in ("preflight", "access_review", "route_probe", "rights")):
        events.add("rights/access_preflight")
    if (
        "media_payload_bytes_saved" in lower
        and re.search(r'"?media_payload_bytes_saved"?\s*[:=]\s*0\b', lower)
    ) or "failed_zero_byte_probe" in lower:
        events.add("failed_zero_byte_probe")
    restricted_content_artifact = relative.startswith("data/restricted/")
    if restricted_content_artifact and (
        "acquisition_manifest" in relative
        or ".source_manifest.json" in relative
        or re.search(
            r'"status"\s*:\s*"(?:complete_verified_ready|complete_validated_promoted)"',
            lower,
        )
    ):
        events.add("media_acquired")
    if restricted_content_artifact and (
        "full_timeline_index" in relative
        or "_index_v1/" in relative
        or re.search(
            r'"decision"\s*:\s*"[^"]*(?:index|timeline)[^"]*ready"',
            lower,
        )
    ):
        events.add("media_indexed")
    if restricted_content_artifact and any(
        token in relative
        for token in ("candidate_registry", "family_mining", "candidate_ranking")
    ):
        events.add("learned_model_ranked")
        events.add("candidate_mined")
    if relative.startswith("orchestration/prompts/") or relative.endswith(".prompt"):
        events.add("semantic_prompt_exposed")
    if (
        '"semantic_annotations_opened_or_used": true' in lower
        or '"semantic_annotations_accessed": true' in lower
        or '"annotation_opened": true' in lower
    ):
        events.add("annotation_opened")

    if "metadata_only" in lower or "metadata_catalog_only" in lower:
        events.add("metadata_catalog_only")
    if "rights/access_preflight" in lower:
        events.add("rights/access_preflight")
    return events


def aliases_in_text(text: str) -> set[str]:
    aliases: set[str] = set()
    aliases.update(normalize_alias(value) for value in CANDIDATE_RE.findall(text))
    aliases.update(normalize_alias(value) for value in EC_RE.findall(text))
    aliases.update(f"NAID:{match.group('id')}" for match in NAID_RE.finditer(text))
    aliases.update(normalize_alias(value) for value in LECTURE_GROUP_RE.findall(text))
    aliases.update(normalize_alias(value) for value in LECTURE_REPLACEMENT_RE.findall(text))
    for match in EPIC_VIDEO_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"P{match.group('participant')}")
        aliases.add(f"EPIC:P{match.group('participant')}")
    for match in CC4D_GROUP_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"CC4D:P{int(match.group('person')):02d}")
    for match in ASSEMBLY_GROUP_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"ASSEMBLY101:{match.group('participant')}")
    for match in ASSEMBLY_SESSION_RE.finditer(text):
        aliases.add(match.group())
        aliases.add(f"ASSEMBLY101:{match.group('participant')}")
    for match in NASA_POST_RE.finditer(text):
        aliases.add(f"NASA:POST:{match.group('id')}")
    for match in NASA_CONTENT_RE.finditer(text):
        aliases.add(f"NASA:CONTENT:{match.group('id')}")
    for match in NASA_ASSET_RE.finditer(text):
        aliases.add(f"NASA:ASSET:{match.group('id')}")
    return aliases


def component_lookup(components: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for component in components:
        for alias in component["aliases"]:
            lookup[alias] = component["closure_root"]
    return lookup


def classify_exposures(
    root: Path,
    files: list[Path],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup = component_lookup(components)
    events: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in files:
        text = read_text(path)
        event_types = classify_path(path.relative_to(root), text)
        if not event_types:
            continue
        aliases = aliases_in_text(text)
        closure_roots = sorted({lookup[alias] for alias in aliases if alias in lookup})
        if not closure_roots:
            continue
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        for closure_root in closure_roots:
            for event_type in event_types:
                key = (closure_root, event_type, relative)
                events[key] = {
                    "closure_root": closure_root,
                    "eligibility_effect": (
                        "CONTAMINATED"
                        if event_type in CONTAMINATING_EVENTS
                        else "CONDITIONAL"
                    ),
                    "event_type": event_type,
                    "evidence": {
                        "locator": "file",
                        "path": relative,
                        "sha256": digest,
                    },
                }
    return sorted(
        events.values(),
        key=lambda row: (
            row["closure_root"],
            EVENT_ORDER.index(row["event_type"]),
            row["evidence"]["path"],
        ),
    )


def explicit_structured_exposures(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(group: str, event: str, relative: str, pointer: str, detail: str) -> None:
        path = root / relative
        if not path.is_file():
            return
        rows.append(
            {
                "closure_root": group,
                "eligibility_effect": (
                    "CONTAMINATED" if event in CONTAMINATING_EVENTS else "CONDITIONAL"
                ),
                "event_type": event,
                "evidence": {
                    "detail": detail,
                    "locator": pointer,
                    "path": relative,
                    "sha256": sha256_file(path),
                },
            }
        )

    add(
        "EPIC:P23",
        "media_acquired",
        "data/restricted/epic_p23_102_source_v1/manifests/epic_p23_102_exact_manifest.json",
        "/status",
        "COMPLETE_VERIFIED_READY exact P23_102 media",
    )
    add(
        "EPIC:P23",
        "media_indexed",
        "data/restricted/epic_p23_102_full_timeline_index_v1/build_manifest.json",
        "/decision",
        "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY",
    )
    add(
        "EPIC:P23",
        "learned_model_ranked",
        "data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json",
        "/decision",
        "machine-provisional learned observation ranking",
    )
    add(
        "EPIC:P23",
        "candidate_mined",
        "data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json",
        "/summary/candidate_count",
        "P23 candidate registry",
    )
    add(
        "EPIC:P27",
        "media_acquired",
        "data/restricted/epic_wave1_sources_v1/manifests/epic_wave1_acquisition_manifest.json",
        "/sources",
        "EPIC Wave-1 acquired source",
    )
    add(
        "EPIC:P28",
        "media_acquired",
        "data/restricted/epic_wave1_sources_v1/manifests/epic_wave1_acquisition_manifest.json",
        "/sources",
        "EPIC Wave-1 acquired source",
    )
    for person, group, recording in (
        ("CC4D:P01", "cc4d_p01_e08", "16_20"),
        ("CC4D:P02", "cc4d_p02_e02", "15_29"),
        ("CC4D:P03", "cc4d_p03_e03", "26_22"),
    ):
        add(
            person,
            "media_acquired",
            "data/restricted/captaincook4d_wave0_sources_v3/manifests/captaincook4d_wave0_acquisition_manifest.json",
            "/sources",
            f"{recording} / {group} acquired",
        )
        add(
            person,
            "media_indexed",
            "data/restricted/captaincook4d_wave0_index_v1/build_manifest.json",
            "/decision",
            "CaptainCook4D Wave-0 indexed",
        )
    for group in (
        "SG-OXFORD-QM-001",
        "SG-OXFORD-DHL-CONSCIOUSNESS",
        "SG-MIT-RES12-003-L01",
        "SG-YALE-PHYS200-L01",
    ):
        add(
            group,
            "media_acquired",
            f"data/restricted/mini_pilot_sources_v1/{group}/source_manifest.json",
            "/status",
            "COMPLETE_VALIDATED_PROMOTED public lecture source",
        )
        add(
            group,
            "media_indexed",
            "data/rehearsal_plan/mini_pilot_full_timeline_v1.json",
            "/sources",
            "included in mini-pilot full timeline",
        )
        add(
            group,
            "candidate_mined",
            "data/rehearsal_plan/mini_pilot_family_mining_v1.json",
            "/sources",
            "mini-pilot family mining source",
        )
    add(
        "EC-NOAA-SHIPWRECKS",
        "failed_zero_byte_probe",
        "data/source_recon/event_centric_live_preflight_v1/EC-NOAA-SHIPWRECKS/media_head_failure.json",
        "/media_payload_bytes_saved",
        "interrupted HEAD refresh saved zero media payload bytes",
    )
    return rows


def merge_exposures(
    scanned: list[dict[str, Any]],
    structured: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in (*scanned, *structured):
        evidence = row["evidence"]
        key = (
            row["closure_root"],
            row["event_type"],
            evidence["path"],
            evidence["locator"],
        )
        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (
            row["closure_root"],
            EVENT_ORDER.index(row["event_type"]),
            row["evidence"]["path"],
            row["evidence"]["locator"],
        ),
    )


def summarize_groups(
    components: list[dict[str, Any]],
    exposures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for exposure in exposures:
        by_root[exposure["closure_root"]].append(exposure)
    rows = []
    for component in components:
        root = component["closure_root"]
        event_types = sorted(
            {row["event_type"] for row in by_root.get(root, [])},
            key=EVENT_ORDER.index,
        )
        contaminating = [event for event in event_types if event in CONTAMINATING_EVENTS]
        if contaminating:
            eligibility = "INELIGIBLE_CONTAMINATED"
        elif event_types:
            eligibility = "CONDITIONAL_UNTOUCHED"
        else:
            eligibility = "UNCLASSIFIED_NO_EXPOSURE_EVIDENCE"
        rows.append(
            {
                "aliases": component["aliases"],
                "closure_root": root,
                "eligibility": eligibility,
                "event_types": event_types,
                "touched": bool(contaminating),
            }
        )
    return rows


def candidate_replacements(
    root: Path,
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    group_map = {row["closure_root"]: row for row in groups}
    rows: list[dict[str, Any]] = []

    untouched_path = root / "data/rehearsal_plan/untouched_test_group_ledger_v1.json"
    if untouched_path.is_file():
        document = load_json(untouched_path)
        for index, row in enumerate(document.get("test_groups", [])):
            root_alias = normalize_alias(row["participant_block_id"])
            state = group_map.get(root_alias)
            if state and state["eligibility"] == "CONDITIONAL_UNTOUCHED":
                rows.append(
                    {
                        "closure_root": root_alias,
                        "enumeration_basis": row.get("enumeration_basis"),
                        "evidence": {
                            "locator": f"/test_groups/{index}",
                            "path": untouched_path.relative_to(root).as_posix(),
                            "sha256": sha256_file(untouched_path),
                        },
                        "exact_locally_enumerated_id": row.get(
                            "exact_object_or_session_id"
                        ),
                        "reason": "locally enumerated metadata group with no contaminating exposure event",
                    }
                )

    replacement_path = root / "data/rehearsal_plan/mini_pilot_replacement_candidates.json"
    if replacement_path.is_file():
        document = load_json(replacement_path)
        for index, row in enumerate(document.get("candidates", [])):
            candidate = row.get("candidate_id", "")
            mapped = lecture_group_for_candidate(candidate)
            if not mapped:
                continue
            state = group_map.get(mapped)
            if state and state["eligibility"] == "CONDITIONAL_UNTOUCHED":
                rows.append(
                    {
                        "closure_root": mapped,
                        "enumeration_basis": "EXACT_LOCAL_REPLACEMENT_METADATA_RECORD",
                        "evidence": {
                            "locator": f"/candidates/{index}",
                            "path": replacement_path.relative_to(root).as_posix(),
                            "sha256": sha256_file(replacement_path),
                        },
                        "exact_locally_enumerated_id": candidate,
                        "reason": "exact local lecture metadata record not semantically exposed",
                    }
                )
    return sorted(rows, key=lambda row: (row["closure_root"], row["exact_locally_enumerated_id"]))


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("SCHEMA_VERSION_MISMATCH")
    if manifest.get("final_marker") != FINAL_READY:
        raise ManifestError("FINAL_MARKER_MISMATCH")
    if not manifest["scan"]["scanned_file_count"]:
        raise ManifestError("NO_FILES_SCANNED")
    if not manifest["alias_graph"]["components"]:
        raise ManifestError("EMPTY_ALIAS_GRAPH")
    if not manifest["exposure_events"]:
        raise ManifestError("EMPTY_EXPOSURE_EVENTS")
    touched = manifest["current_touched_groups"]
    if not touched:
        raise ManifestError("EMPTY_TOUCHED_GROUPS_CIRCULAR_DEFAULT_FORBIDDEN")
    if "EPIC:P23" not in {row["closure_root"] for row in touched}:
        raise ManifestError("P23_CONTAMINATION_NOT_DETECTED")
    alias_sets = [set(row["aliases"]) for row in manifest["alias_graph"]["components"]]
    required_alias_sets = (
        {"cand-042", "EC-NARA-CITY-UNDER-ICE", "NAID:2569752"},
        {"EPIC:P23", "P23", "P23_102"},
        {"CC4D:P01", "cc4d_p01_e08", "16_20"},
    )
    for required in required_alias_sets:
        if not any(required <= aliases for aliases in alias_sets):
            raise ManifestError(f"REQUIRED_ALIAS_CLOSURE_MISSING:{sorted(required)}")
    policy = manifest["untouched_eligibility_policy"]
    if set(policy["conditional_event_types"]) != CONDITIONAL_EVENTS:
        raise ManifestError("CONDITIONAL_POLICY_MISMATCH")
    if set(policy["contaminating_event_types"]) != CONTAMINATING_EVENTS:
        raise ManifestError("CONTAMINATION_POLICY_MISMATCH")
    replacement_roots = {
        row["closure_root"] for row in manifest["candidate_replacement_discovery"]
    }
    touched_roots = {row["closure_root"] for row in touched}
    if replacement_roots & touched_roots:
        raise ManifestError("TOUCHED_GROUP_OFFERED_AS_REPLACEMENT")
    if any(
        row["eligibility"] != "CONDITIONAL_UNTOUCHED"
        for row in manifest["candidate_replacement_discovery"]
        if "eligibility" in row
    ):
        raise ManifestError("NONCONDITIONAL_REPLACEMENT")


def build_manifest(root: Path) -> dict[str, Any]:
    files, inventory = scan_inventory(root)
    file_set = set(files)
    graph = extract_aliases(root, file_set)
    components = graph.components()
    scanned_exposures = classify_exposures(root, files, components)
    exposures = merge_exposures(scanned_exposures, explicit_structured_exposures(root))
    groups = summarize_groups(components, exposures)
    touched = [row for row in groups if row["touched"]]
    replacements = candidate_replacements(root, groups)
    manifest = {
        "alias_graph": {
            "component_count": len(components),
            "components": components,
            "normalization_rule": (
                "Aliases are linked only by exact local structured evidence; "
                "closures propagate at participant/person/production level."
            ),
        },
        "candidate_replacement_discovery": replacements,
        "created_date": CREATED_DATE,
        "current_touched_groups": touched,
        "exposure_events": exposures,
        "final_marker": FINAL_READY,
        "manifest_id": MANIFEST_ID,
        "scan": inventory,
        "schema_version": SCHEMA_VERSION,
        "untouched_eligibility_policy": {
            "conditional_event_types": sorted(
                CONDITIONAL_EVENTS, key=EVENT_ORDER.index
            ),
            "contaminating_event_types": sorted(
                CONTAMINATING_EVENTS, key=EVENT_ORDER.index
            ),
            "decision_rule": (
                "metadata catalog inspection, rights/access preflight, and "
                "failed zero-byte probes may remain CONDITIONAL; any media "
                "content, index/model/candidate output, semantic prompt, human "
                "prescreen, or opened annotation contaminates the full alias closure"
            ),
            "event_vocabulary": list(EVENT_ORDER),
            "replacement_discovery_rule": (
                "Only exact groups already enumerated in local metadata may be "
                "reported, and only when their closure has no contaminating event."
            ),
        },
    }
    validate_manifest(manifest)
    return manifest


def render_markdown(manifest: dict[str, Any]) -> str:
    touched = manifest["current_touched_groups"]
    replacements = manifest["candidate_replacement_discovery"]
    counts = Counter(
        event["event_type"] for event in manifest["exposure_events"]
    )
    lines = [
        "# Source exposure alias manifest v1",
        "",
        f"- Final marker: `{manifest['final_marker']}`",
        f"- Date: `{manifest['created_date']}`",
        f"- Scanned files: {manifest['scan']['scanned_file_count']}",
        f"- Scanned bytes: {manifest['scan']['scanned_total_bytes']}",
        f"- Alias closures: {manifest['alias_graph']['component_count']}",
        f"- Exposure evidence rows: {len(manifest['exposure_events'])}",
        f"- Currently touched closures: {len(touched)}",
        "",
        "## Safety boundary",
        "",
        (
            "The generator scans only allowlisted bounded "
            "text/JSON/CSV/prompt/log/index/manifest files. It excludes media, "
            "model, annotation, and annotations directories and never opens "
            "media or semantic annotation bodies."
        ),
        "",
        "## Eligibility policy",
        "",
        "- Conditional only: `metadata_catalog_only`, `rights/access_preflight`, `failed_zero_byte_probe`.",
        (
            "- Contaminating: `media_acquired`, `media_indexed`, "
            "`learned_model_ranked`, `candidate_mined`, "
            "`semantic_prompt_exposed`, `human_prescreened`, "
            "`annotation_opened`."
        ),
        "- Any contaminating event applies to the full alias closure.",
        "",
        "## Event counts",
        "",
        "| Event | Evidence rows |",
        "|---|---:|",
    ]
    for event in EVENT_ORDER:
        lines.append(f"| `{event}` | {counts[event]} |")
    lines.extend(
        [
            "",
            "## Current touched closures",
            "",
            "| Closure root | Event types | Alias sample |",
            "|---|---|---|",
        ]
    )
    for row in touched:
        aliases = ", ".join(f"`{value}`" for value in row["aliases"][:6])
        events = ", ".join(f"`{value}`" for value in row["event_types"])
        lines.append(f"| `{row['closure_root']}` | {events} | {aliases} |")
    lines.extend(
        [
            "",
            "## Exact local replacement discovery",
            "",
            "These are discovery results, not authorization. They are limited to exact locally enumerated metadata groups with no detected contaminating event.",
            "",
            "| Closure root | Exact local ID | Basis |",
            "|---|---|---|",
        ]
    )
    for row in replacements:
        lines.append(
            f"| `{row['closure_root']}` | `{row['exact_locally_enumerated_id']}` | "
            f"`{row['enumeration_basis']}` |"
        )
    lines.extend(
        [
            "",
            "## Required alias checks",
            "",
            "- `cand-042`, `EC-NARA-CITY-UNDER-ICE`, and `NAID:2569752` share one evidence-backed closure.",
            "- `P23`, `P23_102`, and all detected P23 derivatives close to `EPIC:P23`.",
            "- CaptainCook4D recording and person/environment aliases close at person level.",
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


def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
