#!/usr/bin/env bash
# AWS shell functions

toolbox_require_commands aws aws || return 0

aws.caller_identity() {
    aws sts get-caller-identity --output yaml | column -t
}

# Number of days to cache AWS profile list (used by aws.env function)
# Override this in ~/.zshrc or ~/.zshrc.local.pre
SC_AWS_CACHE_DAYS="${SC_AWS_CACHE_DAYS:-30}"

# AWS regions list with descriptions
# Format: 'region-code:Description'
AWS_REGIONS=(
  'us-east-1:US East (N. Virginia)'
  'us-east-2:US East (Ohio)'
  'us-west-1:US West (N. California)'
  'us-west-2:US West (Oregon)'
  'eu-west-1:Europe (Ireland)'
  'eu-west-2:Europe (London)'
  'eu-west-3:Europe (Paris)'
  'eu-central-1:Europe (Frankfurt)'
  'eu-central-2:Europe (Zurich)'
  'eu-north-1:Europe (Stockholm)'
  'eu-south-1:Europe (Milan)'
  'eu-south-2:Europe (Spain)'
  'ap-northeast-1:Asia Pacific (Tokyo)'
  'ap-northeast-2:Asia Pacific (Seoul)'
  'ap-northeast-3:Asia Pacific (Osaka)'
  'ap-southeast-1:Asia Pacific (Singapore)'
  'ap-southeast-2:Asia Pacific (Sydney)'
  'ap-southeast-3:Asia Pacific (Jakarta)'
  'ap-southeast-4:Asia Pacific (Melbourne)'
  'ap-south-1:Asia Pacific (Mumbai)'
  'ap-south-2:Asia Pacific (Hyderabad)'
  'ap-east-1:Asia Pacific (Hong Kong)'
  'sa-east-1:South America (São Paulo)'
  'ca-central-1:Canada (Central)'
  'ca-west-1:Canada (Calgary)'
  'af-south-1:Africa (Cape Town)'
  'me-south-1:Middle East (Bahrain)'
  'me-central-1:Middle East (UAE)'
)

# Usage: _aws_get_profiles_cache [-f]
# Returns: Prints cached profiles, one per line
_aws_get_profiles_cache() {
  local force_update=false
  [[ "$1" == "-f" ]] && force_update=true

  local stat_fmt="-f %m"
  [[ "$(uname)" == "Linux" ]] && stat_fmt="-c %Y"

  local cache_dir="${HOME}/.cache/silentcastle"
  local cache_file="${cache_dir}/aws.profiles.cache"
  local cache_age_days="${SC_AWS_CACHE_DAYS:-30}"

  if [[ ! -d "$cache_dir" ]]; then
    mkdir -p "$cache_dir" || return 1
    chmod 700 "$cache_dir" || return 1
  fi

  local needs_update=false

  if [[ ! -f "$cache_file" ]]; then
    needs_update=true
  elif [[ "$force_update" == true ]]; then
    needs_update=true
  else
    local cache_mtime
    cache_mtime=$(stat $stat_fmt "$cache_file" 2>/dev/null)
    if [[ ! "$cache_mtime" =~ ^[0-9]+$ ]]; then
      needs_update=true
    else
      local current_time
      current_time=$(date +%s)
      local cache_age_seconds=$((current_time - cache_mtime))
      local max_age_seconds=$((cache_age_days * 86400))

      if (( cache_age_seconds > max_age_seconds )); then
        needs_update=true
      fi
    fi
  fi

  if [[ "$needs_update" == true ]]; then
    if command -v aws >/dev/null 2>&1; then
      aws configure list-profiles 2>/dev/null > "$cache_file"
      chmod 600 "$cache_file"
    else
      echo "aws CLI not found" >&2
      return 1
    fi
  fi

  cat "$cache_file" 2>/dev/null
}

aws.env() {
  case "${1:-}" in
    set|profile|region)
      local _subcmd="$1"; shift
      local _out
      _out="$(aws-env "$_subcmd" "$@")" || return $?
      eval "$_out"
      ;;
    show|token-status)
      aws-env "$@"
      ;;
    clear)
      unset AWS_PROFILE AWS_REGION AWS_DEFAULT_REGION \
            AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY \
            AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
      echo "AWS env cleared"
      ;;
    *)
      aws-env --help
      return 1
      ;;
  esac
}
