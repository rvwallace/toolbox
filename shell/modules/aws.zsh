# shellcheck shell=zsh
# AWS Interactive shell module completions

toolbox_require_commands aws aws || return 0

# --- Completions ---
_aws_env_complete_profiles() {
  local profiles_output
  profiles_output=$(_aws_get_profiles_cache 2>/dev/null)
  
  if [[ -n "$profiles_output" ]]; then
    local -a profiles
    profiles=(${(f)profiles_output})
    _describe 'AWS profiles' profiles
  fi
}

_aws_env_complete_regions() {
  _describe 'AWS regions' AWS_REGIONS
}

_aws_env() {
  local -a subcommands
  local state

  subcommands=(
    'set:Select AWS profile and region interactively'
    'profile:Select AWS profile only'
    'region:Select AWS region only'
    'show:Display current AWS environment'
    'clear:Clear all AWS environment variables'
    'token-status:Check AWS token expiration'
  )

  _arguments \
    '1:command:->cmds' \
    '*::arg:->args'

  case $state in
    cmds)
      _describe -t commands 'aws.env commands' subcommands
      ;;
    args)
      case ${words[1]:-} in
        profile)
          _aws_env_complete_profiles
          ;;
        region)
          _aws_env_complete_regions
          ;;
        set)
          if (( CURRENT == 2 )); then
            _aws_env_complete_profiles
          elif (( CURRENT == 3 )); then
            _aws_env_complete_regions
          fi
          ;;
      esac
      ;;
  esac
}

compdef _aws_env aws.env
