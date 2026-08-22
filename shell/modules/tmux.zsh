# shellcheck shell=zsh
# zsh completions for tmux shell helpers

(( ${+functions[tp]} )) || { toolbox_mark_module_unavailable tmux "missing:tp"; return 0; }

_toolbox_tp() {
    _arguments \
        '(-EE)-E[Close popup when command exits (default)]' \
        '(-E)-EE[Stay open if command fails]' \
        '(-h --help)'{-h,--help}'[Show usage information]' \
        '*::command:_normal'
}

compdef _toolbox_tp tp

# Tmux Popup Toggle Widget (Ctrl-X, p)
if (( $+commands[tmux] )); then
    _tmux_popup_toggle() {
        if [[ -z $BUFFER ]]; then
            zle up-history
        fi

        local popup_prefix="tmux display-popup -- "

        if [[ $BUFFER == ${popup_prefix}* ]]; then
            BUFFER="${BUFFER#${popup_prefix}}"
        elif [[ $BUFFER == "tmux display-popup"* ]]; then
            zle -M "Complex popup command - edit manually"
        else
            BUFFER="${popup_prefix}${BUFFER}"
        fi
        zle redisplay
    }
    zle -N _tmux_popup_toggle
    bindkey -M emacs "^Xp" _tmux_popup_toggle 2>/dev/null || true
    bindkey -M viins "^Xp" _tmux_popup_toggle 2>/dev/null || true
fi
