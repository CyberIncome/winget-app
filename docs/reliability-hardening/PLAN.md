# Reliability Hardening Plan

Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`
Date: 2026-09-01

## Operating discipline

This pass follows the useful Ferrox Factory practices established before implementation:

1. research framework/runtime behavior before version-sensitive changes;
2. define goal-backward must-haves;
3. isolate changes in small commits;
4. add newly discovered defects to scope instead of hiding them;
5. require mechanical evidence after changes;
6. distrust an apparently finished state and run another adversarial pass;
7. distinguish what can be proven on the audit host from what requires native Windows acceptance.

## Goal

Make Winget Universal Dashboard resilient to intermittent startup, scan, update, process, output, and shutdown failures while preserving the existing UI and making unsafe/ambiguous package targeting fail closed.

## Must-haves

### Lifecycle and process ownership
- No canonical production path launches untracked fire-and-forget daemon threads for long-running work.
- Inventory, parsing, detective and API work has explicit process ownership, timeout, cancellation and cleanup.
- Canonical shutdown contains child-process/QProcess teardown exceptions and does not target destroyed Qt objects.
- Startup work is staged instead of overlapping every heavyweight subsystem.
- Foreground refresh/inventory/update requests do not overlap.

### Winget process protocol
- `FailedToStart`, `CrashExit`, hard timeout, normal non-zero exit and success remain distinct.
- Crash/timeout never enters the normal retry-without-`--silent` path.
- Output silence may warn but does not itself kill an installer.
- Refresh stdout is bounded and a read/overflow failure invalidates the scan rather than creating a partial authoritative result.
- Console/live-line rendering is bounded.

### Parsing and update correctness
- Malformed/partial Winget output fails closed.
- Localized table headers and CJK/full-width fields are parsed by display-cell layout rather than English labels/codepoint offsets.
- Unicode width disagreement fails closed instead of shifting a package ID into a neighboring column.
- Unknown installed versions are preserved without vetoing a Winget-reported update.
- Package source provenance survives display, selection, deduplication, command construction and row removal.
- Registry uninstall IDs are never used as Winget package provenance.
- Detective-only findings are informational and cannot independently authorize an update.
- Package/name/source selectors reject truncated, control-bearing or option-like values.

### Configuration, network and resource bounds
- Config defaults/reads are deep-copy safe and writes are atomic.
- Legacy PAT migration does not destroy plaintext state until secure-store migration succeeds.
- PAT writes are debounced and pending state is flushed during canonical close.
- HTTP requests are HTTPS-only, bounded in redirects/body size, and do not forward explicit credentials across origins.
- CLI captured stdout/stderr is disk-backed and bounded rather than unbounded in-memory capture.

### Diagnostics and release reproducibility
- Each GUI run has a session ID and persistent rotating diagnostics.
- Unhandled Python/thread/native faults have a durable logging path.
- Normal close emits a clean-exit marker.
- Runtime/dev/build dependencies are separated and constrained.
- Tracked bytecode/cache artifacts are removed and ignored.
- A clean Windows clone can build GUI/CLI release artifacts from checked-in tooling.
- No GitHub Actions workflow is required; release acceptance is available as a local Windows gate.

## Phases and status

### Phase 1 — Baseline/Ferrox research and repository audit
**Complete.** Repository structure, runtime paths, Ferrox Factory operating model, historical audit artifacts and initial crash/correctness risks were mapped before implementation.

### Phase 2 — Owned background lifecycle
**Complete.** Added worker targets and `ManagedProcessJob`; long-running production work uses owned spawned processes with timeout/cancel/cleanup.

### Phase 3 — Staged hardened GUI controller
**Complete.** `HardenedMainWindow` stages startup, separates process outcomes, changes watchdog semantics and provides deterministic managed-job behavior.

### Phase 4 — Production provenance/protocol layer
**Complete.** `ProductionMainWindow` owns source-aware update authority, strict process-output capture, callback containment, operation exclusion and detective isolation.

### Phase 5 — Canonical runtime boundary
**Complete.** `RuntimeMainWindow` is the final GUI surface and contains synchronous QProcess start/watchdog failures plus hostile shutdown state/terminate/wait/kill failures. Canonical path is `src.main -> RuntimeMainWindow`.

### Phase 6 — Parser, executor and CLI hardening
**Complete.** Added strict localized Winget parser, robust byte decoder, full selector validation, source-aware command generation and disk-backed bounded CLI capture.

### Phase 7 — Config/network/diagnostics/repository hygiene
**Complete.** Atomic config persistence, keyring migration, bounded redirect-aware HTTPS, rotating/session/fault logging, cache cleanup and dependency separation are in place.

### Phase 8 — Reproducible Windows packaging/acceptance
**Complete / PASS.** `scripts/build_windows.py` built both one-file artifacts successfully. The packaged CLI and packaged GUI smoke tests passed. Native Windows verification passed after one verification-harness repair loop.

### Phase 9 — Final adversarial verification and documentation
**Complete / PASS.** The final loops found and repaired additional defects, including stale Qt model indexes, stdout-read invalidation, shutdown exception escape paths, broader selector controls, bounded CLI capture, a console-history regression introduced during hardening, an over-strict Unicode parser invariant, and a direct smoke-script import-path defect in the verification harness.

### Phase 10 — Native Windows acceptance
**Complete / PASS.** Final accepted Windows run: compile PASS, Ruff PASS, native lifecycle 19/19 PASS, full pytest/pytest-qt 181/181 PASS, source CLI PASS, canonical runtime GUI smoke PASS, Winget v1.29.290 PASS, real read-only Winget scan PASS. The immediately preceding build-enabled run also passed GUI/CLI PyInstaller builds and both packaged smokes.

## Important deviations/findings added during execution

- Legacy startup overlapped heavy subsystems and used unowned daemon threads.
- Winget failure states were conflated and crash/timeout could reach retry behavior.
- Human-readable Winget parsing could return empty/partial results on malformed output.
- Duplicate package IDs from different sources lost source identity.
- Registry uninstall IDs were incorrectly capable of influencing Winget matching.
- Detective findings could mutate executable update state.
- Failed-to-start batches could repeatedly attempt an unavailable Winget executable.
- Debounced PAT state could be lost on close.
- CLI and GUI scan contracts diverged.
- Cross-origin redirect handling initially stripped secret headers but still forwarded explicit `auth=`/`cookies=` kwargs.
- An alternate legacy GUI execution path could bypass the hardened controller.
- A hardening validator initially accepted newline-adjacent selector/source input; verification caught it and the gate was restarted.
- QProcess callback and shutdown methods still had exception escapes after the first controller hardening; `RuntimeMainWindow` now owns the final boundary.
- Production model source-aware checkbox identity initially disagreed with inherited selection helper methods; the helper contract was unified.
- CLI `capture_output=True` was an unbounded memory path; capture is now temp-file-backed and bounded.
- A hardening change accidentally increased console history from 2,000 to 10,000 blocks; canonical runtime restores the original 2,000-block cap while retaining new live-line/output caps.
- A Unicode boundary invariant initially rejected a legitimate German truncated-ID fixture. Fresh exact-blob testing caught it; the parser gate reran 15/15 after correction.
- The first Windows aggregate run found a test-harness-only import-path defect in `scripts/smoke_gui.py`; all application tests/builds/package smokes had passed. The harness was repaired, guarded, and the full Windows gate reran successfully with 181 tests.
- Final HTTP review identified that current HTTPS safety is not DNS/IP-level SSRF isolation. This remains a non-blocking future hardening opportunity rather than a fragile hostname blacklist.

## Final evidence / release rule

Audit-host exact-current-blob evidence: **65 tests passed** in the final pure-Python loop.

Native Windows acceptance:

- lifecycle integration: **19/19 PASS**;
- full pytest/pytest-qt: **181/181 PASS**;
- real read-only Winget scan: **PASS**;
- aggregate Windows verifier: **PASS**.

Packaged acceptance:

- GUI PyInstaller build: **PASS**;
- CLI PyInstaller build: **PASS**;
- packaged CLI smoke: **PASS**;
- packaged GUI smoke: **PASS**.

The only changes after the successful packaged build were the direct smoke-script path bootstrap, its regression test and documentation; application/build sources were unchanged.

**Implementation/static/pure-Python status: COMPLETE / PASS.**

**Native Windows/package acceptance: COMPLETE / PASS.**

**Merge/release: READY TO MERGE.**
