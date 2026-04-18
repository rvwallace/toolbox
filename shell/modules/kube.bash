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
    _toolbox_kubectl_load_bash_completion() {
        local cache_dir cache_file version_file current_version
        cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/silentcastle/toolbox/completions"
        cache_file="${cache_dir}/kubectl.bash"
        version_file="${cache_dir}/kubectl.version"
        current_version="$(kubectl version --client=true -o yaml 2>/dev/null | tr -d '\r')"
        [[ -n "$current_version" ]] || return 0

        toolbox_completion_cache_ensure "$cache_file" "$version_file" "$current_version" kubectl completion bash || return 0

        # shellcheck source=/dev/null
        source "$cache_file" >/dev/null 2>&1 || return 0
    }

    _toolbox_kubectl_load_bash_completion
    complete -o default -F __start_kubectl k 2>/dev/null
fi
