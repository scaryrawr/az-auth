if [ -n "${ZSH_VERSION-}" ]; then
    __az_auth_source="${(%):-%x}"
else
    __az_auth_source="${BASH_SOURCE[0]}"
fi
case "$__az_auth_source" in
    /*) ;;
    *) __az_auth_source="$PWD/$__az_auth_source" ;;
esac
__az_auth_core="${__az_auth_source%/*}/../functions/az-auth-core.cjs"
unset __az_auth_source

__az_auth_run() {
    if [ ! -f "$__az_auth_core" ]; then
        printf '%s\n' 'az-auth-core is required. Reinstall the checkout. See README.md.' >&2
        return 127
    fi
    if ! command -v node >/dev/null 2>&1; then
        printf '%s\n' 'Node 22 or newer is required. Install Node on PATH. See README.md.' >&2
        return 127
    fi
    command node "$__az_auth_core" "$@"
}

npm() { __az_auth_run run --manager npm -- "$@"; }
npx() { __az_auth_run run --manager npx -- "$@"; }
pnpm() { __az_auth_run run --manager pnpm -- "$@"; }
pnpx() { __az_auth_run run --manager pnpx -- "$@"; }
pn() { __az_auth_run run --manager pnpm -- "$@"; }
yarn() { __az_auth_run run --manager yarn -- "$@"; }
bun() { __az_auth_run run --manager bun -- "$@"; }
corepack() { __az_auth_run run --manager corepack -- "$@"; }
dotnet() { __az_auth_run run --manager dotnet -- "$@"; }
nuget() { __az_auth_run run --manager nuget -- "$@"; }
rush() { __az_auth_run run --manager rush -- "$@"; }
rush-pnpm() { __az_auth_run run --manager rush-pnpm -- "$@"; }
write-npm() { __az_auth_run write-npm -- "$@"; }
