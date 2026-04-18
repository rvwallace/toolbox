# shellcheck shell=zsh
# Kubernetes Interactive shell module completions

toolbox_require_commands kube kubectl || return 0

# --- Completions ---
_k_env() {
  local -a subcommands
  local state

  subcommands=(
    'select:Pick a kubeconfig file from ~/.kube (fzf)'
    'context:Pick a kubectl context (fzf)'
    'namespace:Set namespace on current context (fzf if no arg)'
    'ns:Set namespace on current context (alias)'
    'clear:Clear KUBECONFIG/KUBE_CONFIG_PATH and unset current-context'
  )

  _arguments \
    '1:command:->cmds' \
    '*::arg:->args'

  case $state in
    cmds)
      _describe -t commands 'k.env commands' subcommands
      ;;
    args)
      case ${words[2]:-} in
        namespace|ns)
          local -a namespaces
          namespaces=(${(f)"$(kubectl get ns -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n')"})
          _describe 'namespaces' namespaces
          ;;
      esac
      ;;
  esac
}

compdef _k_env k.env

_toolbox_kubectl_load_zsh_completion() {
  local cache_dir cache_file version_file current_version
  cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/silentcastle/toolbox/completions"
  cache_file="${cache_dir}/_kubectl"
  version_file="${cache_dir}/kubectl.version"
  current_version="$(kubectl version --client=true -o yaml 2>/dev/null | tr -d '\r')"
  [[ -n "$current_version" ]] || return 0

  toolbox_completion_cache_ensure "$cache_file" "$version_file" "$current_version" kubectl completion zsh || return 0

  # shellcheck source=/dev/null
  source "$cache_file" >/dev/null 2>&1 || return 0
}

_toolbox_kubectl_load_zsh_completion
compdef k=kubectl
