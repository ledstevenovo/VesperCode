"""T01.2 step 1.D: real cross-process Win32 workspace mutex probes."""

from __future__ import annotations

from spikes.win32_workspace_boundary.mutex_probe import probe_workspace_mutex


def test_two_processes_never_hold_one_workspace_mutex_together() -> None:
    result = probe_workspace_mutex("a" * 64, contender_count=2, timeout_ms=2_000)
    assert result.maximum_concurrent_holders == 1


def test_mutex_probe_closes_contention_timeout_abandonment_and_cleanup() -> None:
    result = probe_workspace_mutex("b" * 64, contender_count=3, timeout_ms=1)
    assert result.workspace_identity_digest == "b" * 64
    assert result.contender_count == 3
    assert result.maximum_concurrent_holders == 1
    assert result.timeout_count >= 1
    assert result.cleanup_verified is True


def test_distinct_workspace_mutex_names_do_not_share_a_lease() -> None:
    first = probe_workspace_mutex("c" * 64, contender_count=2, timeout_ms=2_000)
    second = probe_workspace_mutex("d" * 64, contender_count=2, timeout_ms=2_000)
    assert first.workspace_identity_digest != second.workspace_identity_digest
    assert first.maximum_concurrent_holders == second.maximum_concurrent_holders == 1
