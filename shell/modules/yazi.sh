#!/usr/bin/env bash
# Yazi shell wrapper: preserve the directory selected when Yazi exits.

toolbox_require_commands yazi yazi || return 0

y() {
    local tmp cwd
    tmp="$(mktemp -t yazi-cwd.XXXXXX)" || return 1

    command yazi "$@" --cwd-file="$tmp"

    IFS= read -r -d '' cwd < "$tmp"
    if [[ "$cwd" != "$PWD" && -d "$cwd" ]]; then
        # use builtin cd if we want to bypass zoxide if installed and overrides cd
        # builtin cd -- "$cwd"

        cd -- "$cwd"
    fi

    command rm -f -- "$tmp"
}
