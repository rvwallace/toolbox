# Kubernetes shell helpers for Nushell

def k_env_subcommands [] {
    [
        { value: "select", description: "Pick a kubeconfig file from ~/.kube (fzf)" }
        { value: "context", description: "Pick a kubectl context (fzf)" }
        { value: "namespace", description: "Set namespace on current context (fzf if no arg)" }
        { value: "ns", description: "Set namespace on current context (alias)" }
        { value: "clear", description: "Clear KUBECONFIG and unset current context" }
    ]
}

# Kubernetes environment switcher
export def --env "k.env" [
    cmd: string@k_env_subcommands = "select"
    arg?: string
] {
    if (which kubectl | is-empty) {
        print -e "k.env: kubectl not found"
        return 1
    }

    let kube_dir = ($env.HOME | path join ".kube")

    match $cmd {
        "select" => {
            if not ($kube_dir | path exists) {
                print -e $"($kube_dir) not found"
                return 1
            }

            let files = (ls $kube_dir | where type == file | get name | path basename | to text)
            if ($files | is-empty) {
                print -e "no kubeconfigs in ~/.kube"
                return 1
            }

            let pick = (
                $files
                | fzf --height 40% --border
                    --prompt "kubeconfig> "
                    --preview $"bat --style=numbers --color=always -l yaml ($kube_dir)/{} err> /dev/null"
                    --preview-window "right:70%"
                | str trim
            )

            if ($pick | is-not-empty) {
                let fullpath = ($kube_dir | path join $pick)
                $env.KUBECONFIG = $fullpath
                $env.KUBE_CONFIG_PATH = $fullpath
                print $"kubeconfig set to ($fullpath)"
                kubectl config current-context
            }
        }
        "context" => {
            let contexts = (kubectl config get-contexts -o name | lines | to text)
            let pick = ($contexts | fzf --height 40% --prompt "Context> " | str trim)
            if ($pick | is-not-empty) {
                kubectl config use-context $pick
            }
        }
        "namespace" | "ns" => {
            if ($arg | is-empty) {
                let ns_list = (kubectl get ns -o json | from json | get items.metadata.name | to text)
                let pick = ($ns_list | fzf --height 30% --prompt "namespace> " | str trim)
                if ($pick | is-not-empty) {
                    kubectl config set-context --current --namespace $pick
                }
            } else {
                kubectl config set-context --current --namespace $arg
            }
        }
        "clear" => {
            hide-env -i KUBECONFIG KUBE_CONFIG_PATH
            kubectl config unset current-context err> /dev/null
            print "kubeconfig cleared"
        }
        _ => {
            print "Usage: k.env {select|context|namespace|ns|clear}"
            return 1
        }
    }
}

export alias "k.ctx-list" = kubectl config get-contexts
export alias "k.get-all" = kubectl get all --all-namespaces
