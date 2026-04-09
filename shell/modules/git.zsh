# shellcheck shell=zsh
# zsh completions for git shell helpers

(( ${+functions[git.ignore.add]} )) || { toolbox_mark_module_unavailable git "missing:git.ignore.add"; return 0; }

_toolbox_git_ignore_add() {
    _arguments \
        '1:file or pattern:_files'
}

compdef _toolbox_git_ignore_add git.ignore.add
