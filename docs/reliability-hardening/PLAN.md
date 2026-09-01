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

### Configuration/security
- Config defaults are deep-copied.
- Config writes are atomic.
- PAT storage is not rewritten on every keystroke.
- HTTP helpers reject unsafe redirect targets and cap response bodies.

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

## Verification strategy

Because this execution environment is Linux, has no PySide6 installed, has no external network, and GitHub Actions minutes are unavailable, this branch uses layered gates:

- `python -m compileall` / AST parsing for every changed Python file.
- Pure-Python unit tests for parser/result/job-state logic that does not require Windows or Qt.
- Static invariants for lifecycle ownership (for example, production hardened code must not contain raw daemon-thread launches).
- Existing pytest additions for Windows/PySide6 behavior, intended to run locally on the target Windows machine.
- Git diff / repository-tree inspection for hygiene and unintended scope.
- Final goal-backward manual verification against every must-have above.

A native Windows GUI run remains required before merging because COM, `QProcess`, pywin32, App Installer, and Windows multiprocessing behavior cannot be honestly proven in this container.

## Deviation log

Record newly discovered issues here as they are found.

- D1: GitHub repository initially denied branch-ref creation through the integration. Access was corrected by the user before any code change; branch invariant preserved.
- D2: GitHub Actions cannot be used as a verification gate because the account currently has no CI minutes. Replaced with local/offline gates plus explicit Windows-local verification instructions.
- D3: Current Microsoft WinGet documentation (July 2026) still exposes no JSON output for `winget upgrade`; parsing cannot simply be replaced with a JSON flag. Strict table parsing remains necessary.
