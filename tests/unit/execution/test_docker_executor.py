"""T18.2 legacy step 18.C: closed execution result and collector contracts.

``RawExecutionResultV1`` is one closed bounded raw-evidence schema (every
success/failure combination pins its exact flags, byte total, and error
code), and the bounded attach-stream collector parses the docker frame
protocol with deadlines and per-stream caps deterministically offline
(GREEN-1..GREEN-4).
"""

from __future__ import annotations

import struct
import time

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.execution.docker_executor import (
    RawExecutionResultV1,
    _BoundedStreamCollector,
)

_MAX_OUTPUT_BYTES = 4 * 1024**2


def success_result() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "req-1",
        "container_id": "c" * 64,
        "exit_code": 0,
        "stdout": b"out",
        "stderr": b"err",
        "output_bytes": 6,
        "timed_out": False,
        "output_limit_exceeded": False,
        "container_stopped": False,
        "error_code": None,
    }


def test_raw_execution_result_closed_combinations() -> None:
    result = RawExecutionResultV1.model_validate(success_result())
    assert result.error_code is None
    assert result.output_bytes == 6
    timeout = RawExecutionResultV1.model_validate(
        {
            **success_result(),
            "exit_code": 137,
            "timed_out": True,
            "container_stopped": True,
            "error_code": "CHECK_TIMEOUT",
        }
    )
    assert timeout.timed_out is True
    overflow = RawExecutionResultV1.model_validate(
        {
            **success_result(),
            "exit_code": 137,
            "output_limit_exceeded": True,
            "container_stopped": True,
            "error_code": "CHECK_OUTPUT_LIMIT_EXCEEDED",
        }
    )
    assert overflow.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED"
    violation = RawExecutionResultV1.model_validate(
        {
            **success_result(),
            "exit_code": None,
            "stdout": b"",
            "stderr": b"",
            "output_bytes": 0,
            "container_stopped": False,
            "error_code": "CHECK_ISOLATION_VIOLATION",
        }
    )
    assert violation.error_code == "CHECK_ISOLATION_VIOLATION"
    execution_error = RawExecutionResultV1.model_validate(
        {
            **success_result(),
            "container_id": "",
            "exit_code": None,
            "stdout": b"",
            "stderr": b"",
            "output_bytes": 0,
            "container_stopped": False,
            "error_code": "CHECK_EXECUTION_ERROR",
        }
    )
    assert execution_error.error_code == "CHECK_EXECUTION_ERROR"


def test_raw_execution_result_rejects_inconsistent_outcomes() -> None:
    rejected: list[dict[str, object]] = [
        # Success with failure flags or without an exit code.
        {**success_result(), "timed_out": True},
        {**success_result(), "output_limit_exceeded": True},
        {**success_result(), "container_stopped": True},
        {**success_result(), "exit_code": None},
        # Timeout without its flags.
        {
            **success_result(),
            "exit_code": 137,
            "timed_out": False,
            "container_stopped": True,
            "error_code": "CHECK_TIMEOUT",
        },
        {
            **success_result(),
            "exit_code": 137,
            "timed_out": True,
            "container_stopped": False,
            "error_code": "CHECK_TIMEOUT",
        },
        # Output-limit without its flags.
        {
            **success_result(),
            "exit_code": 137,
            "output_limit_exceeded": False,
            "container_stopped": True,
            "error_code": "CHECK_OUTPUT_LIMIT_EXCEEDED",
        },
        {
            **success_result(),
            "exit_code": 137,
            "output_limit_exceeded": True,
            "container_stopped": False,
            "error_code": "CHECK_OUTPUT_LIMIT_EXCEEDED",
        },
        # Isolation violations detected before start: no flags, no code.
        {
            **success_result(),
            "exit_code": 0,
            "container_stopped": True,
            "error_code": "CHECK_ISOLATION_VIOLATION",
        },
        # Execution errors cannot carry a code, timeout flags, or an
        # exit code; ``container_stopped`` stays legal because the
        # executor stops the exact container before failing when one was
        # created.
        {
            **success_result(),
            "container_id": "",
            "exit_code": 0,
            "container_stopped": False,
            "error_code": "CHECK_EXECUTION_ERROR",
        },
        {
            **success_result(),
            "container_id": "",
            "exit_code": None,
            "timed_out": True,
            "container_stopped": False,
            "error_code": "CHECK_EXECUTION_ERROR",
        },
        {
            **success_result(),
            "container_id": "",
            "exit_code": None,
            "output_limit_exceeded": True,
            "container_stopped": False,
            "error_code": "CHECK_EXECUTION_ERROR",
        },
        # A non-execution-error result must carry a container id.
        {**success_result(), "container_id": ""},
        # Unknown error codes and unknown flags.
        {**success_result(), "error_code": "CHECK_UNKNOWN"},
        {**success_result(), "timed_out": 1},
        # Byte totals must bind the exact raw output bytes.
        {**success_result(), "output_bytes": 5},
        {**success_result(), "output_bytes": -1},
        {**success_result(), "output_bytes": True},
        # Streams are exact raw bytes: text spellings reject.
        {**success_result(), "stdout": "out"},
        # Type-confused scalar spellings.
        {**success_result(), "exit_code": "0"},
        {**success_result(), "exit_code": True},
        {**success_result(), "schema_version": True},
        {**success_result(), "schema_version": 1.0},
        {**success_result(), "container_stopped": 1},
        {**success_result(), "request_id": ""},
        {**success_result(), "extra": 1},
    ]
    for payload in rejected:
        with pytest.raises(ValidationError):
            RawExecutionResultV1.model_validate(payload)


def test_raw_execution_result_preserves_non_utf8_raw_bytes() -> None:
    # Raw non-UTF-8 bytes are the evidence: the exact captured bytes are
    # stored and the byte total binds them (never lossily re-encoded).
    result = RawExecutionResultV1.model_validate(
        {
            **success_result(),
            "stdout": b"ok-\xff\xfe",
            "stderr": b"err",
            "output_bytes": 8,
        }
    )
    assert result.stdout == b"ok-\xff\xfe"
    assert result.stderr == b"err"
    assert result.output_bytes == 8
    assert b"\xff" in result.stdout


def _frame(stream_id: int, payload: bytes) -> bytes:
    return struct.pack(">BxxxL", stream_id, len(payload)) + payload


class _ScriptedSocket:
    """Scripted attach socket over the collector's reader surface."""

    def __init__(self, chunks: list[bytes], timeout_forever: bool = False) -> None:
        self._chunks = list(chunks)
        self._timeout_forever = timeout_forever

    def settimeout(self, timeout: float) -> None:
        return None

    def recv_into(self, buffer: bytearray) -> int:
        if self._timeout_forever:
            raise TimeoutError("scripted silent stream")
        if not self._chunks:
            return 0
        chunk = self._chunks.pop(0)
        buffer[: len(chunk)] = chunk
        return len(chunk)


def test_bounded_collector_parses_frames_across_chunks() -> None:
    # Frame boundaries split across arbitrary chunk boundaries.
    frame_a = _frame(1, b"stdout-bytes")
    frame_b = _frame(2, b"stderr-bytes")
    chunked = [
        frame_a[:3],
        frame_a[3:9],
        frame_a[9:] + frame_b[:4],
        frame_b[4:],
    ]
    stdout, stderr, outcome = _BoundedStreamCollector(
        _ScriptedSocket(chunked), _MAX_OUTPUT_BYTES, time.monotonic() + 60
    ).collect()
    assert outcome == "ok"
    assert stdout == b"stdout-bytes"
    assert stderr == b"stderr-bytes"


def test_bounded_collector_deadline() -> None:
    stdout, stderr, outcome = _BoundedStreamCollector(
        _ScriptedSocket([], timeout_forever=True),
        _MAX_OUTPUT_BYTES,
        time.monotonic() - 0.01,
    ).collect()
    assert outcome == "timeout"
    assert stdout == b""
    assert stderr == b""


def test_bounded_collector_overflow_never_buffers_beyond_cap() -> None:
    big_frame = _frame(1, b"x" * (_MAX_OUTPUT_BYTES + 1))
    stdout, stderr, outcome = _BoundedStreamCollector(
        _ScriptedSocket([_frame(1, b"prefix"), big_frame]),
        _MAX_OUTPUT_BYTES,
        time.monotonic() + 60,
    ).collect()
    assert outcome == "overflow"
    assert stdout == b"prefix"
    assert stderr == b""
    # A single stream cannot exceed the cap either.
    overflow_stream = _BoundedStreamCollector(
        _ScriptedSocket([_frame(1, b"x" * _MAX_OUTPUT_BYTES), _frame(1, b"y")]),
        _MAX_OUTPUT_BYTES,
        time.monotonic() + 60,
    ).collect()
    assert overflow_stream[2] == "overflow"
    # The cap is the COMBINED stdout+stderr total of one check (SPEC
    # §1.4.5/§5.1: 单次检查输出最多 4 MiB).
    combined = _BoundedStreamCollector(
        _ScriptedSocket(
            [
                _frame(1, b"o" * (_MAX_OUTPUT_BYTES - 100)),
                _frame(2, b"e" * 200),
            ]
        ),
        _MAX_OUTPUT_BYTES,
        time.monotonic() + 60,
    ).collect()
    assert combined[2] == "overflow"
    within = _BoundedStreamCollector(
        _ScriptedSocket(
            [
                _frame(1, b"o" * (_MAX_OUTPUT_BYTES - 100)),
                _frame(2, b"e" * 50),
            ]
        ),
        _MAX_OUTPUT_BYTES,
        time.monotonic() + 60,
    ).collect()
    assert within[2] == "ok"
    assert len(within[0]) + len(within[1]) == _MAX_OUTPUT_BYTES - 50
