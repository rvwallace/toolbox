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

# Generate completions asynchronously so it does not block shell startup
if type zinit >/dev/null 2>&1; then
    zinit ice wait"1" lucid atload'eval "$(zmx completions zsh)"'
    zinit light zdharma-continuum/null
else
    eval "$(zmx completions zsh)"
fi
