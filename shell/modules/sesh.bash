# shellcheck shell=bash
# sesh bash completion bootstrap

toolbox_require_commands sesh sesh || return 0

_toolbox_sesh_load_bash_completion() {
    local cache_dir cache_file version_file current_version
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/silentcastle/toolbox/completions"
    cache_file="${cache_dir}/sesh.bash"
    version_file="${cache_dir}/sesh.version"
    current_version="$(sesh --version 2>/dev/null | tr -d '\r')"
    [[ -n "$current_version" ]] || return 0

    toolbox_completion_cache_ensure "$cache_file" "$version_file" "$current_version" sesh completion bash || return 0

    # shellcheck source=/dev/null
    source "$cache_file" >/dev/null 2>&1 || return 0
}

_toolbox_sesh_load_bash_completion
