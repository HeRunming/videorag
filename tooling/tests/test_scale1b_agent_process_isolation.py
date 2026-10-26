from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from av_trace_scale1b_agent.process import (
    FreshQwenProcessFactory,
    ModelProcessError,
    ProcessConfig,
    QwenProcess,
)

WORKER = r"""
import json
import os
import sys

seen = 0

def emit(value):
    sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")
    sys.stdout.flush()

emit({
    "type": "ready",
    "pid": os.getpid(),
    "device": "cpu",
    "dtype": "fake",
    "offline": os.environ.get("HF_HUB_OFFLINE") == "1",
    "session_env": os.environ.get("AV_TRACE_SESSION_ID"),
    "cache_env": os.environ.get("AV_TRACE_CACHE_NAMESPACE"),
    "home": os.environ.get("HOME"),
    "cache_home": os.environ.get("XDG_CACHE_HOME"),
})
for line in sys.stdin:
    request = json.loads(line)
    if request.get("type") == "shutdown":
        emit({"type": "shutdown_ack"})
        raise SystemExit(0)
    seen += 1
    emit({
        "type": "generation",
        "raw_text": json.dumps({
            "seen": seen,
            "session_id": request["session_id"],
            "cache_namespace": request["cache_namespace"],
            "request_id": request["request_id"],
        }),
        "parsed": {"seen": seen},
        "prompt_tokens": 1,
        "generated_tokens": 1,
    })
"""


CRASH_WORKER = r"""
import json
import os
import sys

sys.stdout.write(json.dumps({"type": "ready", "pid": os.getpid()}) + "\n")
sys.stdout.flush()
for line in sys.stdin:
    request = json.loads(line)
    if request.get("type") == "shutdown":
        raise SystemExit(0)
    sys.stderr.write("crash-marker-from-fake-worker\n")
    sys.stderr.flush()
    raise SystemExit(17)
"""


def _config() -> ProcessConfig:
    return ProcessConfig(
        startup_timeout_s=2,
        generation_timeout_s=2,
        shutdown_timeout_s=0.2,
    )


def test_fresh_r_n_processes_have_distinct_sessions_and_no_shared_requests(
    tmp_path: Path,
) -> None:
    factory = FreshQwenProcessFactory(
        tmp_path,
        config=_config(),
        command=[sys.executable, "-c", WORKER],
    )
    runtime_dirs: list[Path] = []
    pids: list[int] = []

    with factory.continuations() as pair:
        attestations = pair.attestations()
        restored = attestations["R"]
        no_trigger = attestations["N"]
        runtime_dirs = [
            Path(restored["runtime_namespace"]),
            Path(no_trigger["runtime_namespace"]),
        ]
        pids = [restored["pid"], no_trigger["pid"]]

        assert restored["pid"] != no_trigger["pid"]
        assert restored["process_group_id"] != no_trigger["process_group_id"]
        assert restored["session_id"] != no_trigger["session_id"]
        assert restored["cache_namespace"] != no_trigger["cache_namespace"]
        assert restored["runtime_namespace"] != no_trigger["runtime_namespace"]
        assert not restored["shared_conversation_state"]
        assert not restored["shared_kv_state"]
        assert pair.restored.metadata["offline"]
        assert pair.no_trigger.metadata["offline"]
        assert pair.restored.metadata["session_env"] == restored["session_id"]
        assert (
            pair.no_trigger.metadata["cache_env"]
            == no_trigger["cache_namespace"]
        )

        first_r = pair.restored.generate(
            system="r", payload={"arm": "R"}, max_new_tokens=1
        )
        first_n = pair.no_trigger.generate(
            system="n", payload={"arm": "N"}, max_new_tokens=1
        )
        second_r = pair.restored.generate(
            system="r2", payload={"arm": "R"}, max_new_tokens=1
        )

        assert json.loads(first_r["raw_text"])["seen"] == 1
        assert json.loads(first_n["raw_text"])["seen"] == 1
        assert json.loads(second_r["raw_text"])["seen"] == 2
        assert (
            json.loads(first_r["raw_text"])["session_id"]
            != json.loads(first_n["raw_text"])["session_id"]
        )

    assert all(not path.exists() for path in runtime_dirs)
    assert all(not _process_exists(pid) for pid in pids)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_real_process_crash_retains_stderr_and_session_metadata(
    tmp_path: Path,
) -> None:
    with QwenProcess(
        tmp_path,
        config=_config(),
        command=[sys.executable, "-c", CRASH_WORKER],
    ) as model:
        with pytest.raises(ModelProcessError) as caught:
            model.generate(system="x", payload={"x": 1}, max_new_tokens=1)

        record = caught.value.to_record()
        assert record["code"] == "PROCESS_CRASH"
        assert "crash-marker-from-fake-worker" in (
            record["details"]["stderr_text"]
        )
        assert record["details"]["session_id"] == model.session_id
        assert record["details"]["cache_namespace"] == model.cache_namespace
        assert record["details"]["request_count"] == 1
        assert len(record["details"]["request_hashes"]) == 1
