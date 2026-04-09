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
compdef k=kubectl
