# shellcheck shell=bash
# Terraform bash: tfswitch on directory change (interactive).

toolbox_require_interactive terraform || return 0

_terraform_prompt_tfswitch() {
    if [[ "$PWD" != "${_last_terraform_tfswitch_pwd:-}" ]]; then
        _last_terraform_tfswitch_pwd="$PWD"
        if [[ -f .terraform-version || -f .tfswitchrc || -f versions.tf ]]; then
            command -v tfswitch >/dev/null 2>&1 && tfswitch
        fi
    fi
}

if [[ -z "${PROMPT_COMMAND:-}" ]]; then
    PROMPT_COMMAND="_terraform_prompt_tfswitch"
elif [[ "$PROMPT_COMMAND" != *"_terraform_prompt_tfswitch"* ]]; then
    PROMPT_COMMAND="${PROMPT_COMMAND%;}; _terraform_prompt_tfswitch"
fi

_terraform_prompt_tfswitch
