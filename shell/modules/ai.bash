# shellcheck shell=bash
# AI Interactive shell module bash UI

toolbox_require_interactive ai || return 0
toolbox_require_commands ai aichat || return 0

# aichat (dispatcher: toolbox_aichat_widget_run in ai.sh) — Bind: Alt-e
_aichat_bash() {
    if [[ -z "$READLINE_LINE" ]]; then
        return 0
    fi
    local _old="$READLINE_LINE" _out
    _out=$(toolbox_aichat_widget_run "$_old")
    if [[ "$_out" == __TOOLBOX_AICHAT_SUBMIT__' '* ]]; then
        # readline cannot accept the buffer programmatically after bind -x; eval runs the same composed line.
        READLINE_LINE=""
        READLINE_POINT=0
        eval "${_out#__TOOLBOX_AICHAT_SUBMIT__ }"
    else
        READLINE_LINE="$_out"
        READLINE_POINT=${#READLINE_LINE}
    fi
}

bind -x '"\ee": _aichat_bash'
