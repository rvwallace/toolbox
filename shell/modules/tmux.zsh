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
