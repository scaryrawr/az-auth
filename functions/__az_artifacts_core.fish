set -g __az_auth_core_fish (path resolve -- (status dirname)/az-auth-core.cjs)

function __az_artifacts_core
    if not test -f "$__az_auth_core_fish"
        echo "az-auth-core is required. Reinstall the plugin. See README.md." >&2
        return 127
    end
    if not command -q node
        echo "Node 22 or newer is required. Install Node on PATH. See README.md." >&2
        return 127
    end
    command node "$__az_auth_core_fish" $argv
end
