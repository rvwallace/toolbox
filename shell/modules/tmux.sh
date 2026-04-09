#!/usr/bin/env bash
# shellcheck shell=bash
# tmux shell helpers

toolbox_require_commands tmux tmux || return 0
toolbox_require_tmux_session tmux || return 0

tp() {
    local exit_flag="-E"

    _tp_usage() {
        cat <<'EOF'
Usage: tp [-E|-EE] <command...>

Run a command inside a tmux display-popup window.

Options:
  -E      Close popup when command exits (default)
  -EE     Stay open if command fails (useful for seeing errors)

Examples:
  tp ls -la
  tp 'cmd1; cmd2'
  tp -EE 'might-fail'

Note: Without quotes, semicolons are parsed by the shell before tp sees them.
EOF
    }

    case "${1-}" in
        -h|--help)
            _tp_usage
            return 0
            ;;
        -EE)
            exit_flag="-EE"
            shift
            ;;
        -E)
            shift
            ;;
    esac

    if (($# == 0)); then
        _tp_usage
        return 1
    fi

    tmux display-popup "$exit_flag" -- "${SHELL:-/bin/sh}" -c "$*"
}
