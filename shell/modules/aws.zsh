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

# --- Starship Prompt AWS Token TTL Helper ---
_toolbox_aws_token_ttl() {
  emulate -L zsh -o extended_glob

  local profile=${SC_AWS_TOKEN_PROFILE:-techops}
  local credentials_file=${AWS_SHARED_CREDENTIALS_FILE:-$HOME/.aws/credentials}
  local line section expires

  [[ -r "$credentials_file" ]] || return 1

  while IFS= read -r line; do
    if [[ "$line" == \[*\] ]]; then
      section="${line#\[}"
      section="${section%\]}"
      continue
    fi

    if [[ "$section" == "$profile" && "$line" == x_security_token_expires[[:space:]]#=* ]]; then
      expires="${line#*=}"
      expires="${expires##[[:space:]]#}"
      expires="${expires%%[[:space:]]#}"
      break
    fi
  done < "$credentials_file"

  [[ -n "$expires" ]] || return 1

  local normalized=$expires
  if [[ "$normalized" == *[+-][0-9][0-9]:[0-9][0-9] ]]; then
    normalized="${normalized%:*}${normalized##*:}"
  fi

  local expires_epoch
  expires_epoch=$(strftime -r "%Y-%m-%dT%H:%M:%S%z" "$normalized" 2>/dev/null) ||
    expires_epoch=$(strftime -r "%Y-%m-%dT%H%M%S%z" "$normalized" 2>/dev/null) ||
    return 1

  local remaining_seconds=$((expires_epoch - EPOCHSECONDS))
  local abs_seconds=${remaining_seconds#-}
  local hours=$((abs_seconds / 3600))
  local minutes=$(((abs_seconds % 3600) / 60))
  local seconds=$((abs_seconds % 60))
  local formatted

  printf -v formatted "%02d:%02d:%02d" "$hours" "$minutes" "$seconds"
  (( remaining_seconds < 0 )) && formatted="-$formatted"
  print -r -- "$formatted"
}

_toolbox_refresh_aws_token_ttl() {
  [[ -n "$AWS_PROFILE" ]] || {
    unset SC_AWS_TOKEN_TTL
    return
  }

  local now=${EPOCHSECONDS:-0}
  local cache_seconds=${SC_AWS_TOKEN_CACHE_SECONDS:-60}

  (( now > 0 )) || return
  (( now - ${SC_AWS_TOKEN_LAST_CHECK:-0} < cache_seconds )) && return

  typeset -g SC_AWS_TOKEN_LAST_CHECK=$now
  export SC_AWS_TOKEN_TTL
  SC_AWS_TOKEN_TTL="$(_toolbox_aws_token_ttl)" || unset SC_AWS_TOKEN_TTL
}

if [[ -o interactive ]]; then
  zmodload zsh/datetime 2>/dev/null || true
  autoload -Uz add-zsh-hook 2>/dev/null || true
  add-zsh-hook precmd _toolbox_refresh_aws_token_ttl 2>/dev/null || true
fi
