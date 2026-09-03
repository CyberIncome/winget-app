# Multi-Provider Update Architecture

## Goal

Evolve Winget Universal Dashboard from a WinGet-focused updater into a Windows
update control plane that can discover updates from multiple owning ecosystems
without pretending that every update is a WinGet package.

The provider boundary is an authority boundary. Detection, identity, execution,
progress, errors, and handoff behavior stay owned by the provider that produced
the update record.

## Non-negotiable invariants

1. **Provider identity is part of update identity.** `steam:1234` and
   `winget:1234` are unrelated records even if their visible names match.
2. **A scan failure is not zero updates.** Provider failures remain visible in
   the aggregate snapshot.
3. **Command execution requires an exact scanned target.** A provider may not
   silently substitute whatever is newest at execution time.
4. **No cross-provider dispatch.** A provider action must preserve provider id,
   item id, and exact target from the scan that authorized it.
5. **Handoff is different from managed execution.** Launcher-owned ecosystems
   may be detected and surfaced without pretending WUD can safely patch them.
6. **Existing WinGet hardening remains authoritative during migration.** The
   provider WinGet adapter is scan/plan infrastructure until the universal
   dispatcher has Windows lifecycle, progress, cancellation, and confirmation
   acceptance of its own.
7. **No UI automation as an update protocol.** Clicking launcher/browser GUI
   elements is not a supported provider contract.
8. **Project-local developer dependencies are opt-in.** Global tool managers
   can be universal providers; arbitrary project venv/node_modules/etc. must not
   be swept into a system-wide Update All operation.
9. **Credentials are explicit.** Third-party clients that require account auth
   must be opt-in and must use their own supported credential storage.
10. **System/driver/firmware providers are conservative.** Detection may precede
    execution by an entire release tranche when the OS/vendor orchestrator has
    stronger ownership semantics.

## Provider modes

| Mode | Meaning | Universal Update All |
| --- | --- | --- |
| `managed` | WUD can construct a deterministic provider-owned update action | Eligible only after execution acceptance |
| `handoff` | WUD can detect the update but the owning launcher/UI performs it | Never silently included |
| `informational` | WUD can report state only | Never included |

## First implementation tranche

| Provider | Category | Detection | Planned action | Current integration |
| --- | --- | --- | --- | --- |
| WinGet | applications / Store | strict existing WinGet scan | exact id + source + version | adapter only; existing GUI remains execution path |
| Steam | games | local app manifests + Valve UpToDateCheck | open Steam Downloads | read-only/handoff |
| Chocolatey | applications/dev tools | `choco outdated --limit-output` | exact `choco upgrade --version` | scan + plan |
| pipx | dev tools | structured outdated JSON | exact package spec for supported unsuffixed envs | scan + plan, custom envs fail closed |
| npm globals | dev tools | global outdated JSON | exact `package@version` | scan + plan |

`python -m src.providers.cli status` and
`python -m src.providers.cli scan --provider <id>` provide a read-only developer
surface for proving providers before they enter the production GUI.

## Next high-value providers

### Games and launchers

- **Epic Games / Legendary**: optional third-party integration. Legendary can
  inspect and update Epic-owned games, but authentication and credential
  ownership require explicit opt-in. Do not silently bundle or authenticate it.
- **EA app, Ubisoft Connect, Battle.net, Rockstar**: begin with local detection
  if a stable machine-readable source exists and hand off to the owning launcher.
  Promote to managed only if a documented deterministic update interface exists.
- **GOG Galaxy**: same detect/handoff rule; do not scrape the launcher UI.

### Windows and Microsoft

- **Microsoft Store**: prefer the existing WinGet `msstore` source where package
  identity/targets are available; keep Store provenance visible as its own
  category even when transport is WinGet.
- **Windows Update**: detect-first using supported Windows Update APIs. Direct
  installation is deferred because Windows Settings/Update Orchestrator owns
  reboot, policy, and servicing coordination.
- **Microsoft Defender platform/signatures**: candidate system-maintenance
  provider, kept separate from ordinary application updates.
- **WSL runtime**: expose WSL version/status once a reliable read-only latest
  comparison is available. `wsl --update` alone is not enough to prove an
  update exists.
- **Visual Studio Installer**: candidate managed provider after exact instance
  identity and update-target behavior are proven.
- **VS Code / Cursor extensions**: candidate extension providers. Enumeration
  and mutation must be separated so a scan does not update extensions.
- **PowerShell modules / PSResourceGet**: candidate development provider with
  repository/package provenance and explicit scope handling.
- **.NET global tools**: candidate development provider; never sweep project
  tool manifests into global Update All by default.

### Other package managers and developer runtimes

- **Scoop**: strong candidate, but repository metadata refresh (`scoop update`)
  mutates local bucket metadata. Treat that mutation explicitly instead of
  calling it a purely read-only scan.
- **pnpm globals** and other global Node tool stores: candidate when current and
  target versions can be queried separately from execution.
- **uv tools**: candidate Python tool provider, distinct from arbitrary project
  environments.
- **Rustup**: candidate runtime/toolchain provider; toolchain/component updates
  should not be confused with Cargo project dependencies.
- **Conda/Mamba**: opt-in environments only. Base/global environment may be
  manageable; per-project envs should not be silently updated.
- **RubyGems global tools**, **Go-installed tools**, and similar ecosystems:
  require a stable installed-versus-latest query before inclusion.

### Drivers and firmware

These are valuable but higher-risk and should start as separate provider groups:

- Windows Update driver catalog / optional driver updates
- NVIDIA / AMD / Intel graphics tooling
- Dell Command Update
- Lenovo System Update / Commercial Vantage tooling
- HP Image Assistant
- OEM BIOS, dock, Thunderbolt, chipset, and peripheral firmware

A driver/firmware provider must preserve hardware identity, applicability,
power/reboot requirements, and vendor ownership. Generic scraping of vendor web
pages is not acceptable update authority.

### Self-updaters and maintenance surfaces

Potentially useful status/handoff providers include:

- Docker Desktop and container tooling
- browser binaries and, separately, browser extensions
- Office Click-to-Run
- game launchers themselves
- printer/peripheral management suites
- database/local-server runtimes
- language runtime managers

These should not be counted twice when the binary is already actionable through
WinGet. Provider-level deduplication must preserve ownership/provenance instead of
merging by display name alone.

## Planned phases

### Phase A - contracts and read-only proof

- normalized provider types and authority modes
- provider registry
- provider-local failures
- aggregate snapshot
- read-only provider CLI
- WinGet adapter
- Steam / Chocolatey / pipx / npm provider parsers and plans

### Phase B - Windows acceptance and provider status UI

- run provider parser/registry tests on Windows
- exercise read-only provider CLI against the real machine
- add a Providers page with availability, capability, warning, and scan state
- do not alter the existing Updates table or Update Selected dispatch yet

### Phase C - universal update model

- join provider snapshots into a provider-aware table model
- preserve provider/category columns and filters
- provider-scoped selection identity
- managed / handoff / blocked visual states
- per-provider and universal counts with partial-scan warnings

### Phase D - execution dispatcher

- provider-owned command execution with process-tree containment
- confirmation/elevation policy
- exact-target revalidation before launch
- provider-specific progress parsers
- handoff actions kept separate from executable actions
- mixed-provider batch result tracking

### Phase E - expansion

- Epic optional integration
- Scoop and Microsoft surfaces
- extension/runtime managers
- Windows Update detection
- vendor driver/firmware providers after contract-specific research

## Release rule

No provider is called "managed" in the production GUI merely because a command
exists. It must have parser tests, exact-target tests, identity/dispatch tests,
real Windows scan evidence, cancellation/shutdown behavior where applicable, and
provider-specific execution acceptance before it joins Universal Update All.
