---
name: review-fish-wrapper-changes
description: Review fish wrapper changes for token injection consistency and safe argument passthrough.
---

# Review fish wrapper changes

1. Read the shared policy and execution checks in `.github/skills/code-review/SKILL.md` once. This workflow supplies the fish-specific checks; do not recursively invoke the two skills.
2. Trace changed wrappers through `__az_artifacts_core`. Confirm `$argv` reaches Node without string reconstruction or fish-side policy.
3. Inspect `functions/__az_artifacts_core.fish` and the isolated plugin-copy tests. The core must resolve beside the installed helper after the caller changes directories.
4. For `completions/pnpm.fish`, inspect `test_completion_never_fetches_or_exposes_token` in `tests/test_wrappers.py`. Check placeholder substitution with an inherited secret, zero Azure calls, argument boundaries, and fish file-completion output.
5. Run the per-file fish syntax loop and behavioral suite listed in `AGENTS.md`. A multi-file `fish --no-execute` invocation checks only its first script.

Report a finding only when the changed behavior violates a documented contract or a reproduced caller-visible expectation. Skip style-only comments.
