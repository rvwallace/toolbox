# Chef shell helpers for Nushell

def chef_env_subcommands [] {
    [
        { value: "set", description: "Select and set the Chef environment" }
        { value: "clear", description: "Clear current CHEF_ENV" }
        { value: "show", description: "Show current CHEF_ENV" }
        { value: "list", description: "List available Chef configurations" }
    ]
}

def chef_available_configs [] {
    let chef_dir = ($env.CHEF_ENV_DIR? | default ($env.HOME | path join ".chef"))
    if not ($chef_dir | path exists) { return [] }

    ls $chef_dir
    | where type == dir
    | where { |it| ($it.name | path join "config.yml") | path exists }
    | get name
    | path basename
}

# Chef environment switcher
export def --env "chef.env" [
    cmd: string@chef_env_subcommands = "set"
    query?: string
] {
    let chef_dir = ($env.CHEF_ENV_DIR? | default ($env.HOME | path join ".chef"))

    match $cmd {
        "set" => {
            if ($query | is-not-empty) and (($chef_dir | path join $query "config.yml") | path exists) {
                $env.CHEF_ENV = $query
                print $"CHEF_ENV set to ($query)"
                return
            }

            let configs = (chef_available_configs | to text)
            if ($configs | is-empty) {
                print -e $"No Chef configurations found under ($chef_dir)"
                return 1
            }

            let pick = (
                $configs
                | fzf --height 40% --border
                    --prompt "Select Chef config > "
                    --preview $"bat --style=plain --paging=never ($chef_dir)/{}/config.yml"
                    --preview-window "right:70%"
                    --query ($query | default "")
                | str trim
            )

            if ($pick | is-not-empty) {
                $env.CHEF_ENV = $pick
                print $"CHEF_ENV set to ($pick)"
            }
        }
        "clear" => {
            if "CHEF_ENV" in $env {
                hide-env -i CHEF_ENV
                print "CHEF_ENV cleared"
            } else {
                print "CHEF_ENV was not set"
            }
        }
        "show" => {
            if "CHEF_ENV" in $env {
                print $"CHEF_ENV=($env.CHEF_ENV)"
            } else {
                print "CHEF_ENV is not set"
            }
        }
        "list" => {
            chef_available_configs | each { |it| print $"  - ($it)" }
        }
        _ => {
            print "Usage: chef.env {set|clear|show|list}"
            return 1
        }
    }
}
