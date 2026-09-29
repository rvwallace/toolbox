# Toolbox Nushell initialization
# Load this module from a private local shell configuration file:
#   use /path/to/toolbox/shell/init.nu *

const TOOLBOX_ROOT = (path self | path dirname | path dirname)

export-env {
    let toolbox_bin = ($TOOLBOX_ROOT | path join "bin")
    if ($toolbox_bin | path exists) {
        $env.PATH = ($env.PATH | prepend $toolbox_bin | uniq)
    }
}

export use modules/aws.nu *
export use modules/kube.nu *
export use modules/chef.nu *
export use modules/git.nu *
export use modules/tmux.nu *
export use modules/yazi.nu *
export use modules/terraform.nu *
export use modules/toolboxctl_helpers.nu *
