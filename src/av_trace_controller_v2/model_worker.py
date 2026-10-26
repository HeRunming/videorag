"""Offline Qwen worker with xgrammar-constrained Transformers generation."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

from av_trace_scale1b_agent.schema import PublicSchemaError, extract_json_object


class ConstraintRuntimeFailure(RuntimeError):
    pass


def _peak_rss() -> tuple[int, int]:
    peak_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak_kib, peak_kib * 1024


def _read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline()
    if not line:
        raise RuntimeError("PARENT_CLOSED_STDIN")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise TypeError("REQUEST_NOT_OBJECT")
    return value


def _write(value: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    )
    sys.stdout.flush()


class QwenRuntime:
    def __init__(
        self,
        snapshot: Path,
        *,
        threads: int,
        max_context_tokens: int,
    ) -> None:
        os.environ.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        for key in (
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "all_proxy",
            "NO_PROXY",
            "no_proxy",
        ):
            os.environ.pop(key, None)

        import numpy as np

        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]

        import torch
        import xgrammar as xgr
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.manual_seed(0)
        torch.set_num_threads(max(1, threads))
        self.torch = torch
        self.xgr = xgr
        self.tokenizer = AutoTokenizer.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            dtype="auto",
            low_cpu_mem_usage=True,
            attn_implementation="eager",
        ).eval()
        tokenizer_info = xgr.TokenizerInfo.from_huggingface(
            self.tokenizer,
            vocab_size=int(self.model.config.vocab_size),
        )
        self.grammar_compiler = xgr.GrammarCompiler(
            tokenizer_info,
            max_threads=max(1, threads),
        )
        self.max_context_tokens = max_context_tokens

    def _compile_constraint(self, schema: dict[str, Any]):
        try:
            return self.grammar_compiler.compile_json_schema(
                schema,
                any_whitespace=True,
                strict_mode=True,
                max_whitespace_cnt=8,
            )
        except Exception as exc:
            raise ConstraintRuntimeFailure(
                f"constraint compilation failed: {type(exc).__name__}: {exc}"
            ) from exc

    def generate(
        self,
        *,
        system: str,
        payload: dict[str, Any],
        max_new_tokens: int,
        constraint_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        constrained = constraint_schema is not None
        if constrained:
            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                },
            ]
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        payload, sort_keys=True, ensure_ascii=False
                    ),
                },
                {"role": "assistant", "content": "{"},
            ]
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
                continue_final_message=True,
            )
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_context_tokens,
        )
        generation_kwargs: dict[str, Any] = {
            **inputs,
            "do_sample": False,
            "max_new_tokens": max_new_tokens,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if constrained:
            try:
                from xgrammar.contrib.hf import LogitsProcessor

                compiled = self._compile_constraint(dict(constraint_schema))
                generation_kwargs["logits_processor"] = [
                    LogitsProcessor(compiled)
                ]
            except ConstraintRuntimeFailure:
                raise
            except Exception as exc:
                raise ConstraintRuntimeFailure(
                    "constraint integration failed: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        started = time.perf_counter()
        try:
            with self.torch.inference_mode():
                output = self.model.generate(**generation_kwargs)
        except Exception as exc:
            if constrained and "out of memory" not in str(exc).casefold():
                raise ConstraintRuntimeFailure(
                    f"constrained generation failed: {type(exc).__name__}: {exc}"
                ) from exc
            raise
        generated = output[0, inputs.input_ids.shape[1] :]
        decoded = self.tokenizer.decode(generated, skip_special_tokens=True)
        text = decoded if constrained else "{" + decoded
        parsed: Any = None
        parse_error: str | None = None
        if not constrained:
            try:
                parsed = extract_json_object(text)
            except PublicSchemaError as exc:
                parse_error = str(exc)
        peak_rss_kib, peak_rss_bytes = _peak_rss()
        return {
            "raw_text": text,
            "parsed": parsed,
            "parse_error": parse_error,
            "prompt_tokens": int(inputs.input_ids.shape[1]),
            "generated_tokens": int(generated.shape[0]),
            "latency_seconds": round(time.perf_counter() - started, 6),
            "peak_rss_kib": peak_rss_kib,
            "peak_rss_bytes": peak_rss_bytes,
            "constraint_engine": "xgrammar" if constrained else None,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--max-context-tokens", type=int, default=32768)
    args = parser.parse_args(argv)
    runtime = QwenRuntime(
        args.snapshot,
        threads=args.threads,
        max_context_tokens=args.max_context_tokens,
    )
    peak_rss_kib, peak_rss_bytes = _peak_rss()
    _write(
        {
            "type": "ready",
            "pid": os.getpid(),
            "model_class": type(runtime.model).__name__,
            "tokenizer_class": type(runtime.tokenizer).__name__,
            "dtype": str(next(runtime.model.parameters()).dtype),
            "device": str(next(runtime.model.parameters()).device),
            "max_context_tokens": args.max_context_tokens,
            "offline": True,
            "local_files_only": True,
            "constraint_engine": "xgrammar",
            "peak_rss_kib": peak_rss_kib,
            "peak_rss_bytes": peak_rss_bytes,
        }
    )
    while True:
        try:
            request = _read()
        except RuntimeError as exc:
            if str(exc) == "PARENT_CLOSED_STDIN":
                return 0
            raise
        if request.get("type") == "shutdown":
            _write({"type": "shutdown_ack"})
            return 0
        if request.get("type") != "generate":
            _write({"type": "error", "code": "UNKNOWN_REQUEST"})
            continue
        try:
            constraint = request.get("constraint_schema")
            if constraint is not None and not isinstance(constraint, dict):
                raise ConstraintRuntimeFailure(
                    "constraint schema must be an object"
                )
            result = runtime.generate(
                system=str(request["system"]),
                payload=dict(request["payload"]),
                max_new_tokens=int(request["max_new_tokens"]),
                constraint_schema=constraint,
            )
            _write({"type": "generation", **result})
        except ConstraintRuntimeFailure as exc:
            _write(
                {
                    "type": "error",
                    "code": "CONSTRAINT_RUNTIME_FAILURE",
                    "message": str(exc)[:500],
                }
            )
        except (RuntimeError, ValueError, TypeError, KeyError, MemoryError) as exc:
            message = str(exc)
            code = (
                "OOM"
                if "out of memory" in message.casefold()
                else type(exc).__name__.upper()
            )
            _write({"type": "error", "code": code, "message": message[:500]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
