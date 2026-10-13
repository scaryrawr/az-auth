#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
node = os.environ.get("AZ_AUTH_NODE") or shutil.which("node")
if not node:
    sys.exit("Node 22 or newer is required.")
required = ("pwsh",) if os.name == "nt" else ("fish", "bash", "zsh", "pwsh")
for shell in required:
    executable = os.environ.get("AZ_AUTH_PWSH") if shell == "pwsh" else None
    executable = executable or shutil.which(shell)
    if not executable or not Path(executable).is_file():
        sys.exit(f"{shell} is required for the full conformance suite.")
print("Testing shells: " + ", ".join(required) + "; core: Node.js", flush=True)
subprocess.run([node, "--test", str(ROOT / "tests/core.test.cjs")], check=True)
env = os.environ | {"AZ_AUTH_NODE": node, "AZ_AUTH_CORE": str(ROOT / "functions/az-auth-core.cjs")}
with tempfile.TemporaryDirectory(prefix="az-auth-tests-") as directory:
    if os.name == "nt":
        csc = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        fixture = str(Path(directory) / "fixture.exe")
        subprocess.run([str(csc), "/nologo", "/r:System.Web.Extensions.dll", f"/out:{fixture}",
                        str(ROOT / "tests/fixture.cs")], check=True)
        env["AZ_AUTH_FIXTURE"] = fixture
    else:
        env["AZ_AUTH_FIXTURE"] = str(ROOT / "tests/fixture.cjs")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, env=env,
    )
    sys.exit(result.returncode)
