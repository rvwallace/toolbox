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
  _aws_require() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1 || { echo "aws.env: missing command '$cmd'" >&2; return 1; }
  }

  _aws_fzf_select() {
    local query="$1"; shift
    local fzf_opts=(--border --ansi --exit-0 --query "$query" --select-1 --exact)
    [[ -n "$TMUX" ]] && fzf_opts+=(--tmux=center) || fzf_opts+=(--height=40%)
    printf '%s\n' "$@" | fzf "${fzf_opts[@]}"
  }

  _aws_profile_select() {
    _aws_require fzf || return

    local force_flag=""
    [[ "$1" == "-f" ]] && { force_flag="-f"; shift; }

    local profiles
    profiles=$(_aws_get_profiles_cache "$force_flag") || { echo "Failed to get AWS profiles" >&2; return 1; }

    # Bash 4+ required for mapfile
    local -a profiles_arr
    if command -v mapfile >/dev/null 2>&1; then
      mapfile -t profiles_arr <<< "$profiles"
    else
      # Fallback for old Bash / Zsh strictly in sh compliance (though zsh doesn't emulate readarray)
      # In Zsh, reading lines into array requires different syntax. 
      # Since this runs cross-shell, IFS logic handles it safely.
      local IFS=$'\n'
      profiles_arr=($profiles)
    fi

    local profile_selected
    profile_selected=$(_aws_fzf_select "$1" "${profiles_arr[@]}")
    [[ -z "$profile_selected" ]] && { echo "AWS Profile not updated."; return 1; }

    export AWS_PROFILE="$profile_selected"
    echo "AWS Profile set to $AWS_PROFILE"
  }

  _aws_region_select() {
    _aws_require fzf || return

    local region_selected
    region_selected=$(_aws_fzf_select "${1:-us-}" "${AWS_REGIONS[@]}")
    [[ -z "$region_selected" ]] && { echo "AWS Region not updated."; return 1; }

    export AWS_DEFAULT_REGION="${region_selected%%:*}"
    export AWS_REGION="$AWS_DEFAULT_REGION"
    echo "AWS Region set to $AWS_DEFAULT_REGION"
  }

  _aws_env_set() {
    _aws_profile_select "$1" && _aws_region_select "$2"
  }

  _aws_env_clear() {
    unset AWS_PROFILE AWS_REGION AWS_DEFAULT_REGION \
          AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY \
          AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
    echo "AWS env cleared"
  }

  _aws_env_show() {
    local rows=("Variable|Value")

    if command -v aws.token.timeout.sh >/dev/null 2>&1; then
      local ttl=$(aws.token.timeout.sh -t 2>/dev/null)
      [[ -n $ttl ]] && rows+=("AWS_TOKEN_TTL|$ttl")
    fi

    # Using -v requires Bash 4.2+ or Zsh. Fallback to length check for older shells.
    [[ -n "${AWS_PROFILE:-}" ]]           && rows+=("AWS_PROFILE|$AWS_PROFILE")
    [[ -n "${AWS_REGION:-}" ]]            && rows+=("AWS_REGION|$AWS_REGION")
    [[ -n "${AWS_DEFAULT_PROFILE:-}" ]]   && rows+=("AWS_DEFAULT_PROFILE|$AWS_DEFAULT_PROFILE")
    [[ -n "${AWS_DEFAULT_REGION:-}" ]]    && rows+=("AWS_DEFAULT_REGION|$AWS_DEFAULT_REGION")
    [[ -n "${AWS_ACCESS_KEY_ID:-}" ]]     && rows+=("AWS_ACCESS_KEY_ID|$AWS_ACCESS_KEY_ID")
    [[ -n "${AWS_SECRET_ACCESS_KEY:-}" ]] && rows+=("AWS_SECRET_ACCESS_KEY|${AWS_SECRET_ACCESS_KEY:0:5}*****")
    [[ -n "${AWS_SESSION_TOKEN:-}" ]]     && rows+=("AWS_SESSION_TOKEN|${AWS_SESSION_TOKEN:0:5}*****")
    [[ -n "${AWS_SECURITY_TOKEN:-}" ]]    && rows+=("AWS_SECURITY_TOKEN|${AWS_SECURITY_TOKEN:0:5}*****")

    (( ${#rows[@]} == 1 )) && rows+=("_No AWS environment variables set_|")

    local output=$(printf '%s\n' "${rows[@]}")
    if command -v column >/dev/null 2>&1; then
      printf '%s\n' "$output" | column -t -s '|'
    else
      printf '%s\n' "$output"
    fi
  }

  _aws_env_token_status() {
    local creds_file="$HOME/.aws/credentials"

    if [[ ! -f "$creds_file" ]]; then
      echo "AWS credentials file not found: $creds_file" >&2
      return 1
    fi

    local profile="${SAML2AWS_PROFILE:-${AWS_SSO_PROFILE:-${AWS_PROFILE:-default}}}"
    local expires_line
    expires_line=$(
      awk -v profile="$profile" '
        /^\[/ { in_profile = ($0 == "[" profile "]"); next }
        in_profile && $1 == "x_security_token_expires" { print; exit }
      ' "$creds_file"
    )

    if [[ -z "$expires_line" ]]; then
      echo "No token expiration found for [$profile] profile" >&2
      echo "Run 'saml2aws login' to authenticate" >&2
      return 1
    fi

    local expires_time
    expires_time=$(printf '%s\n' "$expires_line" | cut -d'=' -f2- | xargs)

    if [[ -z "$expires_time" ]]; then
      echo "Token expires: (missing value)"
      return 0
    fi

    local expires_epoch current_epoch formatted_time
    if command -v python3 >/dev/null 2>&1; then
      local py_output
      py_output=$(
        python3 - "$expires_time" <<'PY' 2>/dev/null
import sys
from datetime import datetime, timezone

text = sys.argv[1].strip()
if not text:
    raise SystemExit(1)

raw = " ".join(text.split())
if raw.endswith(" UTC"):
    raw = raw[:-4] + "+00:00"
if raw.endswith("Z"):
    raw = raw[:-1] + "+00:00"

try:
    dt = datetime.fromisoformat(raw)
except ValueError:
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    else:
        raise SystemExit(1)

if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)

now = datetime.now(timezone.utc)
local_dt = dt.astimezone()

print(int(dt.timestamp()))
print(local_dt.strftime("%H:%M"))
print(int(now.timestamp()))
PY
      )

      if [[ -n "$py_output" ]]; then
        IFS=$'\n' read -r expires_epoch formatted_time current_epoch <<<"$py_output"
      fi
    fi

    if [[ -z "$expires_epoch" || -z "$current_epoch" ]]; then
      if command -v gdate >/dev/null 2>&1; then
        expires_epoch=$(gdate -d "$expires_time" +%s 2>/dev/null)
        formatted_time=$(gdate -d "$expires_time" '+%H:%M' 2>/dev/null)
        current_epoch=$(gdate +%s)
      elif date -d "@0" +%s >/dev/null 2>&1; then
        expires_epoch=$(date -d "$expires_time" +%s 2>/dev/null)
        formatted_time=$(date -d "$expires_time" '+%H:%M' 2>/dev/null)
        current_epoch=$(date +%s)
      fi
    fi

    if [[ -z "$expires_epoch" || -z "$current_epoch" ]]; then
      echo "Token expires: $expires_time (unable to parse time)"
      return 0
    fi

    local time_diff=$((expires_epoch - current_epoch))
    local display_time=${formatted_time:-$expires_time}
    local mins=$((time_diff / 60))

    if (( time_diff < 0 )); then
      echo "Token EXPIRED $(( -mins )) minutes ago"
      echo "Run 'saml2aws login' to refresh"
      return 1
    elif (( time_diff < 3600 )); then
      echo "Token expires in $mins minutes ($display_time)"
      (( time_diff < 300 )) && echo "Run 'saml2aws login' soon"
    else
      echo "Token valid for $((time_diff / 3600))h $((mins % 60))m (expires $display_time)"
    fi
  }

  local cmd="${1:-}"
  [[ -n "$cmd" ]] && shift

  case "$cmd" in
    set) _aws_env_set "$@" ;;
    profile) _aws_profile_select "$@" ;;
    region) _aws_region_select "$@" ;;
    show) _aws_env_show "$@" ;;
    clear) _aws_env_clear "$@" ;;
    token-status) _aws_env_token_status "$@" ;;
    *)
      cat <<'EOF'
Usage: aws.env {set|profile|region|show|clear|token-status}

Commands:
  set          - Select AWS profile and region interactively
  profile      - Select AWS profile only
  region       - Select AWS region only
  show         - Display current AWS environment
  clear        - Clear all AWS environment variables
  token-status - Check AWS token expiration

Environment Variables:
  SAML2AWS_PROFILE=<profile>               - Profile to check for token expiration (highest priority)
  AWS_SSO_PROFILE=<profile>                - Alternative profile variable (fallback)
  AWS_PROFILE=<profile>                    - AWS profile (used as final fallback)
EOF
      return 1
      ;;
  esac
}
