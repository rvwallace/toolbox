# shellcheck shell=zsh
# Chef Interactive shell module completions

toolbox_require_commands chef knife || return 0

# --- Completions ---
_chef_env_complete_configs() {
  local -a configs
  # Execute via subshell using the newly defined shell function in context!
  configs=(${(f)"$(chef.env list 2>/dev/null | awk '{print $2}')"})
  _describe 'Chef configurations' configs
}

_chef_env() {
  local state
  local -a subcmds

  subcmds=(
    'set:Set the Chef environment'
    'clear:Clear the Chef environment'
    'show:Show the current Chef environment'
    'list:List available Chef configurations'
  )

  _arguments \
    '1:command:->cmds' \
    '*::arg:->args'

  case $state in
    cmds)
      _describe -t commands 'chef.env commands' subcmds
      ;;
    args)
      case ${words[2]:-} in
        set)
          _chef_env_complete_configs
          ;;
      esac
      ;;
  esac
}

compdef _chef_env chef.env
