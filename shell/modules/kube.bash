# shellcheck shell=bash
# Kubernetes Interactive shell module bash completions

toolbox_require_commands kube kubectl || return 0

_kube_env_complete_bash() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cword=$COMP_CWORD
    local words=("${COMP_WORDS[@]}")

    local commands="select context namespace ns clear"

    case "${prev}" in
        namespace|ns)
            local namespaces
            namespaces=$(kubectl get ns -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
            COMPREPLY=( $(compgen -W "${namespaces}" -- "${cur}") )
            return
            ;;
    esac

    if [[ "${cword}" == 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
    fi
}

complete -F _kube_env_complete_bash k.env

# Provide standard completions for the `k` alias
if command -v kubectl >/dev/null 2>&1; then
    source <(kubectl completion bash) 2>/dev/null
    complete -o default -F __start_kubectl k 2>/dev/null
fi
