---
name: validate-fish-plugin
description: Validate fish wrapper and completion changes with syntax and smoke checks.
---

# Validate fish plugin changes

1. Check every file separately. A glob passed as fish script arguments checks only the first file.
   - `for file in functions/*.fish completions/*.fish; do fish --no-execute "$file" || exit; done`
2. Run `python3 tests/run.py`. Use `AZ_AUTH_PWSH` when PowerShell is not on `PATH`.
3. Confirm the suite exercises authenticated and local actions, exact argv, Azure failures, inherited credentials, completion placeholders, and writer usage.
4. If an individual smoke check is needed, use fake external applications on `PATH` and a temporary `HOME`, as the test suite does. A fish `az` function cannot stub the Node core's external Azure CLI.

Report failures with the exact command and first failing output.
