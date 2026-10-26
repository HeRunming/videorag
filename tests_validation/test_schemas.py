from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from av_trace_validation.schemas import SCHEMA_FILES


def test_all_validator_schemas_are_valid_draft_2020_12():
    root = Path("mvp/schemas")
    assert len(SCHEMA_FILES) >= 8
    for filename in SCHEMA_FILES.values():
        schema = json.loads((root / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith("urn:av-trace:schema:validator-")
        assert schema["properties"]["schema_version"]["const"] == "1.0.0"

