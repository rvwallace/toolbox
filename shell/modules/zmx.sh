#!/usr/bin/env bash
# shellcheck shell=bash
# zmx session helpers (fzf + zmx CLI)

toolbox_require_commands zmx zmx fzf || return 0

# Pick a session name: use $1 if set, else fzf over zmx list --short.
_zmx_pick_session() {
    local name="${1-}"
    if [[ -n "$name" ]]; then
        printf '%s\n' "$name"
        return 0
    fi
    zmx list --short 2>/dev/null | fzf --height=40% --reverse --prompt="zmx session> "
}

# Session selector (migrated from sc-zsh zmx-select).
zmx.select() {
    local display output query key selected session_name rc tmpfile

    display=$(zmx list 2>/dev/null | while IFS=$'\t' read -r name pid clients _created dir; do
        [[ "$name" == name=* ]] || continue
        name=${name#name=}
        pid=${pid#pid=}
        clients=${clients#clients=}
        dir=${dir#started_in=}
        printf "%-20s  pid:%-8s  clients:%-2s  %s\n" "$name" "$pid" "$clients" "$dir"
    done)

    output=$({ [[ -n "$display" ]] && printf '%s\n' "$display"; } | fzf \
        --print-query \
        --expect=ctrl-n,ctrl-k,ctrl-d,ctrl-e \
        --height=80% \
        --reverse \
        --prompt="zmx> " \
        --header="Enter: attach | Ctrl-N: new | Ctrl-K: kill | Ctrl-D: detach | Ctrl-E: export" \
        --preview='zmx history {1}' \
        --preview-window=right:60%:follow \
    )
    rc=$?

    query=$(printf '%s\n' "$output" | sed -n '1p')
    key=$(printf '%s\n' "$output" | sed -n '2p')
    selected=$(printf '%s\n' "$output" | sed -n '3p')

    session_name=""
    if [[ -n "$selected" ]]; then
        session_name=$(printf '%s\n' "$selected" | awk '{print $1}')
    fi

    case "$key" in
        ctrl-n)
            if [[ -n "$query" ]]; then
                session_name="$query"
            else
                session_name=$(basename "$PWD")
            fi
            zmx attach "$session_name"
            ;;
        ctrl-k)
            if [[ -n "$session_name" ]]; then
                zmx kill "$session_name"
            fi
            ;;
        ctrl-d)
            if [[ -n "$session_name" ]]; then
                zmx detach "$session_name" 2>/dev/null || zmx detach
            fi
            ;;
        ctrl-e)
            if [[ -n "$session_name" ]]; then
                tmpfile=$(mktemp /tmp/zmx-session-XXXXXX.txt)
                zmx history "$session_name" >"$tmpfile"
                ${EDITOR:-vim} "$tmpfile"
                rm -f "$tmpfile"
            fi
            ;;
        *)
            if [[ $rc -eq 0 && -n "$session_name" ]]; then
                zmx attach "$session_name"
            fi
            ;;
    esac
}

# Browse session scrollback in fzf; Ctrl-S exports full history to PWD; Ctrl-E opens in $EDITOR.
zmx.history() {
    local session hist
    session=$(_zmx_pick_session "${1-}") || return 1
    [[ -z "$session" ]] && return 1

    hist=$(zmx history "$session" 2>/dev/null) || true
    [[ -z "$hist" ]] && hist="(empty history)"

    (
        export _ZMX_HS="$session"
        # shellcheck disable=SC2016
        printf '%s\n' "$hist" | fzf \
            --height=80% \
            --reverse \
            --prompt="zmx history (${session})> " \
            --header="Enter/Esc: close | Ctrl-S: export log to \$PWD | Ctrl-E: open in \$EDITOR" \
            --bind "ctrl-s:execute-silent(bash -c 'log=\"\$PWD/\${_ZMX_HS}-history-\$(date +%Y%m%d-%H%M%S).log\"; zmx history \"\${_ZMX_HS}\" >\"\$log\" 2>/dev/null; printf \"%s\\n\" \"Exported to \$log\" >&2')" \
            --bind "ctrl-e:execute(bash -c 't=\$(mktemp /tmp/zmx-hist.XXXXXX); zmx history \"\${_ZMX_HS}\" >\"\$t\"; \${EDITOR:-vim} \"\$t\"; rm -f \"\$t\"')"
    )
}

zmx.kill() {
    local session
    session=$(_zmx_pick_session "${1-}") || return 1
    [[ -z "$session" ]] && return 1
    if zmx kill "$session"; then
        printf 'zmx: killed session %s\n' "$session"
    fi
}

zmx.detach() {
    if (($# >= 1)); then
        zmx detach "$1" 2>/dev/null || zmx detach
    else
        zmx detach
    fi
}

zmx.wait() {
    if (($# > 0)); then
        zmx wait "$@"
        return $?
    fi

    local selected
    selected=$(zmx list --short 2>/dev/null | fzf -m --height=40% --reverse --prompt="zmx wait> ") || return 1
    [[ -z "$selected" ]] && return 0

    local args=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -n "$line" ]] && args+=("$line")
    done <<<"$selected"

    ((${#args[@]})) || return 0
    zmx wait "${args[@]}"
}
