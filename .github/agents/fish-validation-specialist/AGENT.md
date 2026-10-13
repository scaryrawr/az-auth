---
name: fish-validation-specialist
description: Validate fish plugin changes using syntax checks and lightweight smoke tests.
---

# fish-validation-specialist

Use this agent when users ask to verify or test changes in this repository.

## Validation workflow
1. Check each fish file separately:
   - `for file in functions/*.fish completions/*.fish; do fish --no-execute "$file" || exit; done`
2. Run `python3 tests/run.py`, with `AZ_AUTH_PWSH` for a portable PowerShell executable if needed.
3. Use the suite's temporary homes and external fixtures. Do not run smoke tests against real user configuration or assume a fish `az` function stubs the Node core.
4. Confirm writer usage, append defaults, and project writer behavior remain covered.

## Reporting
- Return clear pass/fail results and the first actionable error.
