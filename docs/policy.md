# Authentication policy

## Core contract

```text
az-auth-core run --manager MANAGER -- ORIGINAL_ARGV...
az-auth-core complete --manager pnpm -- COMPLETION_ARGV...
az-auth-core write-npm -- FEED [USER [EMAIL]]
az-auth-core write-npm --from-project
```

`pn` dispatches to `pnpm`.
Other managers retain their executable name.
The core resolves external executables from `PATH`, not shell functions.
Node launches the manager without a shell and waits for it on both Unix and Windows.
The manager inherits standard input, standard output, and standard error.
On Unix, the core forwards SIGINT, SIGTERM, SIGHUP, and SIGQUIT to its current child.
On Windows, console cancellation depends on the native console process group.
PowerShell on Unix starts Node directly and preserves host streams rather than the object pipeline.

The runtime is Node.js 22 or newer.
The shell adapters resolve `functions/az-auth-core.cjs` relative to their own files.
The Unix `bin/az-auth-core` launcher invokes the same module.
Windows native executables run directly.
Known Node package-manager `.cmd` shims and Azure CLI's Python `az.cmd` are resolved to their entrypoints.
Unknown batch and PowerShell launchers fail instead of concatenating arguments into a command string.

The policy uses the invocation's manager, arguments, working directory, and environment.
It classifies the action, reads effective registry and credential settings, then selects pass-through, token-required, or a nonsecret placeholder.
Only the child environment receives new credentials.
Non-authenticated commands preserve explicitly supplied environment variables.

For a token-required invocation, a nonempty inherited `ARTIFACTS_ACCESSTOKEN` is reused.
NuGet can also reuse `VSS_NUGET_ACCESSTOKEN`.
Otherwise, the core captures Azure CLI output internally using:

```text
az account get-access-token --resource 499b84ac-1321-427f-aa17-267ca6975798 --query accessToken -o tsv
```

Azure CLI failure stops before manager execution and preserves its nonzero exit status.
An empty or whitespace-only returned token fails with status 1.
The core has no token-returning stdout command, retry loop, or credential cache.

## JavaScript actions

These action groups include their existing aliases.
The independently specified regression matrix in `tests/test_wrappers.py` lists the exact alias cases.

| Manager | Registry-capable actions |
| --- | --- |
| `npm` | `install`, `ci`, `update`, `outdated`, `audit`, `view`, `search`, `ping`, `whoami`, `publish`, `unpublish`, `access`, `dist-tag`, `dist-tags`, `owner`, `stars`, `star`, and `unstar`. |
| `pnpm` and `pn` | `install`, `add`, `update`, `remove`, `outdated`, `audit`, `view`, `search`, `ping`, `whoami`, `publish`, `unpublish`, `dist-tag`, `owner`, `fetch`, `patch`, `import`, `store add`, and `dlx`. Recursive and filtered commands use the delegated action. |
| `yarn` | `install`, `add`, `up`, `upgrade`, `upgrade-interactive`, `remove`, `outdated`, `audit`, `info`, `publish`, `tag`, `owner`, and `dlx`. Its `npm` actions include `audit`, `info`, `publish`, `whoami`, `login`, `logout`, and `tag`. `workspace` and `workspaces foreach` use the delegated action. |
| `bun` | `install`, `add`, `update`, `remove`, `publish`, `outdated`, and `x`. |
| `npx` and `pnpx` | Package execution can download a package. `npx --no-install`, `npx --no`, and `npx --yes=false` skip authentication. `bun x --no-install` also skips it. |
| `corepack` | Delegated `npm`, `npx`, `pnpm`, `pnpx`, and `yarn` commands use the delegated manager's policy, including version-qualified names. Maintenance commands skip authentication. |

With no action, `pnpm`, `pn`, and `yarn` use the install policy.
Bare `npm`, `bun`, `npx`, `pnpx`, and `corepack` do not fetch a token.
Option-only `npx` and `pnpx` invocations also skip authentication unless they explicitly request a package with `--package` or `-p`.
Local `run`, `build`, `test`, `exec`, help, version, configuration, maintenance, and unknown actions do not fetch a token.
For example, `npm run install` is local.

Common separate-value options include `--cwd`, `-C`, `--prefix`, `--filter`, `-F`, `--registry`, `--userconfig`, and `--globalconfig`.
`--option=value` and boolean flags are accepted.
Help and version flags stop authentication only while the manager parses them.
Arguments after `--`, or after a download runner's package name, are not inspected as manager flags or configuration overrides.
Unknown options with separate values remain outside this policy.

## JavaScript configuration

Auth entries alone do not trigger token acquisition.
The effective default registry or a configured scope must match a credential reference to `ARTIFACTS_ACCESSTOKEN`.
URL path matching keeps `/feed/` distinct from `/feed-other/`.
Registry schemes and hosts are case-insensitive; paths remain case-sensitive.
An effective literal credential overrides an inherited placeholder reference at the same key.
When several URL credentials match a registry, the longest path selects the effective credential.

The supported sources are:

- npm global, user, and project `.npmrc`, in that order. CLI registry settings override environment settings and files. Scoped CLI settings such as `--@private:registry=URL` override that scope.
- `--globalconfig`, `--userconfig`, and their `npm_config_*` environment settings select file locations. Uppercase environment forms are supported. `npm_config_prefix`, `npm_config_registry`, and `npm_config_global` are also supported.
- The project `.npmrc` at the nearest ancestor containing `package.json` or `node_modules`, or the working directory if neither exists. An arbitrary outer `.npmrc` is not project configuration. Global mode skips the project file. pnpm uses the nearest `pnpm-workspace.yaml` root when present.
- `PREFIX/etc/npmrc` when supplied. Otherwise, the prefix is estimated from the `node` executable's location. Custom global layouts can require explicit `--globalconfig`.
- Yarn `.yarnrc.yml` files in parent directories, with nearer files taking precedence. Standard two-space `npmScopes` and `npmRegistries` mappings, `npmRegistryServer`, and `npmAuthToken` are supported.
- Bun's home `.bunfig.toml` and working-directory `.bunfig.toml` or `bunfig.toml`. Simple `[install]` registry values, inline registry objects, and `[install.scopes]` URL and token settings are supported.

Comments and unrelated token-variable references do not count as credentials.
A configured token-backed scope counts even for public dependencies.
The detector does not resolve dependencies or inspect scripts.
Unreadable or oversized configuration files return an error rather than guessing credentials.

This is a bounded parser, not a complete package-manager configuration implementation.
Unsupported settings include npm built-in config, pnpm `auth.ini` or `config.yaml`, Yarn YAML anchors and custom indentation, multiline Bun objects, and environment-expanded registry URLs.
Scoped environment names and native `YARN_*` and `BUN_*` overrides are not resolved.

When Yarn configuration requires token interpolation and the variable is absent, local commands receive `__fish_completion_placeholder__`.
An explicitly supplied value, including an empty string, is preserved on no-auth paths.
Other local commands do not receive a placeholder.
pnpm completion always receives the placeholder and never invokes Azure CLI.

## Rush

`rush install`, `rush update`, and `rush add` use the registry policy.
`rush build`, `rush rebuild`, `rush purge`, and other local commands do not fetch a token.
`rush-pnpm` uses the pnpm action policy while executing `rush-pnpm`.

The nearest ancestor with `rush.json` selects the Rush root.
`common/config/rush/.npmrc` and then `config/rush/.npmrc` override ordinary project settings.
CLI registry overrides still take precedence.
Custom Rush commands, generated temporary configs, and Rush-specific environment or project-selection overrides are not interpreted.

## NuGet

`dotnet restore` and implicit-restore `build`, `test`, `run`, `pack`, and `publish` qualify unless `--no-restore` is supplied before `--`.
`nuget restore`, `nuget install`, and `nuget update` qualify.
NuGet action names are case-insensitive. Other managers retain their case-sensitive action policy.
Local information, help, version, and other actions do not inspect the credential provider or fetch tokens.
Both managers recognize `-?` as a local help switch.

Effective sources come from the user config and then ancestor configs, root to working directory.
User config is `$APPDATA/NuGet/NuGet.Config` when `APPDATA` is set, otherwise `$HOME/.nuget/NuGet/NuGet.Config`.
Ancestor filenames are `NuGet.config`, `nuget.config`, and `NuGet.Config`.
XML `packageSources` and `disabledPackageSources` support `add`, `remove`, and `clear`.
Disabled sources are excluded.

`--configfile` or NuGet's `-ConfigFile` selects one explicit configuration file instead of the discovered hierarchy.
`--source`, `-s`, or NuGet's `-Source` overrides configured sources.
Repeated source options and semicolon-separated source lists are supported.
Named sources resolve through the effective config.
An explicitly selected named source can override its disabled setting.

Only actual HTTPS URLs at `pkgs.dev.azure.com` or a subdomain of `pkgs.visualstudio.com` qualify.
Userinfo, query strings, and fragments do not qualify.
An auth invocation requires `CredentialProvider.Microsoft.dll` for dotnet or `CredentialProvider.Microsoft.exe` for NuGet under `$HOME/.nuget/plugins`.
Alternatively, `NUGET_PLUGIN_PATHS` can select an existing provider file.
Separate multiple plugin paths with the platform path-list delimiter, `:` on Unix or `;` on Windows.
This is a file-presence check, not a guarantee of provider compatibility or execution permissions.

The child receives `VSS_NUGET_ACCESSTOKEN` and `VSS_NUGET_URI_PREFIXES` built from the effective Azure sources, plus `ARTIFACTS_ACCESSTOKEN`.
An inherited `VSS_NUGET_URI_PREFIXES` does not activate authentication and is replaced on an authenticated invocation.
No provider is downloaded or executed by the core.

Machine-wide NuGet configs, extra user config directories, environment expansion in XML, MSBuild properties, project or solution file discovery, package-source mapping, and custom restore targets are not interpreted.
Discovery starts from the invocation's working directory, not a project argument or `--project`.
Implicit restore can also happen through commands or flags outside this bounded action list.

## Credential inheritance

Authenticated package-manager operations pass credentials to their lifecycle scripts.
Local scripts can invoke installers themselves.
The wrappers do not infer script behavior or remove credentials from manager-owned child processes.
Sourced Bash subshells can reenter the wrapper policy, but a non-auth action still preserves an explicitly inherited token.
