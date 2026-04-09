# shellcheck shell=zsh
# Run tfswitch when entering a directory that pins Terraform version.
# Interactive zsh only; sourced from shell/init.sh.

toolbox_require_interactive tfswitch || return 0
toolbox_require_commands tfswitch tfswitch || return 0

autoload -Uz add-zsh-hook

_tfswitch_chpwd() {
    [[ -f .terraform-version || -f .tfswitchrc || -f versions.tf ]] || return 0
    tfswitch
}

# Idempotent if init is sourced again (e.g. toolbox_reload).
add-zsh-hook -d chpwd _tfswitch_chpwd 2>/dev/null
add-zsh-hook chpwd _tfswitch_chpwd

# chpwd does not run for the shell's starting directory — only after a cd.
# Call once so a terminal opened inside a Terraform tree gets the right binary.
_tfswitch_chpwd
