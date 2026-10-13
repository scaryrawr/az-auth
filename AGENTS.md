# Repository guidance

## Runtime and ownership

Node.js 22 or newer is the approved runtime. There is no Go implementation or build step.
`functions/az-auth-core.cjs` owns action classification, effective configuration, credential acquisition, child execution, and npm configuration writes.
Keep fish, PowerShell, Bash, and zsh adapters thin.
Fisher copies the core alongside the fish functions. Resolve it relative to the adapter file, not the current directory or a separately installed binary.
`shell/az-auth.sh` is shared by Bash and zsh. PowerShell exports are defined by `powershell/AzAuthHelpers.psd1`.

## Behavioral contracts

JavaScript authentication requires both a registry-capable action and an effective registry with credentials referencing `ARTIFACTS_ACCESSTOKEN`.
Home authentication entries alone do not select a registry.
Preserve argv, manager streams and status, and caller environment variables.
Pass new credentials only to the child. Never return tokens through a stdout protocol.
Completion always substitutes `__fish_completion_placeholder__` without calling Azure.
Keep the Azure Artifacts resource ID unchanged.
Keep explicit-feed `write-npm` append-only with its existing username and email defaults.
NuGet requires a separately installed credential provider. Never download one automatically.
Shell startup, sourcing, and module import must stay silent and must not invoke Node or Azure.
See `docs/policy.md` for supported configuration and parser limits.

## Validation

Run `python3 tests/run.py` for the Node tests and shell conformance suite.
Unix requires fish, Bash, zsh, and PowerShell. Windows requires PowerShell.
Use `AZ_AUTH_PWSH` for a portable PowerShell executable.
Tests use temporary homes and fake applications, not real Azure or user configuration.
The core resolves applications from `PATH`; shell-function stubs cannot replace its executables.
`tests/test_wrappers.py` covers fish policy and completion; `tests/test_conformance.py` covers the core and every shell. `tests/core.test.cjs` checks Windows shim resolution.
Native Windows execution requires the Windows CI job. Unix PowerShell wrappers use host streams rather than the object pipeline; do not mistake that documented limitation for pipeline support.

Check each fish file individually:

```sh
for file in functions/*.fish completions/*.fish; do fish --no-execute "$file" || exit; done
bash -n shell/az-auth.sh
zsh -n shell/az-auth.sh
node --check functions/az-auth-core.cjs
node --check bin/az-auth-core
node --check tests/fixture.cjs
git diff --check
```

For fish formatting, use `fish_indent`. No JavaScript formatter or dependency-install step is configured.
