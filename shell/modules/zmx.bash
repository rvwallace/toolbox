# shellcheck shell=bash
# Zmx UI integrations (interactive bash only)

toolbox_require_interactive zmx || return 0
toolbox_require_commands zmx zmx || return 0

# Zmx attach current directory basename — Alt-a
bind '"\ea":"zmx attach $(basename \"$PWD\")\n"'

# Zmx detach — Alt-d
bind '"\ed":"zmx detach\n"'

_toolbox_zmx_load_bash_completion() {
    local cache_dir cache_file version_file current_version
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/silentcastle/toolbox/completions"
    cache_file="${cache_dir}/zmx.bash"
    version_file="${cache_dir}/zmx.version"
    current_version="$(zmx --version 2>/dev/null | tr -d '\r')"
    [[ -n "$current_version" ]] || return 0

    toolbox_completion_cache_ensure "$cache_file" "$version_file" "$current_version" zmx completions bash || return 0

    # shellcheck source=/dev/null
    source "$cache_file" >/dev/null 2>&1 || return 0
}

_toolbox_zmx_load_bash_completion
