# P23_102 human prescreen packet v1

distribution_authorized=false

This directory contains one source packet, twenty blank neutral lead forms, one blank P23 source exposure ledger, and fictional calibration material. The source packet defines the common review instructions. Each lead form supplies timestamp handles, neutral modality hypotheses, the seven required checks, the three allowed choices, and a free rationale field.

No form contains a human identity, observation, or completed choice. All source derivatives remain in source group P23. Validate this directory with:

```text
python tools/p23_102_human_prescreen_packets.py --mode check
```

Validate a completed import with:

```text
python tools/p23_102_human_prescreen_packets.py --mode validate-import --import-path completed.json
```
