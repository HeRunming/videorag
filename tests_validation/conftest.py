from __future__ import annotations

import pytest

from av_trace_validation.certifier import certify_dataset
from av_trace_validation.generator import generate_validator_artifacts


@pytest.fixture(scope="session")
def validator_bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("validator-bundle")
    index = generate_validator_artifacts(output_root=root)
    certificate = certify_dataset(validator_root=root, strict=True)
    return root, index, certificate

