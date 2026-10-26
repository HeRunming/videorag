"""Errors raised by the metadata-only data adapter pipeline."""

from __future__ import annotations


class DataAdapterError(RuntimeError):
    """Base class for deterministic, user-facing preflight failures."""


class FixtureError(DataAdapterError):
    """A local repository snapshot is malformed or incomplete."""


class SnapshotImportError(DataAdapterError):
    """A local metadata snapshot is unsafe, malformed, or cannot be promoted."""


class SelectionError(DataAdapterError):
    """Candidate selection cannot be completed safely."""


class ManifestDraftError(DataAdapterError):
    """A fail-closed acquisition manifest cannot be drafted."""


class DownloadPlanError(DataAdapterError):
    """A download plan or execution approval is invalid."""


class DownloadRefused(DownloadPlanError):
    """Execution was refused before any transfer was attempted."""
