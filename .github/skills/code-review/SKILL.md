---
name: code-review
description: Review pull requests in this repository for shared Azure authentication policy, shell compatibility, credential isolation, and configuration-write regressions.
---

# Review Azure auth wrapper pull requests

## Trace the affected contract

Read the diff and the applicable limits in `docs/policy.md`. Use `AGENTS.md` for runtime requirements and validation commands.

- For `functions/az-auth-core.cjs`, trace `classify`, `registryConfiguration`, `hasFeed`, and `run`. Inspect `tests/test_wrappers.py` for aliases, option values, runner boundaries, config precedence, and home auth-only fixtures. Authentication must require both an eligible action and a selected token-backed registry. Check that the longest matching credential path and literal overrides select the effective credential.
- For credential acquisition or child execution, inspect `tests/test_conformance.py`. Verify exact argv, streams, status, inherited environment, failure before manager execution, and cancellation. New tokens must remain in the child environment, not a shell protocol or diagnostic output.
- For fish files or completions, apply `.github/skills/review-fish-wrapper-changes/SKILL.md`.
- For `shell/az-auth.sh` or `powershell/`, inspect initialization, source-relative path, repeated-load, and argument-preservation cases in `tests/test_conformance.py`. Exercise Bash through `BASH_ENV` and zsh through `.zshenv`, not only interactive shells. Compare PowerShell exports with its manifest and documented host-stream limitation.
- For Windows launcher changes, inspect `tests/core.test.cjs` and the Windows execution case in `tests/test_conformance.py`. Ensure arguments remain arrays. Shim-resolution tests on Unix do not establish Windows runtime compatibility.
- For NuGet or Rush changes, inspect effective-source and Rush-root fixtures. Check clear/disabled-source semantics, explicit overrides, local actions, and the credential-provider prerequisite. Do not introduce automatic provider installation.
- For `write-npm`, inspect append-default and project-writer cases. Preserve unrelated user configuration and confirmation before replacing conflicting entries.

## Establish evidence

Run the applicable checks from `AGENTS.md` using isolated external fixtures. For cross-shell or core changes, run the full conformance suite. Check `.github/workflows/ci.yml` when platform coverage changes; distinguish locally verified behavior from a Windows-only check awaiting CI.

Report actionable contract violations with the affected invocation, configuration, and observed or reasoned failure. A documented unsupported parser format alone is not a regression. Identify missing evidence plainly rather than claiming a platform passed.
