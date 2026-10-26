"""Frozen, deterministic JSON index loading for the AV-TRACE MVP backend."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from av_trace.util import load_json, sha256_json

INDEX_SCHEMA_VERSION = "1.0.0"
INDEX_FORMAT = "av_trace_mvp.index.v1"
BACKEND_MANIFEST_VERSION = "1.0.0"
DEFAULT_BACKEND_VERSION = "fixed-mvp-v1"
DEFAULT_INDEX_VERSION = "lexical-index-v1"
TOKENIZER_VERSION = "unicode-alnum-v1"
RANKING_ALGORITHM = "lexical-overlap-v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SHA_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_MODALITIES = {"vision", "speech", "ambient"}
_TRANSCRIPT_SOURCES = {"asr", "subtitle"}


class IndexFormatError(ValueError):
    """Fail-closed error raised for malformed or unfrozen backend artifacts."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise IndexFormatError(code, message)


def _interval(value: Any, record_id: str) -> dict[str, float]:
    if isinstance(value, list):
        _require(len(value) == 1, "INDEX_INTERVAL", f"{record_id} must have one atomic interval.")
        value = value[0]
    _require(isinstance(value, dict), "INDEX_INTERVAL", f"{record_id} has no interval object.")
    start = value.get("start_s")
    end = value.get("end_s")
    _require(
        isinstance(start, (int, float))
        and not isinstance(start, bool)
        and isinstance(end, (int, float))
        and not isinstance(end, bool)
        and 0 <= start < end,
        "INDEX_INTERVAL",
        f"{record_id} interval must satisfy 0 <= start_s < end_s.",
    )
    return {"start_s": float(start), "end_s": float(end)}


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(value[key]) for key in sorted(value))
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return ""


def tokenize(text: str) -> tuple[str, ...]:
    """Return the frozen lexical tokenization used by all search tools."""
    return tuple(token.casefold() for token in _TOKEN_RE.findall(text))


@dataclass(frozen=True)
class IndexRecord:
    record_id: str
    modality: str
    interval: dict[str, float]
    payload: dict[str, Any]
    search_text: str
    preview: str
    route_evidence_ids: tuple[str, ...]
    is_distractor: bool
    family_id: str | None = None
    asset_id: str | None = None
    speaker: str | None = None
    transcript_sources: tuple[str, ...] = ()

    @property
    def result_id(self) -> str:
        return "ptr." + sha256_json({"record_id": self.record_id}).split(":", 1)[1]

    def applies_to(self, family_id: str, asset_id: str) -> bool:
        return (
            (self.family_id is None or self.family_id == family_id)
            and (self.asset_id is None or self.asset_id == asset_id)
        )


def normalize_record(raw: Mapping[str, Any]) -> IndexRecord:
    """Normalize the documented MVP record format and a few harmless aliases."""
    _require(isinstance(raw, Mapping), "INDEX_RECORD", "Every index record must be an object.")
    record_id = raw.get("record_id") or raw.get("evidence_id") or raw.get("event_id")
    _require(isinstance(record_id, str) and bool(_ID_RE.fullmatch(record_id)), "INDEX_ID", "Invalid record_id.")
    modality = raw.get("modality")
    _require(modality in _MODALITIES, "INDEX_MODALITY", f"{record_id} has an invalid modality.")
    interval = _interval(raw.get("interval", raw.get("intervals")), record_id)
    payload = raw.get("payload")
    if payload is None:
        payload = {}
        for key in ("text", "description", "label", "observation", "words", "speaker"):
            if key in raw:
                payload[key] = deepcopy(raw[key])
    _require(isinstance(payload, dict), "INDEX_PAYLOAD", f"{record_id} payload must be an object.")

    route_ids = raw.get("route_evidence_ids")
    if route_ids is None:
        route_ids = raw.get("evidence_ids")
    if route_ids is None:
        derived = raw.get("derived_from_evidence_ids", [])
        primary = raw.get("evidence_id")
        route_ids = ([primary] if isinstance(primary, str) else []) + list(derived)
    _require(
        isinstance(route_ids, list)
        and all(isinstance(item, str) and _ID_RE.fullmatch(item) for item in route_ids)
        and len(route_ids) == len(set(route_ids)),
        "INDEX_ROUTE",
        f"{record_id} route_evidence_ids must be a unique ID array.",
    )
    is_distractor = raw.get("is_distractor", False)
    _require(isinstance(is_distractor, bool), "INDEX_RECORD", f"{record_id} is_distractor must be boolean.")
    _require(
        bool(route_ids) or is_distractor,
        "INDEX_ROUTE",
        f"{record_id} must declare every evidence route, unless explicitly marked as a distractor.",
    )

    search_text = raw.get("search_text")
    if search_text is None:
        search_text = _flatten_text(payload)
    _require(isinstance(search_text, str) and bool(search_text.strip()), "INDEX_TEXT", f"{record_id} has no search text.")
    preview = raw.get("preview", search_text)
    _require(isinstance(preview, str), "INDEX_TEXT", f"{record_id} preview must be a string.")
    preview = preview[:1000]

    speaker = raw.get("speaker")
    if speaker is None and isinstance(payload.get("speaker"), str):
        speaker = payload["speaker"]
    _require(speaker is None or isinstance(speaker, str), "INDEX_RECORD", f"{record_id} speaker must be a string or null.")

    sources = raw.get("transcript_sources")
    if sources is None:
        source = raw.get("transcript_source")
        sources = [source] if source is not None else (["asr"] if modality == "speech" else [])
    _require(
        isinstance(sources, list)
        and len(sources) == len(set(sources))
        and set(sources) <= _TRANSCRIPT_SOURCES,
        "INDEX_TRANSCRIPT",
        f"{record_id} transcript_sources are invalid.",
    )
    if modality != "speech":
        _require(not sources, "INDEX_TRANSCRIPT", f"{record_id} is non-speech and cannot expose transcript sources.")

    family_id = raw.get("family_id")
    asset_id = raw.get("asset_id")
    for field, value in (("family_id", family_id), ("asset_id", asset_id)):
        _require(value is None or (isinstance(value, str) and _ID_RE.fullmatch(value)), "INDEX_ID", f"{record_id} has invalid {field}.")

    return IndexRecord(
        record_id=record_id,
        modality=modality,
        interval=interval,
        payload=deepcopy(payload),
        search_text=search_text,
        preview=preview,
        route_evidence_ids=tuple(route_ids),
        is_distractor=is_distractor,
        family_id=family_id,
        asset_id=asset_id,
        speaker=speaker,
        transcript_sources=tuple(sources),
    )


class FixedIndex:
    """An immutable lexical index with stable IDs and deterministic tie-breaking."""

    def __init__(
        self,
        records: Iterable[IndexRecord],
        *,
        index_version: str = DEFAULT_INDEX_VERSION,
        content_hash: str | None = None,
    ) -> None:
        materialized = tuple(records)
        ids = [record.record_id for record in materialized]
        _require(len(ids) == len(set(ids)), "INDEX_DUPLICATE", "record_id values must be globally unique.")
        self.records = tuple(sorted(materialized, key=lambda record: record.record_id))
        self.index_version = index_version
        document = self.to_document()
        self.index_hash = content_hash or sha256_json(document)
        _require(bool(_SHA_RE.fullmatch(self.index_hash)), "INDEX_HASH", "Invalid index hash.")

    @classmethod
    def from_records(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        index_version: str = DEFAULT_INDEX_VERSION,
    ) -> "FixedIndex":
        return cls((normalize_record(item) for item in records), index_version=index_version)

    @classmethod
    def from_document(
        cls,
        document: Any,
        *,
        index_version: str = DEFAULT_INDEX_VERSION,
        content_hash: str | None = None,
    ) -> "FixedIndex":
        if isinstance(document, list):
            records = document
        else:
            _require(isinstance(document, dict), "INDEX_DOCUMENT", "Index JSON must be an object or record array.")
            if "format" in document:
                _require(document["format"] == INDEX_FORMAT, "INDEX_VERSION", "Unsupported index format.")
            if "schema_version" in document:
                _require(document["schema_version"] == INDEX_SCHEMA_VERSION, "INDEX_VERSION", "Unsupported index schema version.")
            records = document.get("records")
        _require(isinstance(records, list), "INDEX_DOCUMENT", "Index document must contain a records array.")
        raw_hash = content_hash or sha256_json(document)
        return cls((normalize_record(item) for item in records), index_version=index_version, content_hash=raw_hash)

    @classmethod
    def load(cls, path: str | Path, *, index_version: str = DEFAULT_INDEX_VERSION) -> "FixedIndex":
        document = load_json(path)
        return cls.from_document(document, index_version=index_version, content_hash=sha256_json(document))

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": INDEX_SCHEMA_VERSION,
            "format": INDEX_FORMAT,
            "records": [
                {
                    "record_id": record.record_id,
                    "family_id": record.family_id,
                    "asset_id": record.asset_id,
                    "modality": record.modality,
                    "interval": record.interval,
                    "payload": record.payload,
                    "search_text": record.search_text,
                    "preview": record.preview,
                    "route_evidence_ids": list(record.route_evidence_ids),
                    "is_distractor": record.is_distractor,
                    "speaker": record.speaker,
                    "transcript_sources": list(record.transcript_sources),
                }
                for record in self.records
            ],
        }

    def for_family(self, family_id: str, asset_id: str) -> tuple[IndexRecord, ...]:
        return tuple(record for record in self.records if record.applies_to(family_id, asset_id))

    def for_asset(self, asset_id: str) -> tuple[IndexRecord, ...]:
        """Return the common source-level candidate universe for every family."""

        return tuple(record for record in self.records if record.asset_id in {None, asset_id})

    def search(
        self,
        *,
        records: Iterable[IndexRecord],
        modality: str,
        query: str,
        interval: Mapping[str, float],
        top_k: int,
        excluded_result_ids: Iterable[str] = (),
        speaker_hint: str | None = None,
    ) -> list[tuple[IndexRecord, float]]:
        query_tokens = Counter(tokenize(query))
        excluded = set(excluded_result_ids)
        query_phrase = " ".join(tokenize(query))
        generic_tokens = {
            "vision": {"visual"},
            "speech": {"speech"},
            "ambient": {"ambient"},
        }[modality]
        ranked: list[tuple[IndexRecord, float]] = []
        for record in records:
            if record.modality != modality or record.result_id in excluded:
                continue
            if record.interval["end_s"] <= interval["start_s"] or record.interval["start_s"] >= interval["end_s"]:
                continue
            document_tokens = Counter(tokenize(record.search_text))
            overlap = sum(min(count, document_tokens[token]) for token, count in query_tokens.items())
            if overlap == 0:
                if not generic_tokens.intersection(query_tokens):
                    continue
                score = 0.001
            else:
                score = overlap / max(1, sum(query_tokens.values()))
            normalized_document = " ".join(tokenize(record.search_text))
            if query_phrase and query_phrase in normalized_document:
                score += 0.25
            if speaker_hint and record.speaker and speaker_hint.casefold() in record.speaker.casefold():
                score += 0.1
            ranked.append((record, round(score, 6)))
        ranked.sort(
            key=lambda item: (
                -item[1],
                item[0].interval["start_s"],
                item[0].interval["end_s"],
                item[0].result_id,
            )
        )
        return ranked[:top_k]


@dataclass(frozen=True)
class BackendManifest:
    document: dict[str, Any]
    root: Path | None = None

    @property
    def backend_version(self) -> str:
        return self.document["backend_version"]

    @property
    def index_version(self) -> str:
        return self.document["index_version"]

    @property
    def index_hash(self) -> str:
        return self.document["index_hash"]

    @property
    def manifest_hash(self) -> str:
        return sha256_json(self.document)

    @property
    def tool_costs(self) -> dict[str, float]:
        return deepcopy(self.document["tool_costs"])

    @classmethod
    def for_index(
        cls,
        index: FixedIndex,
        tool_costs: Mapping[str, float],
        *,
        backend_version: str = DEFAULT_BACKEND_VERSION,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> "BackendManifest":
        document = {
            "schema_version": BACKEND_MANIFEST_VERSION,
            "backend_version": backend_version,
            "tool_api_version": "0.2.0",
            "index_version": index.index_version,
            "deterministic": True,
            "hash_algorithm": "sha256-canonical-json-v1",
            "ranking": {
                "algorithm": RANKING_ALGORITHM,
                "tokenizer": TOKENIZER_VERSION,
                "score_precision": 6,
                "tie_breakers": ["score_desc", "start_s_asc", "end_s_asc", "result_id_asc"],
            },
            "tool_costs": dict(tool_costs),
            "artifacts": artifacts or [{"role": "index", "path": "index.json", "sha256": index.index_hash}],
            "index_hash": index.index_hash,
            "record_count": len(index.records),
        }
        return cls(document)

    @classmethod
    def load(cls, path: str | Path) -> "BackendManifest":
        source = Path(path)
        document = load_json(source)
        schema_path = Path(__file__).resolve().parents[2] / "mvp/schemas/backend_manifest_schema.json"
        schema = load_json(schema_path)
        errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda error: list(error.path))
        if errors:
            first = errors[0]
            pointer = "/" + "/".join(str(part) for part in first.absolute_path)
            raise IndexFormatError("MANIFEST_SCHEMA", f"{pointer}: {first.message}")
        return cls(document, source.parent)

    def verify(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "mvp/schemas/backend_manifest_schema.json"
        errors = sorted(
            Draft202012Validator(load_json(schema_path)).iter_errors(self.document),
            key=lambda error: list(error.path),
        )
        if errors:
            first = errors[0]
            pointer = "/" + "/".join(str(part) for part in first.absolute_path)
            raise IndexFormatError("MANIFEST_SCHEMA", f"{pointer}: {first.message}")
        _require(self.document["deterministic"] is True, "MANIFEST_DETERMINISM", "Manifest must freeze deterministic=true.")
        index_artifacts = [item for item in self.document["artifacts"] if item["role"] == "index"]
        _require(len(index_artifacts) == 1, "MANIFEST_INDEX", "Manifest must declare exactly one index artifact.")
        _require(index_artifacts[0]["sha256"] == self.index_hash, "MANIFEST_INDEX", "index_hash must equal the index artifact hash.")
        _require(self.document["record_count"] >= 1, "MANIFEST_INDEX", "record_count must be positive.")
        if self.root is None:
            return
        for artifact in self.document["artifacts"]:
            relative = Path(artifact["path"])
            _require(not relative.is_absolute() and ".." not in relative.parts, "MANIFEST_PATH", "Artifact paths must stay below the manifest directory.")
            target = self.root / relative
            _require(target.is_file(), "MANIFEST_MISSING", f"Missing artifact {artifact['path']}.")
            if target.suffix.lower() == ".json":
                actual = sha256_json(load_json(target))
            else:
                import hashlib

                actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            _require(actual == artifact["sha256"], "MANIFEST_HASH", f"Hash mismatch for {artifact['path']}.")


@dataclass(frozen=True)
class GeneratedCorpus:
    manifest: BackendManifest
    index: FixedIndex
    families: tuple[dict[str, Any], ...]

    def family(self, family_id: str) -> dict[str, Any]:
        matches = [family for family in self.families if family.get("family_id") == family_id]
        _require(len(matches) == 1, "CORPUS_FAMILY", f"Expected exactly one family named {family_id}.")
        return deepcopy(matches[0])


def _json_artifact(path: Path, root: Path, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_json(load_json(path)),
    }


def _binary_artifact(path: Path, root: Path, role: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": "sha256:" + digest.hexdigest(),
    }


def build_generated_backend(root: str | Path) -> GeneratedCorpus:
    """Build and persist the frozen backend bundle from corpus-native artifacts.

    Index content is derived from timelines, transcripts, audio-event labels,
    and the standalone evidence inventory. Family annotations are used only to
    bind records to families and declare intervention routes; they never supply
    search text, payloads, intervals, or modality.
    """

    root_path = Path(root)
    index_path = root_path / "corpus_index.json"
    _require(index_path.is_file(), "CORPUS_MISSING", f"Missing {index_path}.")
    corpus = load_json(index_path)
    _require(
        isinstance(corpus, dict)
        and corpus.get("schema_version") == "1.0"
        and isinstance(corpus.get("families"), list)
        and isinstance(corpus.get("sources"), list),
        "CORPUS_INDEX",
        "Unsupported synthetic corpus_index.json.",
    )
    sources = {item["source_id"]: item for item in corpus["sources"]}
    source_payloads: dict[str, dict[str, Any]] = {}
    source_artifacts: list[dict[str, Any]] = []
    for source_id in sorted(sources):
        payload: dict[str, Any] = {}
        for key, directory, role in (
            ("timeline", "timelines", "event_timeline"),
            ("evidence", "evidence", "evidence_inventory"),
            ("transcript", "transcripts", "transcript"),
            ("audio_events", "audio_events", "audio_events"),
        ):
            path = root_path / directory / f"{source_id}.json"
            _require(path.is_file(), "CORPUS_MISSING", f"Missing documented {key} file for {source_id}.")
            payload[key] = load_json(path)
            source_artifacts.append(_json_artifact(path, root_path, role))
        manifest_path = root_path / sources[source_id]["manifest_path"]
        media_path = root_path / sources[source_id]["media_path"]
        _require(manifest_path.is_file(), "CORPUS_MISSING", f"Missing manifest for {source_id}.")
        _require(media_path.is_file(), "CORPUS_MISSING", f"Missing media for {source_id}.")
        source_artifacts.append(_json_artifact(manifest_path, root_path, "acquisition_manifest"))
        source_artifacts.append(_binary_artifact(media_path, root_path, "source_media"))
        source_payloads[source_id] = payload

    families: list[dict[str, Any]] = []
    family_paths: list[Path] = []
    records: list[dict[str, Any]] = []
    indexed_source_events: set[tuple[str, str]] = set()
    for summary in sorted(corpus["families"], key=lambda item: item["family_id"]):
        family_path = root_path / summary["path"]
        _require(family_path.is_file(), "CORPUS_MISSING", f"Missing family artifact {summary['path']}.")
        family = load_json(family_path)
        source_id = summary["source_id"]
        _require(source_id in sources, "CORPUS_INDEX", f"Unknown source {source_id}.")
        payloads = source_payloads[source_id]
        timeline = {item["event_id"]: item for item in payloads["timeline"].get("events", [])}
        evidence_meta = {item["evidence_id"]: item for item in payloads["evidence"].get("evidence", [])}
        transcripts = {item["segment_id"]: item for item in payloads["transcript"].get("segments", [])}
        audio = {item["event_id"]: item for item in payloads["audio_events"].get("events", [])}
        graph_ids = {
            item["evidence_id"] for item in family["claim_evidence_graph"]["evidence_units"]
        }
        _require(graph_ids <= set(evidence_meta), "CORPUS_INDEX", f"Family {family['family_id']} evidence is absent from evidence inventory.")
        for event_id in sorted(evidence_meta):
            evidence_item = evidence_meta[event_id]
            source_event = (source_id, event_id)
            if source_event in indexed_source_events:
                continue
            indexed_source_events.add(source_event)
            timeline_event = timeline.get(event_id)
            _require(timeline_event is not None, "CORPUS_INDEX", f"Missing timeline event {event_id}.")
            modality = evidence_item.get("modality")
            _require(modality in _MODALITIES, "CORPUS_INDEX", f"Invalid modality for {event_id}.")
            interval = _interval(evidence_item.get("intervals"), event_id)
            _require(
                interval == _interval(
                    {"start_s": timeline_event.get("start_s"), "end_s": timeline_event.get("end_s")},
                    event_id,
                )
                and modality == timeline_event.get("modality"),
                "CORPUS_INDEX",
                f"Timeline/evidence disagreement for {event_id}.",
            )
            transcript = transcripts.get(event_id)
            audio_event = audio.get(event_id)
            if modality == "speech":
                _require(transcript is not None, "CORPUS_INDEX", f"Missing transcript for {event_id}.")
            if modality in {"speech", "ambient"}:
                _require(audio_event is not None, "CORPUS_INDEX", f"Missing audio event for {event_id}.")
            native_text = [
                evidence_item.get("observation"),
                timeline_event.get("label"),
                transcript.get("text") if transcript else None,
                audio_event.get("class") if audio_event else None,
            ]
            generic_terms = {
                "vision": "visual visible shape symbol arrow appeared shown",
                "speech": "speech spoken says code instruction announcement report status units bin route",
                "ambient": "ambient sound audio bell pulse machine motor click confirmation chime",
            }[modality]
            search_text = " ".join(
                item for item in native_text if isinstance(item, str) and item.strip()
            )
            search_text = f"{generic_terms} {search_text}"
            record_payload: dict[str, Any] = {
                "description": timeline_event["label"],
            }
            if transcript:
                record_payload["text"] = transcript["text"]
            if audio_event:
                record_payload["audio_event"] = audio_event["class"]
                record_payload["audio_parameters"] = audio_event.get("audio_parameters", {})
            opaque_record_id = (
                "rec."
                + sha256_json(
                    {
                        "asset_id": family["source"]["asset_id"],
                        "event_id": event_id,
                    }
                ).split(":", 1)[1][:32]
            )
            records.append(
                {
                    "record_id": opaque_record_id,
                    "family_id": None,
                    "asset_id": family["source"]["asset_id"],
                    "modality": modality,
                    "interval": interval,
                    "payload": record_payload,
                    "search_text": search_text,
                    "preview": (
                        f"{modality} candidate at "
                        f"{interval['start_s']:.1f}-{interval['end_s']:.1f}s"
                    ),
                    # Route identity comes from the standalone generated
                    # evidence inventory. The graph is checked for coverage,
                    # but never supplies index payload/search content.
                    "route_evidence_ids": [event_id],
                    "is_distractor": False,
                    "speaker": None,
                    "transcript_sources": ["asr"] if transcript else [],
                }
            )
        families.append(family)
        family_paths.append(family_path)

    fixed_index = FixedIndex.from_records(
        records,
        index_version=f"synthetic-{corpus.get('generator_version', 'v1')}",
    )
    costs = families[0]["episodes"][0]["budget"]["tool_costs"]
    _require(
        all(episode["budget"]["tool_costs"] == costs for family in families for episode in family["episodes"]),
        "CORPUS_COSTS",
        "Synthetic families do not share one frozen cost schedule.",
    )
    backend_version = "synthetic-fixed-v1"
    normalized: list[dict[str, Any]] = []
    for family in families:
        item = deepcopy(family)
        for episode in item["episodes"]:
            episode["backend"]["backend_version"] = backend_version
            episode["backend"]["index_hash"] = fixed_index.index_hash
        normalized.append(item)

    index_document = fixed_index.to_document()
    frozen_families = normalized
    index_output = root_path / "backend_index.json"
    families_output = root_path / "backend_families.json"
    index_output.write_text(
        json.dumps(index_document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    families_output.write_text(
        json.dumps(frozen_families, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    artifacts = [
        _json_artifact(index_output, root_path, "index"),
        _json_artifact(families_output, root_path, "family"),
        _json_artifact(index_path, root_path, "corpus_index"),
        *source_artifacts,
    ]
    manifest = BackendManifest.for_index(
        fixed_index,
        costs,
        backend_version=backend_version,
        artifacts=artifacts,
    )
    manifest_path = root_path / "backend_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    persisted = BackendManifest.load(manifest_path)
    persisted.verify()
    return GeneratedCorpus(persisted, fixed_index, tuple(deepcopy(frozen_families)))


def load_generated(root: str | Path = "mvp/generated") -> GeneratedCorpus:
    """Load a frozen backend bundle or adapt the sibling synthetic corpus."""
    root_path = Path(root)
    if not (root_path / "backend_manifest.json").is_file():
        return _load_synthetic_generated(root_path)
    manifest = BackendManifest.load(root_path / "backend_manifest.json")
    manifest.verify()
    index_artifact = next(item for item in manifest.document["artifacts"] if item["role"] == "index")
    index_document = load_json(root_path / index_artifact["path"])
    index = FixedIndex.from_document(
        index_document,
        index_version=manifest.index_version,
        content_hash=manifest.index_hash,
    )
    _require(len(index.records) == manifest.document["record_count"], "MANIFEST_INDEX", "record_count does not match the index.")
    families: list[dict[str, Any]] = []
    for artifact in manifest.document["artifacts"]:
        if artifact["role"] != "family":
            continue
        document = load_json(root_path / artifact["path"])
        if isinstance(document, list):
            families.extend(document)
        elif isinstance(document, dict) and isinstance(document.get("families"), list):
            families.extend(document["families"])
        else:
            families.append(document)
    _require(bool(families), "CORPUS_FAMILY", "Manifest must include at least one family artifact.")
    ids = [family.get("family_id") for family in families]
    _require(all(isinstance(item, str) for item in ids) and len(ids) == len(set(ids)), "CORPUS_FAMILY", "Family IDs must be unique.")
    return GeneratedCorpus(manifest, index, tuple(deepcopy(families)))


def _load_synthetic_generated(root: Path) -> GeneratedCorpus:
    """Build the documented synthetic layout into a persisted frozen bundle."""
    candidates = [root / "corpus_index.json", root / "full/corpus_index.json", root / "quick/corpus_index.json"]
    index_path = next((path for path in candidates if path.is_file()), None)
    _require(index_path is not None, "MANIFEST_MISSING", f"No backend_manifest.json or corpus_index.json below {root}.")
    return build_generated_backend(index_path.parent)


def load_index(path: str | Path, *, index_version: str = DEFAULT_INDEX_VERSION) -> FixedIndex:
    """Public convenience wrapper for loading one canonical index document."""
    return FixedIndex.load(path, index_version=index_version)


def load_backend_manifest(path: str | Path) -> BackendManifest:
    """Public convenience wrapper for loading and verifying a manifest."""
    manifest = BackendManifest.load(path)
    manifest.verify()
    return manifest
