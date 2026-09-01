# Reliability Hardening Verification

Status: IN PROGRESS

This file is the evidence ledger for `audit/ferrox-reliability-hardening`.

## Evidence rules

- Implementation claims are not accepted without code or mechanical evidence.
- Each must-have resolves to VERIFIED, FAILED, or WINDOWS-VERIFY.
- WINDOWS-VERIFY is used only where the current environment cannot exercise a Windows/Qt/WinGet boundary.
- Any FAILED must-have blocks merge.

## Must-have ledger

| Must-have | Status | Evidence |
| --- | --- | --- |
| No untracked production daemon threads | IN PROGRESS | |
| Owned jobs have timeout/cancellation/cleanup | IN PROGRESS | |
| Shutdown terminates owned children | IN PROGRESS | |
| Startup is staged | IN PROGRESS | |
| Winget outcomes are distinguished | IN PROGRESS | |
| Crash/timeout does not trigger silent retry | IN PROGRESS | |
| Watchdog hard deadline is not output-idle kill | IN PROGRESS | |
| Batch returns to idle | IN PROGRESS | |
| Parser fails explicitly on malformed tables | IN PROGRESS | |
| Parser validates columns / optional Source | IN PROGRESS | |
| Uncertain versions remain safe | IN PROGRESS | |
| Config defaults deep copied | IN PROGRESS | |
| Config writes atomic | IN PROGRESS | |
| PAT writes debounced | IN PROGRESS | |
| Redirect targets constrained | IN PROGRESS | |
| Session/lifecycle diagnostics | IN PROGRESS | |
| Clean-exit marker | IN PROGRESS | |
| Bytecode/cache artifacts removed | IN PROGRESS | |
| Dependencies split/constrained | IN PROGRESS | |
| No CI workflow required | VERIFIED | User constraint; branch will not add `.github/workflows` |
