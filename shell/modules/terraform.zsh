# shellcheck shell=zsh
# Terraform zsh: tfswitch on chpwd + completions for tf.* helpers.

toolbox_require_interactive terraform || return 0

autoload -Uz add-zsh-hook compinit

_terraform_chpwd_tfswitch() {
    [[ -f .terraform-version || -f .tfswitchrc || -f versions.tf ]] || return 0
    command -v tfswitch >/dev/null 2>&1 || return 0
    tfswitch
}

add-zsh-hook -d chpwd _terraform_chpwd_tfswitch 2>/dev/null
add-zsh-hook chpwd _terraform_chpwd_tfswitch

_terraform_chpwd_tfswitch

_tf_plan_save() {
    _arguments \
        '--init[Run terraform init first or when .terraform is missing]' \
        '--no-sensitive[Pass -no-sensitive to terraform show when supported]' \
        '*:terraform plan argument: '
}

_tf_state_show_save() {
    _arguments \
        '--managed-only[Exclude data.* resources]' \
        '*:grep pattern: '
}

_tf_apply_save() {
    _arguments \
        '--init[Run terraform init before plan]' \
        '--yes[Apply without confirmation]' \
        '*:terraform plan argument: '
}

_tf_apply_last() {
    _arguments \
        '--yes[Apply without confirmation]'
}

compdef _tf_plan_save tf.plan.save tf-plan-save
compdef _tf_state_show_save tf.state.show.save tf-state-show-save
compdef _tf_apply_save tf.apply.save tf-apply-save
compdef _tf_apply_last tf.apply.last tf-apply-last
