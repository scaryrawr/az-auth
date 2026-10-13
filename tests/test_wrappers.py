#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(os.environ.get("AZ_AUTH_TEST_ROOT", Path(__file__).resolve().parents[1]))
FISH = shutil.which("fish")
NODE = os.environ.get("AZ_AUTH_NODE") or shutil.which("node")
WRAPPERS = ("npm", "npx", "pnpm", "pnpx", "pn", "yarn", "bun", "corepack")
FAKE = f"""#!{sys.executable}
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
record = {{
    "command": name,
    "args": sys.argv[1:],
    "token": os.environ.get("ARTIFACTS_ACCESSTOKEN"),
}}
with open(os.environ["TEST_LOG"], "a") as log:
    log.write(json.dumps(record) + "\\n")
if name == "az":
    print(os.environ.get("TEST_AZ_TOKEN", "fresh-token"))
    sys.exit(int(os.environ.get("TEST_AZ_STATUS", "0")))
if len(sys.argv) > 1 and sys.argv[1] == "completion-server":
    print(os.environ.get("TEST_COMPLETIONS", "install\\\\tInstall packages"))
sys.exit(int(os.environ.get("TEST_MANAGER_STATUS", "0")))
"""


@unittest.skipUnless(FISH, "fish is required")
class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        for name in (*WRAPPERS, "az"):
            path = self.bin / name
            path.write_text(FAKE)
            path.chmod(0o755)
        if NODE:
            (self.bin / "node").symlink_to(NODE)
        self.log = self.directory / "calls.jsonl"
        self.project = self.directory / "project"
        self.project.mkdir()
        (self.project / "package.json").write_text("{}")
        (self.project / "src").mkdir()
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.directory),
            "XDG_CONFIG_HOME": str(self.directory),
            "TEST_ROOT": str(ROOT),
            "TEST_LOG": str(self.log),
        }
        (self.directory / ".npmrc").write_text(
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
            "registry=https://private.invalid/feed/\n"
            "@fixture:registry=https://private.invalid/feed/\n"
        )

    def invoke(self, manager, *args, extra=None, script=None):
        self.log.unlink(missing_ok=True)
        code = 'set -g fish_function_path "$TEST_ROOT/functions" $fish_function_path\n'
        code += script or '$argv[1] $argv[2..-1]'
        result = subprocess.run(
            [FISH, "--no-config", "-c", code, manager, *args],
            env=self.env | (extra or {}),
            text=True,
            capture_output=True,
            cwd=self.project,
        )
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def check(self, manager, args, auth, inherited=None):
        extra = {} if inherited is None else {"ARTIFACTS_ACCESSTOKEN": inherited}
        result, calls = self.invoke(manager, *args, extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        azure = [call for call in calls if call["command"] == "az"]
        external = [call for call in calls if call["command"] != "az"]
        self.assertEqual(len(azure), int(auth and not inherited), (manager, args, calls))
        self.assertEqual(len(external), 1, calls)
        self.assertEqual(external[0]["command"], "pnpm" if manager == "pn" else manager)
        self.assertEqual(external[0]["args"], list(args))
        self.assertEqual(external[0]["token"], inherited or ("fresh-token" if auth else inherited))
        if azure:
            self.assertEqual(
                azure[0]["args"],
                ["account", "get-access-token", "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
                 "--query", "accessToken", "-o", "tsv"],
            )

    def test_all_wrappers_auth_and_no_auth(self):
        actions = {
            "npm": ("install",), "npx": ("tool",), "pnpm": ("install",),
            "pnpx": ("tool",), "pn": ("install",), "yarn": ("install",),
            "bun": ("install",), "corepack": ("pnpm", "install"),
        }
        for manager, args in actions.items():
            with self.subTest(manager=manager):
                self.check(manager, args, True)
                self.check(manager, ("--version",), False)
                self.check(manager, args, True, "caller-token")
                self.check(manager, ("--version",), False, "caller-token")
                self.check(manager, args, True, "-n")

    def test_action_groups_and_aliases(self):
        groups = {
            "npm": "install i in ins inst insta instal add isnt isntall ci clean-install ic install-clean update up upgrade udpate outdated audit view info show v search s se find ping whoami publish unpublish access dist-tag owner stars star unstar",
            "pnpm": "install i add update up upgrade remove rm uninstall un outdated audit view info show search ping whoami publish unpublish dist-tag owner fetch patch import",
            "yarn": "install i add up upgrade upgrade-interactive remove outdated audit info publish tag owner",
            "bun": "install i add a update remove rm uninstall publish outdated",
        }
        for manager, actions in groups.items():
            for action in actions.split():
                with self.subTest(manager=manager, action=action):
                    self.check(manager, (action, "package"), True)

    def test_local_actions_and_false_positives(self):
        for manager in ("npm", "pnpm", "pn", "yarn", "bun"):
            for args in (("run", "install"), ("run", "publish"), ("test",), ("exec", "--", "tool", "--help"),
                         ("config", "get", "registry"), ("help", "install"), ("unknown", "install"),
                         ("build",), ("init",), ("link",)):
                with self.subTest(manager=manager, args=args):
                    self.check(manager, args, False)
        for args in (("store", "prune"), ("server", "start"), ("completion-server",)):
            self.check("pnpm", args, False)

    def test_defaults(self):
        for manager in WRAPPERS:
            self.check(manager, (), manager in ("pnpm", "pn", "yarn"))
        self.check("pnpm", ("--silent",), True)
        self.check("yarn", ("--cwd", "a directory"), True)
        self.check("npm", ("--silent",), False)

    def test_leading_options(self):
        for manager in ("npm", "pnpm", "pn", "yarn", "bun"):
            for args in (("--cwd", "install", "run", "build"), ("--registry", "install", "run", "build"),
                         ("--prefix=install", "run", "build"), ("-C", "install", "run", "build"),
                         ("--userconfig", "--help", "run", "build")):
                self.check(manager, args, False)
            self.check(manager, ("--silent", "--registry=https://registry.invalid", "install"), True)
            self.check(manager, ("--version", "install"), False)
            self.check(manager, ("install", "--help"), False)
            self.check(manager, ("install", "--", "--help"), True)
            self.check(manager, ("install", "--registry", "--help"), True)
        self.check("npm", ("--workspace", "install", "run", "build"), False)
        self.check("pnpm", ("--filter", "install", "run", "build"), False)
        self.check("pnpm", ("-F", "install", "--recursive", "run", "build"), False)
        self.check("pnpm", ("--filter=install", "-r", "add", "dependency"), True)
        self.check("pnpm", ("--workspace", "run", "install"), False)
        self.check("pnpm", ("-w", "add", "dependency"), True)

    def test_nested_commands(self):
        for args, auth in (
            (("recursive", "--filter", "run", "add", "package"), True),
            (("recursive", "run", "install"), False),
            (("r", "update"), True), (("store", "add", "package"), True),
        ):
            self.check("pnpm", args, auth)
        for args, auth in (
            (("workspace", "install", "run", "build"), False),
            (("workspace", "a workspace", "add", "package"), True),
            (("workspaces", "foreach", "-A", "run", "install"), False),
            (("workspaces", "foreach", "--from", "install", "add", "package"), True),
            (("workspaces", "run", "install"), False),
            (("npm", "info", "package"), True), (("npm", "publish"), True),
            (("npm", "audit"), True), (("npm", "tag", "add", "package", "tag"), True),
            (("npm", "--registry", "install", "whoami"), True),
            (("npm", "unknown", "publish"), False),
        ):
            self.check("yarn", args, auth)
        for args, auth in (
            (("enable", "pnpm"), False), (("prepare", "yarn@4"), False),
            (("install",), False), (("use", "pnpm@10"), False),
            (("pnpm",), True), (("yarn@4",), True), (("npm",), False),
            (("pnpm@10", "--filter", "install", "run", "build"), False),
            (("--verbose", "yarn@4", "npm", "publish"), True),
            (("npm", "--userconfig", "a config", "ci"), False),
            (("yarn", "workspace", "install", "run", "build"), False),
            (("yarn", "install", "--help"), False),
        ):
            self.check("corepack", args, auth)

    def test_download_runners(self):
        for manager, prefix in (("npx", ()), ("pnpx", ()), ("bun", ("x",)),
                                ("pnpm", ("dlx",)), ("yarn", ("dlx",))):
            self.check(manager, (*prefix, "tool"), True)
            self.check(manager, (*prefix, "--help"), False)
            self.check(manager, (*prefix, "tool", "--help"), True)
            self.check(manager, (*prefix, "--", "tool", "--help"), True)
        self.check("npx", ("--no-install", "tool"), False)
        self.check("npx", ("--no", "tool"), False)
        self.check("npx", ("--yes=false", "tool"), False)
        self.check("npx", ("--package", "tool", "other-tool"), True)
        self.check("npx", ("-p", "tool"), True)
        self.check("npx", ("--package", "--help", "tool"), True)
        self.check("bun", ("x", "--no-install", "tool"), False)
        self.check("bun", ("--no-install", "x", "tool"), False)
        self.check("bun", ("x", "tool", "--no-install"), True)
        self.check("pnpm", ("dlx", "--package", "--help", "tool"), True)
        self.check("yarn", ("dlx", "-p", "--help", "tool"), True)

    def test_passthrough_status_and_environment_scope(self):
        args = ("install", "a package", "$(touch forbidden)", "; echo unsafe", "*", "", "a\nb")
        for manager in WRAPPERS:
            command_args = ("pnpm", *args) if manager == "corepack" else args
            result, calls = self.invoke(manager, *command_args, extra={"TEST_MANAGER_STATUS": "37"})
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertEqual(calls[-1]["args"], list(command_args))
            self.assertEqual(calls[-1]["token"], "fresh-token")
            result, calls = self.invoke(manager, "--version", extra={"TEST_MANAGER_STATUS": "37"})
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertIsNone(calls[-1]["token"])
        result, calls = self.invoke(
            "npm", script='npm install; or exit $status\nnpm run build\nset -q ARTIFACTS_ACCESSTOKEN; and exit 99\nexit 0'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call["token"] for call in calls if call["command"] == "npm"], ["fresh-token", None])

    def test_azure_failure_stops_manager(self):
        for manager in WRAPPERS:
            args = ("pnpm", "install") if manager == "corepack" else ("install",)
            for extra, expected in (
                ({"TEST_AZ_STATUS": "23"}, 23),
                ({"TEST_AZ_STATUS": "23", "TEST_AZ_TOKEN": ""}, 23),
                ({"TEST_AZ_TOKEN": ""}, 1),
                ({"TEST_AZ_TOKEN": "   "}, 1),
            ):
                with self.subTest(manager=manager, extra=extra):
                    result, calls = self.invoke(manager, *args, extra=extra)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual([call["command"] for call in calls], ["az"])
        self.check("npm", ("install",), True, "")
        self.check("npm", ("run", "build"), False, "")

    def test_auth_entries_without_registry_selection(self):
        (self.directory / ".npmrc").write_text(
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
        )
        for manager in WRAPPERS:
            args = ("pnpm", "install") if manager == "corepack" else ("install",)
            self.check(manager, args, False)
        (self.project / ".npmrc").write_text("registry=https://private.invalid/feed/\n")
        self.check("npm", ("install",), True)
        self.check("npm", ("run", "install"), False)
        self.check("npm", ("install", "--registry", "https://registry.npmjs.org/"), False)
        self.check("npm", ("--registry=https://registry.npmjs.org/", "install"), False)
        self.check("npm", ("install",), False, "caller-token")

    def test_runner_arguments_do_not_override_registry(self):
        (self.directory / ".npmrc").write_text(
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
            "registry=https://private.invalid/feed/\n"
        )
        for manager, args in (
            ("npx", ("tool",)),
            ("pnpx", ("tool",)),
            ("pnpm", ("dlx", "tool")),
            ("pnpm", ("dlx", "--package", "dependency", "tool")),
            ("yarn", ("dlx", "-p", "dependency", "tool")),
            ("corepack", ("yarn", "dlx", "-p", "dependency", "tool")),
            ("bun", ("x", "--silent", "tool")),
        ):
            self.check(manager, (*args, "--registry=https://registry.npmjs.org/"), True)
        self.check("npm", ("install", "package", "--registry=https://registry.npmjs.org/"), False)

    def test_config_precedence_and_scope_matching(self):
        (self.directory / ".npmrc").write_text(
            "registry=https://private.invalid/feed/\n"
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
        )
        (self.project / ".npmrc").write_text("registry=https://registry.npmjs.org/\n")
        self.check("npm", ("install",), False)
        self.check("npm", ("install", "--registry", "https://private.invalid/feed/"), True)
        result, calls = self.invoke(
            "npm", "install", extra={"npm_config_registry": "https://private.invalid/feed/"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call["command"] for call in calls], ["az", "npm"])
        result, calls = self.invoke(
            "npm", "install", "--registry=https://registry.npmjs.org/",
            extra={"npm_config_registry": "https://private.invalid/feed/"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call["command"] for call in calls], ["npm"])
        (self.project / ".npmrc").write_text(
            "registry=https://registry.npmjs.org/\n@private:registry=https://private.invalid/feed/nested/\n"
        )
        self.check("npm", ("install",), True)
        self.check("npm", ("install", "--registry=https://registry.npmjs.org/"), True)
        self.check("npm", ("install", "--@private:registry=https://registry.npmjs.org/"), False)
        (self.project / ".npmrc").write_text("registry=https://private.invalid/feed-other/\n")
        self.check("npm", ("install",), False)
        (self.project / ".npmrc").write_text(
            "registry=https://private.invalid/feed/\n//private.invalid/feed/:_authToken=other-token\n"
        )
        self.check("npm", ("install",), False)

    def test_project_root_workspace_and_cwd(self):
        (self.directory / ".npmrc").write_text(
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
        )
        (self.directory / "package.json").write_text("{}")
        (self.directory / ".npmrc").write_text(
            "//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
            "registry=https://private.invalid/feed/\n"
        )
        alternate_user = self.directory / "auth.npmrc"
        alternate_user.write_text("//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n")
        self.check("npm", ("--userconfig", str(alternate_user), "install"), False)
        self.check("npm", ("--userconfig", str(alternate_user), "--prefix", "..", "install"), True)
        self.check("npm", ("--userconfig", str(alternate_user), "-C", "..", "install"), True)
        self.check("npm", ("--userconfig", str(alternate_user), "--cwd=..", "install"), True)
        (self.directory / "pnpm-workspace.yaml").write_text("packages: ['project']\n")
        self.check("pnpm", ("--userconfig", str(alternate_user), "install"), True)
        self.check("corepack", ("pnpm@10", "--userconfig", str(alternate_user), "install"), True)
        child = self.project / "child"
        child.mkdir()
        (self.project / ".npmrc").write_text("registry=https://private.invalid/feed/\n")
        self.check("npm", ("--userconfig", str(alternate_user), "--prefix", str(child), "install"), True)
        (child / "package.json").write_text("{}")
        self.check("npm", ("--userconfig", str(alternate_user), "--prefix", str(child), "install"), False)

    def test_explicit_user_global_and_environment_config(self):
        (self.directory / ".npmrc").unlink()
        user = self.directory / "custom.npmrc"
        user.write_text("//private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n")
        global_config = self.directory / "global.npmrc"
        global_config.write_text("registry=https://private.invalid/feed/\n")
        self.check("npm", ("--userconfig", str(user), "--globalconfig", str(global_config), "ci"), True)
        self.check("npm", ("--userconfig=" + str(user), "--globalconfig=" + str(global_config), "ci"), True)
        for case in ("npm_config", "NPM_CONFIG"):
            result, calls = self.invoke("npm", "install", extra={
                f"{case}_USERCONFIG" if case == "NPM_CONFIG" else f"{case}_userconfig": str(user),
                f"{case}_GLOBALCONFIG" if case == "NPM_CONFIG" else f"{case}_globalconfig": str(global_config),
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([call["command"] for call in calls], ["az", "npm"])
        prefix = self.directory / "prefix"
        (prefix / "etc").mkdir(parents=True)
        (prefix / "etc/npmrc").write_text("registry=https://private.invalid/feed/\n")
        self.check("npm", ("--userconfig", str(user), "--prefix", str(prefix), "-g", "install"), True)
        (global_config).write_text("registry=https://registry.npmjs.org/\n")
        (self.project / ".npmrc").write_text("registry=https://private.invalid/feed/\n")
        self.check("npm", ("--userconfig", str(user), "--globalconfig", str(global_config), "install"), True)
        self.check("npm", ("--userconfig", str(user), "--globalconfig", str(global_config), "-g", "install"), False)

    def test_comments_and_unrelated_token_references(self):
        (self.directory / ".npmrc").write_text(
            "# registry=https://private.invalid/feed/\n"
            "; //private.invalid/feed/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
            "registry=https://private.invalid/feed/\n"
            "email=${ARTIFACTS_ACCESSTOKEN}\n"
            "//unrelated.invalid/:_authToken=${ARTIFACTS_ACCESSTOKEN}\n"
        )
        self.check("npm", ("install",), False)
        (self.directory / ".npmrc").write_text(
            'registry = https://private.invalid/feed/\n'
            '//private.invalid/feed/:_authToken = "${ARTIFACTS_ACCESSTOKEN}" # auth\n'
        )
        self.check("npm", ("install",), True)

    def test_yarn_native_config_and_placeholder(self):
        (self.directory / ".npmrc").unlink()
        yarnrc = self.project / ".yarnrc.yml"
        yarnrc.write_text(
            'npmRegistryServer: "https://private.invalid/feed/"\n'
            'npmAuthToken: "${ARTIFACTS_ACCESSTOKEN}"\n'
        )
        self.check("yarn", ("install",), True)
        for manager, args in (
            ("yarn", ("run", "install")), ("corepack", ("yarn@4", "run", "build")),
            ("yarn", ("--version",)),
        ):
            result, calls = self.invoke(manager, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 1, calls)
            self.assertEqual(calls[0]["token"], "__fish_completion_placeholder__")
            self.check(manager, args, False, "caller-token")
            self.check(manager, args, False, "")
        self.check("npm", ("install",), False)
        yarnrc.write_text(
            'npmScopes:\n  private:\n    npmRegistryServer: "https://private.invalid/feed/"\n'
            '    npmAuthToken: "${ARTIFACTS_ACCESSTOKEN}"\n'
        )
        self.check("yarn", ("install",), True)
        yarnrc.write_text(
            'npmRegistryServer: "https://private.invalid/feed/"\n'
            'npmRegistries:\n  "https://private.invalid/feed/":\n'
            '    npmAuthToken: "${ARTIFACTS_ACCESSTOKEN}"\n'
        )
        self.check("yarn", ("install",), True)
        parent = self.directory / ".yarnrc.yml"
        parent.write_text(yarnrc.read_text())
        yarnrc.write_text('npmRegistryServer: "https://registry.yarnpkg.com/"\n')
        result, calls = self.invoke("yarn", "install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(calls[0]["token"], "__fish_completion_placeholder__")

    def test_bun_native_config(self):
        (self.directory / ".npmrc").unlink()
        bunfig = self.project / "bunfig.toml"
        for content in (
            '[install]\nregistry = {url = "https://private.invalid/feed/", token = "$ARTIFACTS_ACCESSTOKEN"}\n',
            '[install.scopes]\n"@private" = {url = "https://private.invalid/feed/", token = "$ARTIFACTS_ACCESSTOKEN"}\n',
            '[install.scopes.private]\nurl = "https://private.invalid/feed/"\ntoken = "$ARTIFACTS_ACCESSTOKEN"\n',
        ):
            bunfig.write_text(content)
            self.check("bun", ("install",), True)
            self.check("bun", ("run", "install"), False)
            self.check("npm", ("install",), False)
        bunfig.write_text(
            '# token="$ARTIFACTS_ACCESSTOKEN"\n[install]\nregistry="https://registry.npmjs.org/"\n'
        )
        self.check("bun", ("install",), False)
        (self.directory / ".bunfig.toml").write_text(
            '[install]\nregistry = {url = "https://private.invalid/feed/", token = "$ARTIFACTS_ACCESSTOKEN"}\n'
        )
        self.check("bun", ("install",), False)
        bunfig.unlink()
        self.check("bun", ("install",), True)

    def test_completion_never_fetches_or_exposes_token(self):
        script = '''
source "$TEST_ROOT/completions/pnpm.fish"
function commandline
    switch $argv[1]
        case -o
            printf '%s\\n' pnpm 'a package' '; echo unsafe' '--help'
        case -C
            echo 42
        case -ct
            echo src
    end
end
_pnpm_completion
'''
        for inherited in (None, "inherited-secret"):
            extra = {"TEST_AZ_STATUS": "99"}
            if inherited:
                extra["ARTIFACTS_ACCESSTOKEN"] = inherited
            result, calls = self.invoke("pnpm", script=script, extra=extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "install\tInstall packages\n")
            self.assertEqual(len(calls), 1, calls)
            self.assertEqual(calls[0], {
                "command": "pnpm", "token": "__fish_completion_placeholder__",
                "args": ["completion-server", "--", "pnpm", "a package", "; echo unsafe", "--help"],
            })
        file_script = script.replace("_pnpm_completion\n", '''
function __fish_complete_path
    printf '%s\\n' "$argv[1]/file"
end
_pnpm_completion
''')
        result, calls = self.invoke(
            "pnpm", script=file_script, extra={"TEST_COMPLETIONS": "__tabtab_complete_files__"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "src/file\n")
        self.assertEqual(len(calls), 1, calls)


if __name__ == "__main__":
    unittest.main()
