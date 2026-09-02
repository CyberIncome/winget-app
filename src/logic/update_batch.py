"""Structured accounting for GUI package-update batches."""

from __future__ import annotations


def package_ref_key(ref: dict) -> tuple[str, str, str]:
    return (
        str(ref.get("match_by") or "").strip().casefold(),
        str(ref.get("value") or "").strip().casefold(),
        str(ref.get("source") or "").strip().casefold(),
    )


class BatchResultTracker:
    def __init__(self, package_refs):
        self._requested = {}
        for ref in package_refs or []:
            key = package_ref_key(ref)
            if not key[0] or not key[1]:
                continue
            self._requested.setdefault(key, dict(ref))
        self._successes: dict[tuple[str, str, str], dict] = {}
        self._failures: dict[tuple[str, str, str], dict] = {}

    @property
    def requested_count(self) -> int:
        return len(self._requested)

    def record_success(self, ref: dict) -> None:
        key = package_ref_key(ref)
        if key not in self._requested:
            return
        self._failures.pop(key, None)
        self._successes[key] = dict(ref)

    def record_failure(self, ref: dict, reason: str) -> None:
        key = package_ref_key(ref)
        if key not in self._requested or key in self._successes:
            return
        self._failures[key] = {
            "ref": dict(ref),
            "reason": str(reason or "unknown failure"),
        }

    def record_many_failures(self, refs, reason: str) -> None:
        for ref in refs or []:
            self.record_failure(ref, reason)

    def summary(self) -> dict[str, object]:
        completed = set(self._successes) | set(self._failures)
        pending = [
            ref for key, ref in self._requested.items() if key not in completed
        ]
        return {
            "requested": len(self._requested),
            "succeeded": len(self._successes),
            "failed": len(self._failures),
            "pending": len(pending),
            "successes": list(self._successes.values()),
            "failures": list(self._failures.values()),
            "pending_refs": pending,
        }
