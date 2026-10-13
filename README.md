# Azure auth wrappers

One Node.js core owns authentication policy for fish, PowerShell, Bash, and zsh.
The shell functions forward arguments to the core.
Authentication runs only for package-feed actions with an effective token-backed registry.
Home `.npmrc` authentication entries alone do not select a feed.

## Install dependencies

Install Node.js 22 or newer on `PATH`.
The core uses only Node's built-in modules.
There is no build step, npm dependency installation, or Go dependency.
Install the package managers you use.
For authenticated operations, install [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) and run `az login`.
NuGet operations also require a separately installed [Azure Artifacts Credential Provider](https://github.com/microsoft/artifacts-credprovider).
The wrappers never download or install a provider.

## Install fish, the default entrypoint

```fish
fisher install scaryrawr/az-auth.fish
```

Fisher copies `functions/az-auth-core.cjs` alongside the fish functions.
The fish helper resolves the core relative to its own installed file, not the working directory.
No separate core installation is needed.
Wrappers return status 127 with installation guidance if Node or the core file is missing.

## Load Bash or zsh

Keep a checkout at a stable absolute path.
Source its entrypoint in the current shell.

```sh
git clone https://github.com/scaryrawr/az-auth.fish.git /absolute/path/az-auth.fish
. /absolute/path/az-auth.fish/shell/az-auth.sh
```

Both adapters resolve the same `functions/az-auth-core.cjs` relative to the checkout.
They do not require `bin/az-auth-core` on `PATH`.

For noninteractive Bash subshells, set `BASH_ENV` to that absolute file path in your chosen startup file.

```sh
export BASH_ENV=/absolute/path/az-auth.fish/shell/az-auth.sh
```

For zsh, add the source command to `$ZDOTDIR/.zshenv`, or `$HOME/.zshenv` when `ZDOTDIR` is unset.
Do not use `zsh -f` when you want startup files loaded.
These entrypoints work regardless of the `SHELL` variable.
They do not modify `PATH`, export `BASH_ENV`, set shell options, install traps, or run the core during initialization.
Repeated sourcing is silent and idempotent.

## Import PowerShell

Use PowerShell 7.3 or newer.

```powershell
Import-Module /absolute/path/az-auth.fish/powershell/AzAuthHelpers.psd1
```

Add that import to your profile if you want persistent functions.
To migrate from `az-auth-helpers.pwsh`, remove its old profile import and unload the old module before importing this one.
The exported functions include `npm`, `npx`, `pnpm`, `pnpx`, `pn`, `yarn`, `bun`, `corepack`, `dotnet`, `nuget`, `rush`, `Invoke-RushPnpm`, `rush-pnpm`, and `write-npm`.
Import defines functions and an alias only.
It never changes process environment variables.

On Windows, the module invokes Node with standard native argument passing.
On Unix, it uses a direct process invocation to prevent PowerShell from expanding splatted wildcard arguments.
Unix PowerShell output goes directly to the host's standard streams, not the PowerShell object pipeline.
Use the core directly when PowerShell pipeline processing is needed on Unix.

The checkout also provides `bin/az-auth-core` for direct Unix invocation.
On every platform, including Windows, you can invoke the same core through Node.

```sh
node /absolute/path/az-auth.fish/functions/az-auth-core.cjs run --manager npm -- install
```

Standard Windows npm-family `.cmd` shims are resolved to Node and their underlying JavaScript entrypoint.
The Azure CLI Python `az.cmd` launcher is also supported.
Arguments are never concatenated into a `cmd.exe /c` string.
Unrecognized batch files and `.ps1` command wrappers fail with guidance.

## Configure npm authentication entries

The explicit-feed writer keeps the fish append-only behavior and defaults.
It writes six authentication lines to `$HOME/.npmrc` without selecting a registry or fetching a token.

```fish
write-npm pkgs.dev.azure.com/org/project/_packaging/feed/npm
```

Its signature is `write-npm FEED [USER [EMAIL]]`.
Defaults are `AzCliToken` and `not-used@example.com`.
Supply the feed without a protocol or trailing slash, as in the example.
Repeated explicit-feed calls append again.
Legacy feed strings are appended verbatim, including strings ending in `/registry`.
Use the feed base in the example to avoid adding `/registry` twice.
The project `.npmrc` must separately select the feed with a `registry` or scoped registry setting.

PowerShell's no-argument `write-npm` uses `az-auth-core write-npm --from-project`.
It reads the current directory's `.npmrc`, requires an HTTPS Azure Artifacts registry, and writes user authentication entries.
Existing matching entries are left unchanged.
Conflicting entries require a `y` response before replacement.
Unrelated user configuration is preserved.
No-argument fish and Bash writers return usage with a nonzero status.

## Authentication policy

See [supported actions, configuration precedence, and limits](docs/policy.md).
The core never prints a token for a shell to capture.
It passes tokens only in the child environment and preserves manager arguments, standard streams, and exit status.
Completion always substitutes `__fish_completion_placeholder__`, even if a secret is inherited.
There are no runtime network retries or credential caches.

## Verify

Tests use temporary homes and fake external executables.
They do not install packages or contact Azure.

```sh
python3 tests/run.py
node --check functions/az-auth-core.cjs
node --check bin/az-auth-core
node --check tests/fixture.cjs
for file in functions/*.fish completions/*.fish; do fish --no-execute "$file" || exit; done
bash -n shell/az-auth.sh
zsh -n shell/az-auth.sh
git diff --check
```

The Python runner requires fish, Bash, zsh, and PowerShell on Unix, and PowerShell on Windows.
Set `AZ_AUTH_PWSH` to an absolute portable `pwsh` executable when it is not on `PATH`.
It uses a real Node runtime with executable fixtures in an isolated plugin copy.
On Windows, it compiles a temporary .NET fixture for native command tests.
CI runs the Node core and all four shells on Linux and macOS, plus Node and PowerShell on Windows.
Windows launcher execution tests run only on Windows.
