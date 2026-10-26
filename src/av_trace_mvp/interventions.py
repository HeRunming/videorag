"""Pilot-0 intervention isolation and deterministic restoration state machine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from av_trace.util import sha256_json

from .index import FixedIndex, IndexFormatError, IndexRecord


class InterventionError(IndexFormatError):
    """Raised when a family would violate the frozen intervention contract."""


def _fail(code: str, message: str) -> None:
    raise InterventionError(code, message)


def _channel_modalities(channel: str) -> set[str]:
    return {
        "visual": {"vision"},
        "speech": {"speech"},
        "ambient": {"ambient"},
    }.get(channel, set())


def _reachable_ses(family: dict[str, Any], accessible: set[str]) -> set[str]:
    return {
        item["set_id"]
        for item in family["claim_evidence_graph"]["accepted_sufficient_sets"]
        if set(item["evidence_ids"]) <= accessible
    }


@dataclass(frozen=True)
class InterventionSnapshot:
    accessible_evidence_ids: tuple[str, ...]
    enabled_channels: tuple[str, ...]
    restored: bool

    @property
    def state_hash(self) -> str:
        return sha256_json(
            {
                "accessible_evidence_ids": list(self.accessible_evidence_ids),
                "enabled_channels": list(self.enabled_channels),
                "restored": self.restored,
            }
        )


class InterventionRuntime:
    """Mutable state whose only legal transition is the registered restoration."""

    def __init__(self, family: dict[str, Any], state_role: str, index: FixedIndex) -> None:
        self.family = deepcopy(family)
        episodes = family.get("episodes")
        if not isinstance(episodes, list) or [item.get("state_role") for item in episodes] != [
            "CLEAN",
            "BLOCKED",
            "RESTORED",
        ]:
            _fail("INTERVENTION_FAMILY", "Family episodes must be exactly CLEAN, BLOCKED, RESTORED in order.")
        by_role = {episode["state_role"]: episode for episode in episodes}
        if state_role not in by_role:
            _fail("INTERVENTION_STATE", f"Unknown state role {state_role}.")
        self.episode = deepcopy(by_role[state_role])
        self._clean = deepcopy(by_role["CLEAN"])
        self._blocked = deepcopy(by_role["BLOCKED"])
        self._restored_episode = deepcopy(by_role["RESTORED"])
        self._validate(index)

        initial = self.episode["initial_state"]
        self._accessible = set(initial["accessible_evidence_ids"])
        self._enabled = set(initial["enabled_channels"])
        self._initial_accessible = tuple(initial["accessible_evidence_ids"])
        self._initial_enabled = tuple(initial["enabled_channels"])
        self._family_evidence = {
            item["evidence_id"]
            for item in family["claim_evidence_graph"]["evidence_units"]
        }
        self._restore = next(
            (item for item in self.episode["interventions"] if item["phase"] == "restoration"),
            None,
        )
        self._restored = state_role != "RESTORED"

    @property
    def manifest_hash(self) -> str:
        return sha256_json(
            {
                "family_id": self.family["family_id"],
                "mechanism": self.family["intervention_mechanism"],
                "state_role": self.episode["state_role"],
                "initial_state": {
                    "accessible_evidence_ids": list(self._initial_accessible),
                    "enabled_channels": list(self._initial_enabled),
                },
                "interventions": self.episode["interventions"],
            }
        )

    @property
    def snapshot(self) -> InterventionSnapshot:
        ordered_accessible = tuple(
            item
            for item in self._clean["initial_state"]["accessible_evidence_ids"]
            if item in self._accessible
        )
        ordered_channels = tuple(
            item for item in self._clean["initial_state"]["enabled_channels"] if item in self._enabled
        )
        return InterventionSnapshot(ordered_accessible, ordered_channels, self._restored)

    def _validate(self, index: FixedIndex) -> None:
        clean, blocked, restored = self._clean, self._blocked, self._restored_episode
        for field in ("backend", "budget"):
            if clean[field] != blocked[field] or clean[field] != restored[field]:
                _fail("INTERVENTION_ISOLATION", f"{field} differs across matched states.")
        if blocked["initial_state"] != restored["initial_state"]:
            _fail("RESTORATION_START", "RESTORED must begin byte/state-identically to BLOCKED.")
        if clean["interventions"]:
            _fail("INTERVENTION_CLEAN", "CLEAN may not contain interventions.")

        graph = self.family["claim_evidence_graph"]
        evidence = {item["evidence_id"]: item for item in graph["evidence_units"]}
        groups = {item["group_id"]: item for item in graph["necessity_groups"]}
        family_records = index.for_asset(self.family["source"]["asset_id"])
        if not family_records:
            _fail("INDEX_COVERAGE", "No index records apply to this family.")
        covered = {
            evidence_id
            for record in family_records
            for evidence_id in record.route_evidence_ids
            if evidence_id in evidence
        }
        missing = set(evidence) - covered
        if missing:
            _fail("INDEX_COVERAGE", f"Graph evidence has no declared index route: {sorted(missing)}.")

        blocked_ops = [item for item in blocked["interventions"] if item["phase"] == "blocked"]
        restore_ops = [item for item in restored["interventions"] if item["phase"] == "restoration"]
        if len(blocked_ops) != 1 or len(restore_ops) != 1:
            _fail("INTERVENTION_COUNT", "BLOCKED needs one block and RESTORED needs one restoration.")
        block, restore = blocked_ops[0], restore_ops[0]
        restored_blocks = [item for item in restored["interventions"] if item["phase"] == "blocked"]
        if restored_blocks != blocked_ops:
            _fail("RESTORATION_START", "RESTORED must carry the exact BLOCKED operation.")
        if restore["restoration"]["restores_intervention_id"] != block["intervention_id"]:
            _fail("RESTORATION_TARGET", "Restoration must name the blocked intervention.")
        if restore["affected_evidence_ids"] != block["affected_evidence_ids"] or restore["affected_channel"] != block["affected_channel"]:
            _fail("RESTORATION_EXACT", "Restoration must reverse exactly the registered block.")
        trigger = restore["restoration"]
        if trigger["trigger_type"] not in {"fixed_call_index", "get_channel_status"}:
            _fail("RESTORATION_TRIGGER", "Restoration trigger must be fixed_call_index or get_channel_status.")
        if trigger["trigger_type"] == "fixed_call_index":
            value = trigger["trigger_value"]
            if not isinstance(value, int) or value < 0 or value >= restored["budget"]["max_steps"]:
                _fail("RESTORATION_TRIGGER", "fixed_call_index must be within the episode step budget.")
        elif trigger["trigger_value"] is not None:
            _fail("RESTORATION_TRIGGER", "get_channel_status trigger_value must be null.")

        clean_access = set(clean["initial_state"]["accessible_evidence_ids"])
        blocked_access = set(blocked["initial_state"]["accessible_evidence_ids"])
        removed = clean_access - blocked_access
        if not blocked_access <= clean_access:
            _fail("INTERVENTION_ISOLATION", "BLOCKED may not add evidence.")
        mechanism = self.family["intervention_mechanism"]
        if block["mechanism"] != mechanism or restore["mechanism"] != mechanism:
            _fail("INTERVENTION_MECHANISM", "All operations must use the family mechanism.")
        declared = set(block["affected_evidence_ids"])
        if mechanism == "necessity_group_withholding":
            group = groups.get(block["affected_necessity_group_id"])
            if group is None:
                _fail("INTERVENTION_GROUP", "Withholding must reference a declared necessity group.")
            members = set(group["member_evidence_ids"])
            if declared != members or removed != members:
                _fail("INTERVENTION_CLOSURE", "Withholding must remove every and only necessity-group member.")
            if block["affected_channel"] is not None:
                _fail("INTERVENTION_ISOLATION", "Necessity withholding cannot mutate a channel.")
            if clean["initial_state"]["enabled_channels"] != blocked["initial_state"]["enabled_channels"]:
                _fail("INTERVENTION_ISOLATION", "Necessity withholding changed enabled channels.")
            relevant = [
                item
                for item in graph["accepted_sufficient_sets"]
                if set(group["claim_ids"]) <= set(item["claim_ids"])
            ]
            if not relevant or any(not members.intersection(item["evidence_ids"]) for item in relevant):
                _fail("INTERVENTION_CLOSURE", "Necessity group does not close every accepted evidence route.")
        elif mechanism == "modality_channel_outage":
            channel = block["affected_channel"]
            if channel not in {"visual", "speech", "ambient"} or block["affected_necessity_group_id"] is not None:
                _fail("INTERVENTION_CHANNEL", "Channel outage must name one modality channel and no group.")
            expected_removed = {
                evidence_id
                for evidence_id in clean_access
                if evidence[evidence_id]["modality"] in _channel_modalities(channel)
            }
            if declared != expected_removed or removed != expected_removed:
                _fail("INTERVENTION_CLOSURE", "Channel outage must remove every and only record on its route.")
            channel_delta = set(clean["initial_state"]["enabled_channels"]) - set(
                blocked["initial_state"]["enabled_channels"]
            )
            if channel_delta != {channel}:
                _fail("INTERVENTION_ISOLATION", "Channel outage must disable exactly its declared channel.")
        else:
            _fail("INTERVENTION_MECHANISM", f"Unsupported mechanism {mechanism}.")

        if _reachable_ses(self.family, blocked_access):
            _fail("INTERVENTION_CLOSURE", "An accepted SES remains reachable in BLOCKED.")
        terminal_access = blocked_access | set(restore["affected_evidence_ids"])
        if not _reachable_ses(self.family, terminal_access):
            _fail("RESTORATION_EXACT", "Restoration does not make any accepted SES reachable.")

    def maybe_restore(self, tool: str, call_index: int) -> tuple[str, ...]:
        if self._restore is None or self._restored:
            return ()
        spec = self._restore["restoration"]
        triggered = (
            spec["trigger_type"] == "get_channel_status" and tool == "get_channel_status"
        ) or (
            spec["trigger_type"] == "fixed_call_index" and call_index == spec["trigger_value"]
        )
        if not triggered:
            return ()
        self._accessible.update(self._restore["affected_evidence_ids"])
        channel = self._restore["affected_channel"]
        if channel is not None:
            self._enabled.add(channel)
        self._restored = True
        return (self._restore["intervention_id"],)

    def channel_available(self, channel: str) -> bool:
        if channel == "transcript":
            return "transcript" in self._enabled and "speech" in self._enabled
        return channel in self._enabled

    def channel_status(self, channel: str) -> str:
        return "available" if self.channel_available(channel) else "unavailable"

    def visible_records(self, records: Iterable[IndexRecord]) -> tuple[IndexRecord, ...]:
        """Hide every direct or derived record touching an inaccessible evidence route."""
        visible: list[IndexRecord] = []
        for record in records:
            if record.is_distractor and not record.route_evidence_ids:
                visible.append(record)
                continue
            routes = set(record.route_evidence_ids)
            family_routes = routes.intersection(self._family_evidence)
            if not family_routes or family_routes <= self._accessible:
                visible.append(record)
        return tuple(visible)
