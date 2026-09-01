# Reliability Hardening Plan

Branch: `audit/ferrox-reliability-hardening`
Base: `master@fedd09ec7e84f91e22760ca7f3736e9db978db48`

## Operating discipline

This hardening pass follows the parts of the Ferrox Factory line that are useful for this repository:

1. Research current framework/runtime behavior before changing version-sensitive code.
2. Define goal-backward must-haves before implementation.
3. Make isolated, logically atomic commits.
4. Treat newly discovered correctness/reliability defects as recorded in-scope deviations.
5. Verify each increment mechanically before proceeding.
6. Perform a final adversarial, goal-backward verification; changed files are not evidence by themselves.
7. Bound repair loops. A failed gate either gets a concrete repair or is recorded as an explicit remaining gap.

## Goal

Make Winget Universal Dashboard resilient to intermittent startup, scan, update, process, and shutdown failures while improving diagnostics and preserving existing UI behavior.

## Must-haves

### Lifecycle
- No production path launches untracked fire-and-forget Python daemon threads.
- Long-running inventory, parsing, detective, and API work has explicit ownership, timeout, cleanup, and cancellation.
- Closing the GUI terminates owned child processes and does not leave background workers targeting destroyed Qt objects.
- Startup work is staged instead of immediately overlapping every heavyweight subsystem.

### Winget process state
- `FailedToStart`, `CrashExit`, watchdog timeout, normal non-zero exit, and successful exit are distinct outcomes.
- A crashed/timed-out Winget child is not retried merely by removing `--silent`.
- Watchdog behavior is based on a hard elapsed deadline; output silence may warn but must not by itself kill a legitimate installer.
- Batch completion returns the UI to a clean idle state.

### Parsing/correctness
- Malformed Winget table output fails explicitly instead of silently masquerading as zero available updates.
- The parser validates column ordering/bounds and tolerates optional `Source` output.
- Unknown/uncertain installed versions are preserved without unsafe local filtering.
- Package/source provenance is preserved when constructing exact Winget update commands.
- Registry inventory identifiers are never treated as Winget package identifiers.

### Configuration/security
- Config defaults are deep-copied.
- Config writes are atomic.
- PAT storage is not rewritten on every keystroke.
- HTTP helpers reject unsafe redirect targets, cap response bodies, and do not forward explicit credentials across origins.

### Diagnostics
- Every GUI run has a session identifier.
- Owned process/job lifecycle events are logged with enough detail to reconstruct the last active operation before a crash.
- There is an explicit clean-exit marker.

### Repository quality
- Tracked Python bytecode/cache artifacts are removed and ignored broadly.
- Runtime and development dependencies are separated.
- Runtime dependency versions are constrained to a tested release band rather than the entire PySide6 6.x line.
- No GitHub Actions workflow is added or required during this pass because CI minutes are unavailable.

## Phases

### Phase 1 — Lifecycle foundation
Create process-isolated worker targets and a Qt-side managed job controller. Route inventory, Winget parsing, detective, and GitHub rate-limit work through owned subprocess jobs.

### Phase 2 — GUI crash hardening
Introduce a hardened `MainWindow` subclass that stages startup, owns job lifecycle, performs deterministic shutdown, distinguishes Winget outcomes, and improves watchdog/retry semantics.

### Phase 3 — Parser and execution correctness
Add a strict Winget upgrade-table parser and shared structured subprocess result semantics for CLI-facing execution paths.

### Phase 4 — Configuration and security hardening
Make configuration writes atomic/deep-copy safe, debounce PAT persistence, and constrain redirect behavior.

### Phase 5 — Diagnostics, repository hygiene, dependency reproducibility
Add session/lifecycle logging, remove tracked caches, split requirements, and document offline/Windows verification.

### Phase 6 — Verification and architecture cleanup
Run all available mechanical gates, adversarially inspect integration and failure paths, fix discovered regressions, and record residual Windows-only verification requirements.

Implementation/static audit status: complete. Native Windows acceptance status: pending `scripts/verify_windows.py` on the target Windows environment.

## Verification strategy

Because this execution environment is Linux, has no PySide6 installed, has no outbound shell network, and GitHub Actions minutes are unavailable, this branch uses layered gates:

- Pure-Python executable assertions for parser, command construction/execution, configuration, and HTTP safety logic.
- AST/source invariants for lifecycle ownership and canonical entry points.
- Pytest/pytest-qt regression coverage committed for Windows/PySide6 behavior.
- `scripts/verify_windows.py` as the deterministic local Windows gate, including production GUI construction/clean shutdown.
- Git diff / repository-tree inspection for hygiene and unintended scope.
- Final goal-backward manual verification against every must-have above.

A native Windows GUI run remains required before merging because COM, `QProcess`, pywin32, App Installer, and Windows multiprocessing behavior cannot be honestly proven in this container.

## Deviation log

- D1: GitHub repository initially denied branch-ref creation through the integration. Access was corrected by the user before any code change; branch invariant preserved.
- D2: GitHub Actions cannot be used as a verification gate because the account currently has no CI minutes. Replaced with local/offline gates plus explicit Windows-local verification instructions.
- D3: Current Microsoft WinGet documentation still exposes no structured JSON output for `winget upgrade`; strict validation of the human-readable table remains necessary.
- D4: Legacy UI startup overlapped heavyweight update, inventory, detective, and API work and used unowned daemon threads. Production startup was staged and long-running work moved to owned spawned-process jobs.
- D5: Winget process failures conflated normal non-zero exits, crashes, timeouts, and start failures; crash/timeout could enter inappropriate retry behavior. Production state handling now distinguishes these outcomes and retries without `--silent` only after a normal installer failure.
- D6: The original parser could return an empty/partial result for malformed or truncated Winget output. A strict parser now validates headers, separators, columns, every data row, and explicit no-update output.
- D7: Detective-only remote-version results could overwrite the authoritative `Available` value from Winget and could appear executable. Detective results are now informational unless backed by a current Winget upgrade row.
- D8: Exact update targeting originally did not preserve Winget source provenance, allowing duplicate IDs from different sources to collapse. Source is now displayed, retained in selection identity, included in deduplication, and passed via `--source` where available.
- D9: A `FailedToStart` during a batch could continue attempting the same unavailable Winget executable for subsequent packages. The remaining batch is now aborted and UI state is cleared.
- D10: Debounced PAT persistence could lose a pending value if the window closed before the timer fired. Pending PAT state is flushed during production shutdown.
- D11: CLI update scans diverged from the GUI command contract and `status` repeated registry work. CLI `check`/`status` now use the hardened noninteractive scan command and `status` reuses one registry crawl; Ctrl+C also terminates a live update child.
- D12: An adversarial verification run caught a defect in the hardening itself: regex/end trimming could allow newline-bearing selector/source input through validation. Validation was changed to full-string/control-character checks and regression tests were added before the gate was rerun.
- D13: Cross-origin redirect handling stripped secret headers but originally retained explicit Requests `auth=`/`cookies=` kwargs. Those credentials are now dropped whenever a manual redirect changes origin.
- D14: Inventory `Id` values are registry uninstall keys, not Winget provenance. The final audit found that ID collisions could theoretically target the wrong Winget row; inventory-triggered updates now ignore registry IDs and require one unique exact name match against authoritative Winget rows.
- D15: An alternate `src.ui.main_window` direct-execution path could bypass the hardened controller. The historical implementation is preserved in `legacy_window.py`; `main_window.py` is now a compatibility export shim whose executable path routes through canonical `src.main` / `ProductionMainWindow`.
- D16: Previous generated codebase-audit artifacts had scanned virtual-environment content and contained encoding-error output. Misleading generated reports were removed and replaced with this evidence-backed audit trail.
