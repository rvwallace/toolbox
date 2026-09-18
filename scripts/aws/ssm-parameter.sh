#!/usr/bin/env bash
# toolbox-platforms: linux,darwin
set -euo pipefail

usage() {
  local script=${0##*/}
  cat <<EOF
${script} - Select and read an AWS Systems Manager Parameter Store parameter.

TL;DR
  ${script} my-profile us-east-1
  ${script} --quiet --name /app/database/password my-profile us-east-1

USAGE
  ${script} [OPTIONS] [PROFILE] [REGION]

OPTIONS
  -n, --name PARAMETER  Read this parameter without fzf.
  -q, --quiet           Print only the parameter value.
  -r, --refresh         Download a new parameter-name list.
      --show-cache      Show the cache directory and exit.
      --clear-cache     Delete all cached parameter-name lists and exit.
  -h, --help            Show this help.

EXAMPLES
  Select a parameter with fzf:
    ${script} example-profile us-east-1

  Download a new list before selection:
    ${script} --refresh example-profile us-east-1

  Read a parameter by name:
    ${script} --name /example/application/password example-profile us-east-1

  Use the value in another script:
    password=\$(${script} --quiet --name /example/application/password example-profile us-east-1)

  Show or clear the cache:
    ${script} --show-cache
    ${script} --clear-cache

DEFAULTS
  PROFILE uses \$AWS_PROFILE, or "default" when \$AWS_PROFILE is not set.
  REGION uses \$AWS_REGION, \$AWS_DEFAULT_REGION, or the AWS profile configuration.

CACHE
  The script obeys \$XDG_CACHE_HOME. If it is not set, the script uses:
    \$HOME/.cache/silentcastle/ssm-parameter/

  The cache contains parameter names only. It does not contain parameter values.

REQUIREMENTS
  Install and configure the AWS CLI. Interactive mode also requires fzf.
  The AWS identity must have ssm:DescribeParameters and ssm:GetParameter access.
  SecureString parameters also require permission to use their AWS KMS key.

OUTPUT
  Normal output contains the parameter name and decrypted value.
  Quiet output contains only the decrypted value.

  CAUTION: The command prints secret values. Do not send the output to logs.
EOF
}

refresh=false
quiet=false
show_cache=false
clear_cache=false
parameter=
positional=()

while (($#)); do
  case $1 in
    -r|--refresh) refresh=true ;;
    -q|--quiet) quiet=true ;;
    --show-cache) show_cache=true ;;
    --clear-cache) clear_cache=true ;;
    -n|--name)
      [[ $# -gt 1 ]] || { echo "$1 requires a parameter name" >&2; exit 2; }
      parameter=$2
      shift
      ;;
    -h|--help) usage; exit 0 ;;
    --) shift; positional+=("$@"); break ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) positional+=("$1") ;;
  esac
  shift
done

[[ ${#positional[@]} -le 2 ]] || { echo "Too many arguments" >&2; exit 2; }
$show_cache && $clear_cache && { echo "Use only one cache option at a time." >&2; exit 2; }

if [[ -n ${XDG_CACHE_HOME:-} && $XDG_CACHE_HOME == /* ]]; then
  base_cache=$XDG_CACHE_HOME
elif [[ -n ${HOME:-} ]]; then
  base_cache=$HOME/.cache
else
  echo "HOME is not set, and XDG_CACHE_HOME is not an absolute path." >&2
  exit 1
fi
cache_dir=$base_cache/silentcastle/ssm-parameter
legacy_cache_dir=$base_cache/ssm-parameter

# Migrate legacy cache if it exists and new cache does not
if [[ -d "$legacy_cache_dir" && ! -d "$cache_dir" ]]; then
  mkdir -p "$(dirname "$cache_dir")"
  mv "$legacy_cache_dir" "$cache_dir" 2>/dev/null || true
fi

if $show_cache; then
  printf '%s\n' "$cache_dir"
  exit 0
fi

if $clear_cache; then
  rm -rf -- "$cache_dir" "$legacy_cache_dir"
  printf 'Cleared cache: %s\n' "$cache_dir"
  exit 0
fi

profile=${positional[0]:-${AWS_PROFILE:-default}}
region=${positional[1]:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}

command -v aws >/dev/null || { echo "aws is required" >&2; exit 1; }
region=${region:-$(aws configure get region --profile "$profile" 2>/dev/null || true)}

if [[ -z $region ]]; then
  echo "No region set. Pass one as the second argument or configure AWS_REGION." >&2
  exit 1
fi

safe_profile=${profile//[^[:alnum:]._-]/_}
safe_region=${region//[^[:alnum:]._-]/_}
parameter_file="$cache_dir/ssm-parameters-${safe_profile}-${safe_region}.txt"

if $refresh || { [[ -z $parameter ]] && [[ ! -s $parameter_file ]]; }; then
  mkdir -p "$cache_dir"
  tmp=$(mktemp "$cache_dir/.ssm-parameters.XXXXXX")
  trap 'rm -f "$tmp"' EXIT

  echo "Fetching parameter names for ${profile}/${region}..." >&2
  AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 aws ssm describe-parameters \
    --profile "$profile" \
    --region "$region" \
    --query 'Parameters[].Name' \
    --output text \
    | tr '\t' '\n' > "$tmp"

  mv "$tmp" "$parameter_file"
  trap - EXIT
fi

if [[ -z $parameter ]]; then
  command -v fzf >/dev/null || { echo "fzf is required" >&2; exit 1; }
  parameter=$(fzf --prompt="SSM (${profile}/${region})> " < "$parameter_file") || exit 0
fi

[[ -n $parameter ]] || exit 0

value=$(aws ssm get-parameter \
  --profile "$profile" \
  --region "$region" \
  --name "$parameter" \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text)

if $quiet; then
  printf '%s\n' "$value"
else
  printf 'Parameter: %s\nValue: %s\n' "$parameter" "$value"
fi
