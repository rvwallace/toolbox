#!/usr/bin/env bash
# shellcheck shell=bash
# cmux shell helpers

toolbox_require_commands cmux cmux || return 0

_cmux_require_running() {
    if ! cmux ping >/dev/null 2>&1; then
        printf 'cmux: not running or not reachable; start cmux first\n' >&2
        return 1
    fi
}

cmux.ssh() {
    local args=()

    _cmux_require_running || return $?
    while (($#)); do
        if [[ "$1" == "-i" ]]; then
            args+=("--identity")
        else
            args+=("$1")
        fi
        shift
    done

    cmux ssh "${args[@]}"
}

cmux.ssh.jc() {
    local host="${1-}"

    if [[ -z "${JUMPCLOUD_KEY:-}" ]]; then
        printf 'cmux: JUMPCLOUD_KEY is not set\n' >&2
        return 1
    fi
    if [[ -z "${JUMPCLOUD_USER:-}" ]]; then
        printf 'cmux: JUMPCLOUD_USER is not set\n' >&2
        return 1
    fi
    if [[ -z "$host" ]]; then
        printf 'usage: csshjc <host> [remote-command-args...]\n' >&2
        return 2
    fi

    _cmux_require_running || return $?
    shift
    cmux ssh --identity "$JUMPCLOUD_KEY" "${JUMPCLOUD_USER}@${host}" "$@"
}

alias cssh='cmux.ssh'
alias csshjc='cmux.ssh.jc'
