# Terraform shell helpers for Nushell

const TOOLBOX_ROOT = (path self | path dirname | path dirname | path dirname)

export alias tfswitch = tfswitch -b $"($env.HOME)/.local/bin/terraform"

# Save a plan to TF_PLANS_DIR with timestamp and show summary
export def --env "terraform.plan.save" [
    --init
    --no-sensitive
    ...plan_args: string
] {
    let script = ($TOOLBOX_ROOT | path join "shell/modules/terraform.sh")
    if not ($script | path exists) {
        print -e $"terraform.plan.save: script not found at ($script)"
        return 1
    }

    mut cmd_args = []
    if $init { $cmd_args = ($cmd_args | append "--init") }
    if $no_sensitive { $cmd_args = ($cmd_args | append "--no-sensitive") }
    let final_args = ($cmd_args | append $plan_args)

    bash -c $'source "($script)"; terraform.plan.save "$@"' -- ...$final_args
}

# Apply the latest saved plan for current ticket
export def --env "terraform.apply.last" [
    --yes
] {
    let script = ($TOOLBOX_ROOT | path join "shell/modules/terraform.sh")
    if not ($script | path exists) {
        print -e $"terraform.apply.last: script not found at ($script)"
        return 1
    }

    let args = if $yes { ["--yes"] } else { [] }
    bash -c $'source "($script)"; terraform.apply.last "$@"' -- ...$args
}
