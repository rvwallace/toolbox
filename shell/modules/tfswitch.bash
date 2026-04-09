# shellcheck shell=bash
# Run tfswitch when entering a directory that pins Terraform version.
# Interactive bash only; sourced from shell/init.sh.

toolbox_require_interactive tfswitch || return 0
toolbox_require_commands tfswitch tfswitch || return 0

_tfswitch_prompt_cmd() {
    # Only run tfswitch if the directory actually changed
    if [[ "$PWD" != "${_last_tfswitch_pwd:-}" ]]; then
        _last_tfswitch_pwd="$PWD"
        if [[ -f .terraform-version || -f .tfswitchrc || -f versions.tf ]]; then
            tfswitch
        fi
    fi
}

# Safely append to PROMPT_COMMAND
if [[ -z "${PROMPT_COMMAND:-}" ]]; then
    PROMPT_COMMAND="_tfswitch_prompt_cmd"
elif [[ "$PROMPT_COMMAND" != *"_tfswitch_prompt_cmd"* ]]; then
    PROMPT_COMMAND="${PROMPT_COMMAND%;}; _tfswitch_prompt_cmd"
fi

# Run once initially to catch the starting directory
_tfswitch_prompt_cmd
