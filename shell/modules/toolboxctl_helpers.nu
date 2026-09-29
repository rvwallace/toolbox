# Toolbox shell configuration adapter for Nushell

const TOOLBOX_ROOT = (path self | path dirname | path dirname | path dirname)

def toolboxctl_add_csv [current: string items: list<string>] {
    mut values = (
        $current
        | split row ","
        | each { |item| $item | str trim }
        | where { |item| $item | is-not-empty }
    )

    for item in $items {
        let item = ($item | str trim)
        if ($item | is-not-empty) and ($item not-in $values) {
            $values = ($values | append $item)
        }
    }

    $values | str join ","
}

export def --env "toolboxctl.status-refresh" [] {
    let checks = [
        { stem: "ansible", commands: ["ansible"] }
        { stem: "aws", commands: ["aws"] }
        { stem: "chef", commands: ["chef", "knife"] }
        { stem: "git", commands: ["git"] }
        { stem: "kube", commands: ["kubectl"] }
        { stem: "sesh", commands: ["sesh"] }
        { stem: "terraform", commands: ["terraform"] }
        { stem: "tmux", commands: ["tmux"], requires_tmux: true }
        { stem: "yazi", commands: ["yazi"] }
    ]

    mut active = []
    mut unavailable = []

    for check in $checks {
        if ($check.commands | is-empty) {
            $unavailable = ($unavailable | append $"($check.stem)=($check.reason)")
            continue
        }

        let missing = (
            $check.commands
            | where { |command| which $command | is-empty }
        )
        if ($missing | is-empty) {
            if ($check.requires_tmux? | default false) and ("TMUX" not-in $env) {
                $unavailable = ($unavailable | append $"($check.stem)=outside:tmux")
            } else {
                $active = ($active | append $check.stem)
            }
        } else {
            $unavailable = (
                $unavailable
                | append $"($check.stem)=missing:(($missing | str join "+"))"
            )
        }
    }

    $env.TOOLBOX_SHELL_ACTIVE = ($active | str join ",")
    $env.TOOLBOX_SHELL_UNAVAILABLE = ($unavailable | str join ";")
}

# Wrap the external toolbox command while allowing current-Nushell changes.
export def --env --wrapped toolboxctl [...args: string] {
    toolboxctl.status-refresh

    mut reload = false
    mut temporary = false
    mut forwarded = []

    for arg in $args {
        match $arg {
            "-r" | "--reload" => { $reload = true }
            "-t" | "--temporary" => { $temporary = true }
            _ => { $forwarded = ($forwarded | append $arg) }
        }
    }

    if ($forwarded | is-empty) {
        print -e "usage: toolboxctl [-r] [-t] <command> ..."
        print -e "       shortcuts: disable|enable|list|path|effective"
        return 1
    }

    let command = ($forwarded | get 0)
    let command_args = ($forwarded | skip 1)

    if $temporary and $command not-in ["disable", "enable"] {
        print -e "toolboxctl: --temporary is only valid with disable or enable"
        return 1
    }

    if $reload {
        print -e $"toolboxctl: Nushell modules are loaded when imported; restart Nushell or re-run `use ($TOOLBOX_ROOT)/shell/init.nu *`"
    }

    if $temporary and $command == "disable" {
        $env.TOOLBOX_SHELL_DISABLED = (
            toolboxctl_add_csv ($env.TOOLBOX_SHELL_DISABLED? | default "") $command_args
        )
    } else if $temporary and $command == "enable" {
        $env.TOOLBOX_SHELL_ENABLED = (
            toolboxctl_add_csv ($env.TOOLBOX_SHELL_ENABLED? | default "") $command_args
        )
    } else if $command in ["disable", "enable", "list", "path", "effective"] {
        ^toolbox shell $command ...$command_args
    } else {
        ^toolbox $command ...$command_args
    }
}
