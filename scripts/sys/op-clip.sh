#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: op.toclipboard.sh <item name> <user|vpnpass|otp|pass|website|custom> [custom label]

Copies the requested field from a 1Password item to your clipboard.

Positional arguments:
  item name   Name of the 1Password item to query
  field       Which field to copy:
                - user     : Username field
                - vpnpass  : VPN PIN plus current OTP
                - otp      : Current one-time password (TOTP)
                - pass     : Password field
                - website  : Website/URL field
                - custom   : Use a custom label (requires [custom label])

Examples:
  op.toclipboard.sh "JumpCloud" user
  op.toclipboard.sh "CA VPN" vpnpass
  op.toclipboard.sh "My Portal" website
  op.toclipboard.sh "JumpCloud" custom "MFA Token"

The command requires the 1Password CLI (`op`) and a clipboard utility
such as pbcopy (macOS), xclip (Linux), or clip (Windows).
EOF
}

error() {
  echo "Error: $1" >&2
  exit ${2:-1}
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "$1 is not installed or not in PATH"
  fi
}

copy_to_clipboard() {
  local data="$1"
  if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$data" | pbcopy
  elif command -v xclip >/dev/null 2>&1; then
    printf '%s' "$data" | xclip -selection clipboard
  elif command -v clip >/dev/null 2>&1; then
    printf '%s' "$data" | clip
  else
    error "No supported clipboard utility found (pbcopy, xclip, clip)"
  fi
}

fetch_field() {
  local item="$1"
  local field_type="$2"
  local custom_label="${3:-}"
  local label_field=""

  case "$field_type" in
    user)
      label_field="username"
      ;;
    vpnpass)
      label_field="PIN"
      ;;
    otp)
      label_field=""
      ;;
    pass)
      label_field="password"
      ;;
    website)
      label_field="website"
      ;;
    custom)
      if [[ -z "$custom_label" ]]; then
        error "Custom field type requires a label argument"
      fi
      label_field="$custom_label"
      ;;
    *)
      error "Invalid field type: $field_type"
      ;;
  esac

  local result
  if [[ -n "$label_field" ]]; then
    if ! result=$(op item get "$item" --fields label="$label_field"); then
      error "Failed to retrieve $field_type for $item"
    fi
  else
    if ! result=$(op item get "$item" --otp); then
      error "Failed to retrieve OTP for $item"
    fi
  fi

  if [[ "$field_type" == "vpnpass" ]]; then
    local otp_result
    if ! otp_result=$(op item get "$item" --otp); then
      error "Failed to retrieve OTP for $item"
    fi
    result="${result}${otp_result}"
  fi

  printf '%s' "$result"
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
    exit 0
  fi

  if [[ $# -lt 2 ]]; then
    usage
    exit 1
  fi

  local item_name="$1"
  shift
  local field_type="$1"
  shift
  local custom_label=""

  if [[ "$field_type" == "custom" ]]; then
    if [[ $# -lt 1 ]]; then
      usage
      exit 1
    fi
    custom_label="$1"
    shift
  fi

  require_command op

  local output
  output=$(fetch_field "$item_name" "$field_type" "$custom_label")
  copy_to_clipboard "$output"
  echo "Copied $field_type for $item_name to clipboard."
}

main "$@"
