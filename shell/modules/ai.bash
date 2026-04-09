# shellcheck shell=bash
# AI Interactive shell module bash UI

toolbox_require_interactive ai || return 0
toolbox_require_commands ai aichat || return 0

# aichat - Bind: Alt-e
_aichat_bash() {
    if [[ -n "$READLINE_LINE" ]]; then
        local _old="$READLINE_LINE"
        # We can't safely inject the hourglass and visually force a UI refresh 
        # inside standard bash like we can with zle, so we just run synchronously
        READLINE_LINE=$(aichat -e "$_old")
        READLINE_POINT=${#READLINE_LINE}
    fi
}

bind -x '"\ee": _aichat_bash'
