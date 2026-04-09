#!/usr/bin/env bash
# Kubernetes Interactive shell module

toolbox_require_commands kube kubectl || return 0

# --- Aliases ---
alias k="kubectl"
alias k.ctx-list="kubectl config get-contexts"
alias k.get-all="kubectl get all --all-namespaces"

# --- Functions ---
k.env() {
  _kubectl_require() {
    command -v "$1" >/dev/null 2>&1 || { echo "kubectl.env: missing command '$1'" >&2; return 1; }
  }

  _kube_clear() {
    unset KUBECONFIG KUBE_CONFIG_PATH
    kubectl config unset current-context 2>/dev/null
    echo "kubeconfig cleared"
  }

  _kube_select_config() {
    _kubectl_require kubectl || return
    command -v fzf >/dev/null || { echo "fzf not found" >&2; return 1; }
    local dir="$HOME/.kube"
    [[ -d $dir ]] || { echo "$dir not found" >&2; return 1; }

    # Enable nullglob to safely match files
    local -a files
    if [[ -n "${ZSH_VERSION:-}" ]]; then
      # Zsh nullglob approach
      setopt localoptions nullglob
      files=("$dir"/*)
    else
      # Bash nullglob approach
      shopt -s nullglob
      files=("$dir"/*)
      shopt -u nullglob
    fi

    # Filter out directories
    local -a real_files
    for f in "${files[@]}"; do
      [[ -f "$f" ]] && real_files+=("$f")
    done

    [[ ${#real_files[@]} -gt 0 ]] || { echo "no kubeconfigs in $dir" >&2; return 1; }

    local pick
    # If bash 4+ / zsh is used, we can dynamically build options. 
    # To be extremely foolproof and preserve the fzf preview feature exactly across Posix:
    local bname
    local file_list_str=""
    for f in "${real_files[@]}"; do
      bname=$(basename "$f")
      file_list_str+="${bname}"$'\n'
    done

    pick=$(printf '%s' "$file_list_str" \
      | fzf --height 40% --border \
            --prompt "kubeconfig> " \
            --preview 'bat --style=numbers --color=always -l yaml ~/.kube/{} 2>/dev/null || cat ~/.kube/{}' \
            --preview-window=right:70%)
            
    [[ -n "$pick" ]] || return

    local fullpath="${dir}/${pick}"
    export KUBECONFIG="$fullpath"
    export KUBE_CONFIG_PATH="$fullpath"
    echo "kubeconfig set to $fullpath"
    kubectl config current-context
  }

  _kube_select_context() {
    _kubectl_require kubectl || return
    command -v fzf >/dev/null || { echo "fzf not found" >&2; return 1; }
    local context
    context=$(kubectl config get-contexts -o name | fzf --height 40% --prompt "Context> ")
    [[ -n $context ]] && kubectl config use-context "$context"
  }

  _kube_select_namespace() {
    _kubectl_require kubectl || return
    if [[ -z "$1" ]]; then
      command -v fzf >/dev/null || { echo "fzf not found" >&2; return 1; }
      local ns
      ns=$(kubectl get ns -o jsonpath='{.items[*].metadata.name}' \
           | tr ' ' '\n' \
           | fzf --height 30% --prompt "namespace> ")
      [[ -n "$ns" ]] || return
      kubectl config set-context --current --namespace "$ns"
    else
      kubectl config set-context --current --namespace "$1"
    fi
  }

  local cmd="$1"
  [[ -n "$1" ]] && shift

  case "$cmd" in
    select) _kube_select_config "$@" ;;
    context) _kube_select_context "$@" ;;
    namespace|ns) _kube_select_namespace "$@" ;;
    clear) _kube_clear "$@" ;;
    *)
      cat <<'EOF'
Usage: k.env {select|context|namespace|ns|clear}

Commands:
  select           - Pick a kubeconfig file from ~/.kube (fzf)
  context          - Pick a kubectl context (fzf)
  namespace | ns   - Pick or set namespace on current context (fzf if no arg)
  clear            - Clear KUBECONFIG/KUBE_CONFIG_PATH and unset current-context
EOF
      return 1
      ;;
  esac
}
