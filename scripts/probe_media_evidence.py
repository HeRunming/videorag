#!/usr/bin/env python3
"""Probe one registered MP4 interval using media bytes only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_media.adapters import MediaPerception
from av_trace_media.reader import MediaReadError
from av_trace_media.types import TimeInterval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("--sha256", required=True, help="Registered sha256:<hex> for the exact media bytes.")
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--transcript-only", action="store_true")
    parser.add_argument("--ambient-only", action="store_true")
    args = parser.parse_args()
    perception = MediaPerception.synthetic(str(args.media), args.sha256)
    interval = TimeInterval(args.start, args.end)
    try:
        if args.transcript_only:
            result = perception.read_transcript(interval)
        elif args.ambient_only:
            result = perception.observe_ambient(interval)
        else:
            result = perception.inspect_clip(
                interval,
                include_video=not args.no_video,
                include_audio=not args.no_audio,
            )
    except (MediaReadError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": type(exc).__name__, "message": str(exc)}, indent=2))
        return 2
    print(json.dumps({"status": "ok", "result": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
