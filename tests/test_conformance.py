import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = os.environ.get("AZ_AUTH_CORE")
FIXTURE = os.environ.get("AZ_AUTH_FIXTURE")
NODE = os.environ.get("AZ_AUTH_NODE") or shutil.which("node")
MANAGERS = ("npm", "npx", "pnpm", "pnpx", "pn", "yarn", "bun", "corepack",
            "dotnet", "nuget", "rush", "rush-pnpm")
PWSH = os.environ.get("AZ_AUTH_PWSH") or shutil.which("pwsh")
SHELLS = ["core"]
if os.name != "nt":
    SHELLS += [shell for shell in ("fish", "bash", "zsh") if shutil.which(shell)]
if PWSH:
    SHELLS += ["pwsh"]


@unittest.skipUnless(CORE and FIXTURE, "run with python3 tests/run.py")
class ConformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "package.json").write_text("{}")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        suffix = ".exe" if os.name == "nt" else ""
        self.plugin = self.root / "plugin"
        for directory in ("functions", "completions", "shell", "powershell"):
            shutil.copytree(ROOT / directory, self.plugin / directory)
        self.core = self.plugin / "functions/az-auth-core.cjs"
        for manager in (*MANAGERS, "az", "python"):
            shutil.copy2(FIXTURE, self.bin / (manager + suffix))
        if os.name == "nt":
            shutil.copy2(NODE, self.bin / "node.exe")
        else:
            (self.bin / "node").symlink_to(NODE)
            for shell in ("bash", "zsh"):
                if shutil.which(shell):
                    (self.bin / shell).symlink_to(shutil.which(shell))
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "APPDATA": str(self.home / "AppData"),
            "XDG_CONFIG_HOME": str(self.home), "TEST_LOG": str(self.log),
            "TEST_ROOT": str(self.plugin), "SHELL": "/a/different/login/shell",
            "ZDOTDIR": str(self.home),
        }
        for key in ("SystemRoot", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
            if key in os.environ:
                self.env[key] = os.environ[key]
        self.auth()

    def auth(self, registry=True):
        (self.home / ".npmrc").write_text(
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n" +
            ("registry=https://private.invalid/feed/\n" if registry else "")
        )

    def argv(self, shell, manager, args, code=None):
        if shell == "core":
            return [NODE, str(self.core),
                    "run", "--manager", manager, "--", *args]
        if shell == "fish":
            script = 'set -g fish_function_path "$TEST_ROOT/functions" $fish_function_path\n'
            script += code or '$argv[1] $argv[2..-1]'
            return [shutil.which("fish"), "--no-config", "-c", script, manager, *args]
        if shell in ("bash", "zsh"):
            script = '. "$TEST_ROOT/shell/az-auth.sh"\n'
            script += code or '"$@"'
            return [shutil.which(shell), "-c", script, "fixture", manager, *args]
        script = "Import-Module (Join-Path $env:TEST_ROOT 'powershell/AzAuthHelpers.psd1') -Force\n"
        script += code or '$a = @(ConvertFrom-Json $env:TEST_ARGS); & $env:TEST_MANAGER @a; exit $LASTEXITCODE'
        return [PWSH, "-NoProfile", "-NonInteractive", "-Command", script]

    def invoke(self, shell, manager, args=(), extra=None, code=None, stdin=""):
        self.log.unlink(missing_ok=True)
        env = self.env | {"TEST_MANAGER": manager, "TEST_ARGS": json.dumps(args)} | (extra or {})
        result = subprocess.run(self.argv(shell, manager, args, code), cwd=self.project,
                                env=env, text=True, input=stdin, capture_output=True)
        return result, self.calls()

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def check(self, shell, manager, args, auth, extra=None, token=None):
        result, calls = self.invoke(shell, manager, args, extra)
        self.assertEqual(result.returncode, 0, (shell, manager, args, result.stderr))
        self.assertEqual([c["command"] for c in calls],
                         (["az"] if auth else []) + ["pnpm" if manager == "pn" else manager],
                         (shell, manager, args, calls))
        self.assertEqual(calls[-1]["args"], list(args), calls)
        self.assertEqual(calls[-1]["env"]["ARTIFACTS_ACCESSTOKEN"],
                         token or ("fixture-token" if auth else None), calls)
        return calls

    def test_all_shells_and_managers(self):
        for shell in SHELLS:
            for manager in MANAGERS:
                with self.subTest(shell=shell, manager=manager):
                    self.check(shell, manager, ["--version"], False)
                    if manager in ("dotnet", "nuget"):
                        continue
                    args = ["pnpm", "install"] if manager == "corepack" else ["install"]
                    self.check(shell, manager, args, True)
                    self.check(shell, manager, args, False,
                               {"ARTIFACTS_ACCESSTOKEN": "caller"}, "caller")

    def test_exact_arguments_streams_exit_and_parent_env(self):
        args = ["install", "", "a b", "line\nbreak", 'a"b', "$(touch nope)", "&x", "%PATH%", "!", "^", "|", "<", ">", "*"]
        for shell in SHELLS:
            with self.subTest(shell=shell):
                result, calls = self.invoke(shell, "npm", args,
                    {"TEST_IO": "yes", "TEST_MANAGER_STATUS": "37"}, stdin="stdin payload\n")
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertEqual(result.stdout, "manager stdout\nstdin payload\n")
                self.assertEqual(result.stderr, "manager stderr\n")
                self.assertEqual(calls[-1]["args"], args)
                self.assertEqual(calls[-1]["env"]["ARTIFACTS_ACCESSTOKEN"], "fixture-token")
                if shell == "core":
                    continue
                code = {
                    "fish": 'npm install; npm run build; set -q ARTIFACTS_ACCESSTOKEN; and exit 99; exit 0',
                    "bash": 'npm install; npm run build; test "${ARTIFACTS_ACCESSTOKEN+x}" != x',
                    "zsh": 'npm install; npm run build; test "${ARTIFACTS_ACCESSTOKEN+x}" != x',
                    "pwsh": 'npm install; npm run build; if (Test-Path env:ARTIFACTS_ACCESSTOKEN) { exit 99 }; exit 0',
                }[shell]
                result, calls = self.invoke(shell, "npm", code=code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([c["env"]["ARTIFACTS_ACCESSTOKEN"] for c in calls if c["command"] == "npm"],
                                 ["fixture-token", None])

    def test_registry_selection_and_runner_boundaries(self):
        self.auth(registry=False)
        for shell in SHELLS:
            with self.subTest(shell=shell):
                self.check(shell, "npm", ["install"], False)
                (self.project / ".npmrc").write_text("registry=https://private.invalid/feed/\n")
                self.check(shell, "npm", ["install"], True)
                self.check(shell, "npm", ["install", "--registry=https://registry.npmjs.org/"], False)
                self.check(shell, "npm", ["run", "install"], False)
                self.check(shell, "npx", ["tool", "--help", "--registry=https://registry.npmjs.org/"], True)
                self.check(shell, "pnpm", ["dlx", "--package", "tool", "target", "--registry=https://registry.npmjs.org/"], True)
                self.check(shell, "bun", ["x", "--no-install", "tool"], False)
                (self.project / ".npmrc").unlink()

    def test_effective_credentials_use_longest_registry_path(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                (self.project / ".npmrc").write_text(
                    "registry=https://private.invalid/feed/nested/\n"
                    "//private.invalid/feed/nested/:_authToken=literal-token\n"
                )
                self.check(shell, "npm", ["install"], False)
                (self.project / ".npmrc").write_text(
                    "registry=https://private.invalid/feed/nested/\n"
                    "//private.invalid/feed/nested/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
                )
                self.check(shell, "npm", ["install"], True)
        (self.project / ".npmrc").unlink()

    def test_missing_node_and_manager_are_explicit(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                result, calls = self.invoke(shell, "npm", ["--version"], {"PATH": str(self.root)})
                self.assertEqual(result.returncode, 127, result.stderr)
                self.assertEqual(calls, [])
                if shell != "core":
                    self.assertIn("Node 22 or newer is required", result.stderr)
        (self.bin / ("npm.exe" if os.name == "nt" else "npm")).unlink()
        for shell in SHELLS:
            with self.subTest(shell=shell):
                result, calls = self.invoke(shell, "npm", ["--version"])
                self.assertEqual(result.returncode, 127, result.stderr)
                self.assertIn("npm executable not found", result.stderr)
                self.assertEqual(calls, [])

    def test_source_relative_paths_survive_directory_changes(self):
        for shell in ("bash", "zsh"):
            if shell not in SHELLS:
                continue
            script = '. ../plugin/shell/az-auth.sh; cd ..; npm install'
            result = subprocess.run([shutil.which(shell), "-c", script], cwd=self.project,
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c["command"] for c in self.calls()], ["az", "npm"])
            self.log.unlink()

    def test_writer_through_shell_adapters(self):
        feed = "pkgs.dev.azure.com/org/_packaging/feed/npm"
        for shell in SHELLS:
            with self.subTest(shell=shell):
                self.auth(registry=False)
                original = (self.home / ".npmrc").read_text()
                if shell == "core":
                    result = subprocess.run([NODE, str(self.core), "write-npm", "--", feed, "custom", "me@example.com"],
                                            cwd=self.project, env=self.env, capture_output=True, text=True)
                else:
                    result, calls = self.invoke(shell, "write-npm", [feed, "custom", "me@example.com"])
                    self.assertEqual(calls, [])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.home / ".npmrc").read_text(), original +
                    f"//{feed}/registry/:username=custom\n"
                    f"//{feed}/registry/:_authToken=${{ARTIFACTS_ACCESSTOKEN}}\n"
                    f"//{feed}/registry/:email=me@example.com\n"
                    f"//{feed}/:username=custom\n"
                    f"//{feed}/:_authToken=${{ARTIFACTS_ACCESSTOKEN}}\n"
                    f"//{feed}/:email=me@example.com\n")
        if "pwsh" in SHELLS:
            self.auth(registry=False)
            (self.project / ".npmrc").write_text(f"registry=https://{feed}/registry/\n")
            result, calls = self.invoke("pwsh", "write-npm")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("VssSessionToken", (self.home / ".npmrc").read_text())
            self.assertEqual(calls, [])

    @unittest.skipIf(os.name == "nt", "Unix shebang entrypoint")
    def test_checkout_bin_entrypoint(self):
        result = subprocess.run([str(ROOT / "bin/az-auth-core"), "run", "--manager", "npm", "--", "--version"],
                                cwd=self.project, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["command"] for c in self.calls()], ["npm"])

    def test_fetch_failure_completion_and_no_token_api(self):
        for shell in SHELLS:
            for extra, expected in (({"TEST_AZ_STATUS": "23"}, 23), ({"TEST_AZ_TOKEN": ""}, 1),
                                    ({"TEST_AZ_TOKEN": "  "}, 1)):
                with self.subTest(shell=shell, extra=extra):
                    result, calls = self.invoke(shell, "npm", ["install"], extra)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual([c["command"] for c in calls], ["az"])
                    self.assertNotIn("fixture-token", result.stdout + result.stderr)
        exe = [NODE, str(self.core)]
        self.log.unlink()
        result = subprocess.run([*exe, "complete", "--manager", "pnpm", "--", "completion-server", "--", "", "&"],
                                cwd=self.project, env=self.env | {"ARTIFACTS_ACCESSTOKEN": "secret"}, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0]["env"]["ARTIFACTS_ACCESSTOKEN"], "__fish_completion_placeholder__")
        self.assertEqual(self.calls()[0]["args"], ["completion-server", "--", "", "&"])
        result = subprocess.run([*exe, "token"], env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_initialization_is_silent_idempotent_and_missing_core_is_explicit(self):
        self.core.unlink()
        for shell in SHELLS:
            if shell == "core":
                continue
            code = {
                "fish": 'for f in "$TEST_ROOT"/functions/*.fish; source $f; source $f; end; source "$TEST_ROOT/completions/pnpm.fish"',
                "bash": '. "$TEST_ROOT/shell/az-auth.sh"; . "$TEST_ROOT/shell/az-auth.sh"',
                "zsh": '. "$TEST_ROOT/shell/az-auth.sh"; . "$TEST_ROOT/shell/az-auth.sh"',
                "pwsh": "Import-Module (Join-Path $env:TEST_ROOT 'powershell/AzAuthHelpers.psd1') -Force",
            }[shell]
            with self.subTest(shell=shell):
                result, calls = self.invoke(shell, "npm", code=code)
                self.assertEqual((result.returncode, result.stdout, result.stderr, calls), (0, "", "", []))
                result, calls = self.invoke(shell, "npm", ["--version"])
                self.assertEqual(result.returncode, 127, result.stderr)
                self.assertIn("az-auth-core is required", result.stderr)
                self.assertEqual(calls, [])

    def test_bash_env_and_zshenv_subshells_ignore_shell_variable(self):
        if os.name == "nt":
            self.skipTest("Unix shell startup files")
        if "bash" in SHELLS:
            env = self.env | {"BASH_ENV": str(self.plugin / "shell/az-auth.sh")}
            result = subprocess.run([shutil.which("bash"), "-c", 'bash -c \'npm install\''],
                                    env=env, cwd=self.project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c["command"] for c in self.calls()], ["az", "npm"])
        if "zsh" in SHELLS:
            self.log.unlink(missing_ok=True)
            (self.home / ".zshenv").write_text('. "$TEST_ROOT/shell/az-auth.sh"\n')
            result = subprocess.run([shutil.which("zsh"), "-c", "zsh -c 'npm install'"],
                                    env=self.env, cwd=self.project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c["command"] for c in self.calls()], ["az", "npm"])

    def test_writer_append_defaults_and_project_idempotence(self):
        self.auth(registry=False)
        original = (self.home / ".npmrc").read_text()
        exe = [NODE, str(self.core)]
        def write(args, stdin=""):
            return subprocess.run([*exe, "write-npm", *args], cwd=self.project, env=self.env,
                                  text=True, input=stdin, capture_output=True)
        result = write(["--"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage:", result.stderr)
        result = write(["--", "org.pkgs.visualstudio.com/_packaging/feed/npm"])
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = original + (
            "//org.pkgs.visualstudio.com/_packaging/feed/npm/registry/:username=AzCliToken\n"
            "//org.pkgs.visualstudio.com/_packaging/feed/npm/registry/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
            "//org.pkgs.visualstudio.com/_packaging/feed/npm/registry/:email=not-used@example.com\n"
            "//org.pkgs.visualstudio.com/_packaging/feed/npm/:username=AzCliToken\n"
            "//org.pkgs.visualstudio.com/_packaging/feed/npm/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
            "//org.pkgs.visualstudio.com/_packaging/feed/npm/:email=not-used@example.com\n"
        )
        self.assertEqual((self.home / ".npmrc").read_text(), expected)
        before = (self.home / ".npmrc").read_bytes()
        result = write(["--", "feed\nregistry=evil"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.home / ".npmrc").read_bytes(), before)
        result = write(["--from-project"])
        self.assertNotEqual(result.returncode, 0)
        (self.project / ".npmrc").write_text("registry=https://pkgs.dev.azure.com/org/_packaging/feed/npm/registry/\n")
        result = write(["--from-project"])
        self.assertEqual(result.returncode, 0, result.stderr)
        before = (self.home / ".npmrc").read_bytes()
        self.assertEqual(write(["--from-project"]).returncode, 0)
        self.assertEqual((self.home / ".npmrc").read_bytes(), before)
        (self.home / ".npmrc").write_text(before.decode().replace("VssSessionToken", "old-user"))
        before = (self.home / ".npmrc").read_bytes()
        result = write(["--from-project"], "n\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Update existing", result.stderr)
        self.assertEqual((self.home / ".npmrc").read_bytes(), before)
        result = write(["--from-project"], "y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("old-user", (self.home / ".npmrc").read_text())
        self.assertEqual(self.calls(), [])

    def test_rush_root_config_and_local_commands(self):
        self.auth(registry=False)
        (self.root / "rush.json").write_text("{}")
        config = self.root / "common/config/rush"
        config.mkdir(parents=True)
        (config / ".npmrc").write_text("registry=https://private.invalid/feed/\n")
        for shell in SHELLS:
            for manager, args, auth in (("rush", ["update"], True), ("rush", ["install"], True),
                                        ("rush", ["build"], False), ("rush", ["rebuild"], False),
                                        ("rush", ["purge"], False), ("rush-pnpm", ["add", "pkg"], True),
                                        ("rush-pnpm", ["run", "install"], False)):
                with self.subTest(shell=shell, manager=manager, args=args):
                    self.check(shell, manager, args, auth)

    def test_nuget_help_and_plugin_path_lists(self):
        feed = "https://pkgs.dev.azure.com/org/_packaging/feed/nuget/v3/index.json"
        (self.project / "NuGet.Config").write_text(
            f'<configuration><packageSources><add key="private" value="{feed}"/></packageSources></configuration>')
        provider = self.root / "custom-provider"
        provider.write_bytes(b"fixture")
        plugins = os.pathsep.join((str(self.root / "missing-provider"), str(provider)))
        for shell in SHELLS:
            for manager in ("dotnet", "nuget"):
                with self.subTest(shell=shell, manager=manager):
                    self.check(shell, manager, ["restore", "-?"], False)
                    self.check(shell, manager, ["-?", "restore"], False)
                    self.check(shell, manager, ["restore"], True,
                               {"NUGET_PLUGIN_PATHS": plugins})

    def test_nuget_effective_sources_and_provider(self):
        feed = "https://pkgs.dev.azure.com/org/_packaging/feed/nuget/v3/index.json"
        visual = "https://org.pkgs.visualstudio.com/_packaging/feed/nuget/v3/index.json"
        config = self.project / "NuGet.Config"
        config.write_text(f'<configuration><packageSources><add key="private" value="{feed}"/></packageSources></configuration>')
        for shell in SHELLS:
            for manager, action in (("dotnet", "restore"), ("nuget", "restore")):
                with self.subTest(shell=shell, manager=manager):
                    result, calls = self.invoke(shell, manager, [action])
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("Credential Provider", result.stderr)
                    self.assertEqual(calls, [])
                    self.check(shell, manager, ["--version"], False)
        provider = self.home / ".nuget/plugins/provider"
        provider.mkdir(parents=True)
        (provider / "CredentialProvider.Microsoft.dll").write_bytes(b"fixture")
        (provider / "CredentialProvider.Microsoft.exe").write_bytes(b"fixture")
        for shell in SHELLS:
            for manager, args in (("dotnet", ["restore"]), ("dotnet", ["build"]),
                                  ("dotnet", ["test"]), ("dotnet", ["run"]), ("dotnet", ["pack"]),
                                  ("dotnet", ["publish"]), ("nuget", ["restore"]),
                                  ("nuget", ["install", "pkg"]), ("nuget", ["update"])):
                with self.subTest(shell=shell, manager=manager, args=args):
                    calls = self.check(shell, manager, args, True)
                    self.assertEqual(calls[-1]["env"]["VSS_NUGET_ACCESSTOKEN"], "fixture-token")
                    self.assertEqual(calls[-1]["env"]["VSS_NUGET_URI_PREFIXES"], feed)
            self.check(shell, "dotnet", ["build", "--no-restore"], False)
            self.check(shell, "dotnet", ["restore", "--source", "https://api.nuget.org/v3/index.json"], False)
            self.check(shell, "nuget", ["restore", "-Source", visual], True)
            self.check(shell, "dotnet", ["restore"], False, {"VSS_NUGET_ACCESSTOKEN": "reuse"}, "reuse")
        config.write_text(f'<configuration><packageSources><add key="private" value="{feed}"/></packageSources>'
                          '<disabledPackageSources><add key="private" value="true"/></disabledPackageSources></configuration>')
        self.check("core", "dotnet", ["restore"], False)
        config.write_text('<configuration><packageSources><clear/><add key="public" value="https://api.nuget.org/v3/index.json"/></packageSources></configuration>')
        user = self.home / "AppData/NuGet"
        user.mkdir(parents=True)
        (user / "NuGet.Config").write_text(f'<configuration><packageSources><add key="private" value="{feed}"/></packageSources></configuration>')
        self.check("core", "dotnet", ["restore"], False)
        explicit = self.root / "explicit.config"
        explicit.write_text(f'<configuration><packageSources><add key="private" value="{visual}"/></packageSources></configuration>')
        self.check("core", "dotnet", ["restore", "--configfile", str(explicit)], True)
        self.check("core", "nuget", ["restore", "-ConfigFile", str(explicit)], True)
        for bad in ("http://pkgs.dev.azure.com/org", "https://pkgs.dev.azure.com.evil/org",
                    "https://evilpkgs.visualstudio.com/org", "not-a-url"):
            self.check("core", "dotnet", ["restore", "--source", bad], False)
        explicit.write_text("<configuration><broken>")
        result, calls = self.invoke("core", "dotnet", ["restore", "--configfile", str(explicit)])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        result, calls = self.invoke("core", "dotnet", ["restore", "--configfile", "missing"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    @unittest.skipIf(os.name == "nt", "Unix signals")
    def test_cancellation_reaches_manager(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                self.log.unlink(missing_ok=True)
                proc = subprocess.Popen(self.argv(shell, "npm", ["run", "build"]), cwd=self.project,
                                        env=self.env | {"TEST_BLOCK": "yes", "TEST_MANAGER": "npm",
                                                        "TEST_ARGS": '["run","build"]'},
                                        start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline and not self.calls():
                        time.sleep(0.02)
                    self.assertEqual([c["command"] for c in self.calls()], ["npm"])
                    os.killpg(proc.pid, signal.SIGINT)
                    proc.communicate(timeout=10)
                    self.assertNotEqual(proc.returncode, 0)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.communicate()

    @unittest.skipUnless(os.name == "nt", "Windows native launcher execution")
    def test_windows_shims_without_command_string(self):
        args = ["install", "", "a b", "&whoami", "%PATH%", "!", "line\nbreak", 'a"b', "^", "|", "<", ">"]
        (self.bin / "npm.exe").unlink()
        script = self.bin / "node_modules/npm/bin/npm-cli.js"
        script.parent.mkdir(parents=True)
        script.write_text((ROOT / "tests/fixture.cjs").read_text())
        (self.bin / "npm.cmd").write_text('@echo off\r\n"%dp0%\\node.exe" "%dp0%\\node_modules\\npm\\bin\\npm-cli.js" %*\r\n')
        for shell in SHELLS:
            self.check(shell, "npm", args, True)
        for manager in ("pnpm", "pnpx"):
            (self.bin / f"{manager}.exe").unlink()
            script = self.bin / f"node_modules/corepack/dist/{manager}.js"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text((ROOT / "tests/fixture.cjs").read_text())
            (self.bin / f"{manager}.cmd").write_text(
                f'@echo off\r\n"%dp0%\\node.exe" "%dp0%\\node_modules\\corepack\\dist\\{manager}.js" %*\r\n')
            for shell in SHELLS:
                self.check(shell, manager, args, True)
        (self.bin / "az.exe").unlink()
        azure = self.bin / "azure"
        azure.mkdir()
        (azure / "az.cmd").write_text('"%~dp0..\\python.exe" -IBm azure.cli %*\r\n')
        self.env["PATH"] = str(azure) + os.pathsep + self.env["PATH"]
        self.check("core", "npm", args, True)
        (self.bin / "npm.cmd").write_text("echo arbitrary %*\r\n")
        result, calls = self.invoke("core", "npm", ["--version"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported Windows launcher", result.stderr)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
