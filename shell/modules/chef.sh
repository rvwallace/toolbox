#!/usr/bin/env bash
# Chef Interactive shell module

toolbox_require_commands chef knife || return 0

# --- Functions ---
chef.env() {
  _chef_env_dir() {
    printf '%s' "${CHEF_ENV_DIR:-$HOME/.chef}"
  }

  _chef_env_configs() {
    local chef_dir
    chef_dir=$(_chef_env_dir)
    [[ -d "$chef_dir" ]] || return 1
    find "$chef_dir" -maxdepth 1 -mindepth 1 -type d -exec test -e "{}/config.yml" \; -exec basename {} \; | sort -u
  }

  _chef_env_print() {
    local config
    while IFS= read -r config; do
      printf '  - %s\n' "$config"
    done
  }

  _chef_env_list() {
    local configs
    configs=$(_chef_env_configs) || {
      echo "No Chef configurations found under $(_chef_env_dir)" >&2
      return 1
    }
    _chef_env_print <<<"$configs"
  }

  _chef_env_show() {
    if [[ -n "$CHEF_ENV" ]]; then
      echo "CHEF_ENV=$CHEF_ENV"
    else
      echo "CHEF_ENV is not set"
    fi
  }

  _chef_env_clear() {
    if [[ -n "$CHEF_ENV" ]]; then
      unset CHEF_ENV
      echo "CHEF_ENV cleared"
    else
      echo "CHEF_ENV was not set"
    fi
  }

  _chef_env_select_with_menu() {
    local configs="$1"
    local selection
    echo "Available Chef configurations:"
    _chef_env_print <<<"$configs"
    printf '\nEnter the name to use: '
    read -r selection
    printf '%s' "$selection"
  }

  _chef_env_set() {
    local initial_query="$1"
    local chef_dir
    chef_dir=$(_chef_env_dir)

    if [[ -n "$initial_query" && -d "$chef_dir/$initial_query" && -f "$chef_dir/$initial_query/config.yml" ]]; then
      export CHEF_ENV="$initial_query"
      echo "CHEF_ENV set to $CHEF_ENV"
      return 0
    fi

    local configs
    configs=$(_chef_env_configs) || {
      echo "No Chef configurations found under $chef_dir" >&2
      return 1
    }

    local selection=""
    if command -v fzf >/dev/null 2>&1; then
      local preview_cmd="cat"
      if command -v bat >/dev/null 2>&1; then
        preview_cmd="bat --style=plain --paging=never"
      fi
      selection=$(printf '%s\n' "$configs" |
        fzf --height 40% \
            --border \
            --preview="$preview_cmd $chef_dir/{}/config.yml" \
            --preview-window=right:70% \
            --prompt='Select Chef config > ' \
            --query="$initial_query" \
            --select-1 \
            --exit-0)
    else
      selection=$(_chef_env_select_with_menu "$configs")
    fi

    if [[ -z "$selection" ]]; then
      echo "No Chef environment selected"
      return 1
    fi

    export CHEF_ENV="$selection"
    echo "CHEF_ENV set to $CHEF_ENV"
  }

  local command="$1"
  [[ -n "$1" ]] && shift

  case "$command" in
    set) _chef_env_set "$@" ;;
    clear) _chef_env_clear ;;
    show) _chef_env_show ;;
    list) _chef_env_list ;;
    "")
      echo "Usage: chef.env <set|clear|show|list> [name]" >&2
      return 1
      ;;
    *)
      echo "Unknown command: $command" >&2
      echo "Usage: chef.env <set|clear|show|list> [name]" >&2
      return 1
      ;;
  esac
}
