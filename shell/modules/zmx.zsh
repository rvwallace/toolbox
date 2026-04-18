# shellcheck shell=zsh
# ZLE keybindings for zmx (interactive zsh only; sourced from shell/init.sh)
# Migrated from sc-zsh/includes/keybindings.zsh (zmx section).

toolbox_require_interactive zmx || return 0
toolbox_require_commands zmx zmx || return 0

# Zmx attach current directory basename — Alt-a
_zmx_attach_current_dir() {
    BUFFER="zmx attach $(basename "$PWD")"
    zle accept-line
}
zle -N _zmx_attach_current_dir
bindkey -M emacs "^[a" _zmx_attach_current_dir
bindkey -M viins "^[a" _zmx_attach_current_dir

# Zmx detach — Alt-d
_zmx_detach() {
    BUFFER="zmx detach"
    zle accept-line
}
zle -N _zmx_detach
bindkey -M emacs "^[d" _zmx_detach
bindkey -M viins "^[d" _zmx_detach

_toolbox_zmx_load_zsh_completion() {
    local cache_dir cache_file version_file current_version
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/silentcastle/toolbox/completions"
    cache_file="${cache_dir}/_zmx"
    version_file="${cache_dir}/zmx.version"
    current_version="$(zmx --version 2>/dev/null | tr -d '\r')"
    [[ -n "$current_version" ]] || return 0

    toolbox_completion_cache_ensure "$cache_file" "$version_file" "$current_version" zmx completions zsh || return 0

    # shellcheck source=/dev/null
    source "$cache_file" >/dev/null 2>&1 || return 0
}

_toolbox_zmx_load_zsh_completion
