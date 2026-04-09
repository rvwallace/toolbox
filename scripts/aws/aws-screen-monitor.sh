#!/usr/bin/env bash

# #############################################################################
# Script Name: aws-screen-monitor.sh
# Author: Robert Wallace
# Description: Monitor AWS EC2 instance console screenshots in real-time.
#              Displays instance state, status checks, and sends desktop
#              notification when the instance is ready to connect.
#              Useful for monitoring reboots and Windows patching.
# Usage: aws-screen-monitor.sh [instance-id (i-*)]
# Requirements: aws-cli, wezterm or kitty or iTerm2 (figurine optional)
# #############################################################################

set -euo pipefail

# Script System Configuration
readonly CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/silentcastle"
readonly SLEEP_TIME=5
readonly DEPENDENCIES=("aws" "base64")
readonly SPINNERS=(
  '.oOo.'        # Alternative 0
  '⣾⣽⣻⢿⡿⣟⣯⣷'     # Alternative 1
  '▁▃▄▅▆▇█▇▆▅▄▃' # Alternative 2
  '-\\|/'        # Alternative 3
)
readonly SPINNER="${SPINNERS[1]}" # Select spinner style
readonly DELAY=0.1                # Spinner delay

# Global variables
IMGCMD=""
INSTANCE=""
INSTANCE_NAME=""
NOTIFIED=false

# Functions
msg:error() {
  echo "[ERROR] $1" >&2
  exit 1
}

msg:info() {
  echo "[INFO] $1"
}

msg:warn() {
  echo "[WARN] $1" >&2
}

check_instance_id() {
  if [[ ! $1 =~ ^i-[a-zA-Z0-9]{8,17}$ ]]; then
    msg:error "Invalid instance ID format. Must start with 'i-' followed by 8-17 alphanumeric characters."
  fi
}

verify_aws_instance() {
  if ! aws ec2 describe-instances --instance-ids "$1" --query 'Reservations[].Instances[].State.Name' --output text &>/dev/null; then
    msg:error "Instance $1 not found or you don't have permission to access it."
  fi
}

check_dependencies() {
  local missing_deps=()

  for cmd in "${DEPENDENCIES[@]}"; do
    if ! command -v "$cmd" &>/dev/null; then
      missing_deps+=("$cmd")
    fi
  done

  if [[ ${#missing_deps[@]} -gt 0 ]]; then
    echo "Error: Missing required dependencies:" >&2
    printf "  - %s\n" "${missing_deps[@]}" >&2
    exit 1
  fi

  # Check terminal compatibility
  if [[ -n "${KITTY_PID:-}" ]] || [[ -n "${GHOSTTY_BIN_DIR:-}" ]] || [[ "${TERM_PROGRAM}" == "WarpTerminal" ]]; then
    if ! command -v kitty &>/dev/null; then
      msg:error "Kitty terminal not found. Please install it."
      exit 1
    fi
    IMGCMD="kitty +kitten icat --align left --clear"
  elif [[ -n "${ITERM_SESSION_ID:-}" ]]; then
    if command -v imgcat &>/dev/null; then
      if ! imgcat --help 2>&1 | grep -q "iTerm2"; then
        msg:error "iTerm2's imgcat utility not found. Please install the correct version.
More Info: https://iterm2.com/documentation-images.html"
      fi
      IMGCMD="imgcat -W 60%"
    else
      msg:error "iTerm2's imgcat utility not found. Please install it.
More Info: https://iterm2.com/documentation-images.html"
    fi
  elif [[ -n "${WEZTERM_EXECUTABLE:-}" ]]; then
    IMGCMD="wezterm imgcat"
  else
    msg:error "Unsupported terminal. Please use Warp, Ghostty, iTerm2, kitty, or wezterm."
  fi
}

cleanup() {
  clear
  tput rmcup
  exit 0
}

spinner() {
  local pid=$1
  local spinstr=$SPINNER
  local MESSAGE="Pulling new image..."

  while kill -0 $pid 2>/dev/null; do
    local temp=${spinstr#?}
    printf "\r %c %s" "$spinstr" "$MESSAGE"
    spinstr=$temp${spinstr%"$temp"}
    sleep $DELAY
  done
  printf "\r%*s\r" $((${#MESSAGE} + 4)) ""
}

display_image() {
  if [[ ! -f $SCREENSHOT ]]; then
    msg:error "Screenshot file not found: $SCREENSHOT"
  fi

  if [[ -n $IMGCMD ]]; then
    $IMGCMD "$SCREENSHOT"
  else
    msg:error "Image display command not set"
  fi
}

display_header() {
  local name="$1"
  if command -v figurine &>/dev/null; then
    figurine -f "Calvin S.flf" "$name"
  else
    echo "========================================"
    echo "  $name"
    echo "========================================"
  fi
}

countdown_timer() {
  local countdown=$1
  local message="Next update in %d seconds..."
  while ((countdown > 0)); do
    printf "\r$message" "$countdown"
    sleep 1
    ((countdown--))
  done
  printf "\r%*s\r" $((${#message} + 5)) ""
}

get_screenshot() {
  if ! aws ec2 get-console-screenshot \
    --instance-id "$INSTANCE" \
    --query "ImageData" \
    --output text 2>/dev/null | base64 --decode >"$SCREENSHOT"; then
    msg:error "Failed to get console screenshot for instance $INSTANCE"
  fi
}

get_instance_status() {
  local status_output
  status_output=$(aws ec2 describe-instance-status --instance-ids "$INSTANCE" \
    --query 'InstanceStatuses[0].[InstanceState.Name, InstanceStatus.Status, SystemStatus.Status]' \
    --output text 2>/dev/null)
  
  if [[ -z "$status_output" || "$status_output" == "None"* ]]; then
    local state
    state=$(aws ec2 describe-instances --instance-ids "$INSTANCE" \
      --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null)
    echo "${state:-unknown}	pending	pending"
  else
    echo "$status_output"
  fi
}

get_instance_name() {
  aws ec2 describe-instances --instance-ids "$INSTANCE" \
    --query 'Reservations[0].Instances[0].Tags[?Key==`Name`].Value | [0]' \
    --output text 2>/dev/null || echo ""
}

send_notification() {
  local title="$1"
  local message="$2"
  
  if [[ "$(uname)" == "Darwin" ]]; then
    osascript -e "display notification \"$message\" with title \"$title\" sound name \"Glass\"" 2>/dev/null || true
  elif command -v notify-send &>/dev/null; then
    notify-send "$title" "$message" 2>/dev/null || true
  fi
}

check_and_notify_ready() {
  local state="$1"
  local instance_status="$2"
  local system_status="$3"
  
  if [[ "$state" == "running" && "$instance_status" == "ok" && "$system_status" == "ok" ]]; then
    if [[ "$NOTIFIED" == false ]]; then
      local name_display="${INSTANCE_NAME:-$INSTANCE}"
      send_notification "AWS Instance Ready" "$name_display is ready to connect"
      NOTIFIED=true
    fi
    return 0
  else
    NOTIFIED=false
    return 1
  fi
}

format_status_line() {
  local state="$1"
  local instance_status="$2"
  local system_status="$3"
  
  local state_color instance_color system_color reset
  reset="\033[0m"
  
  case "$state" in
    running) state_color="\033[32m" ;;  # green
    stopping|shutting-down) state_color="\033[33m" ;;  # yellow
    stopped|terminated) state_color="\033[31m" ;;  # red
    pending) state_color="\033[36m" ;;  # cyan
    *) state_color="" ;;
  esac
  
  case "$instance_status" in
    ok) instance_color="\033[32m" ;;
    initializing) instance_color="\033[33m" ;;
    *) instance_color="\033[31m" ;;
  esac
  
  case "$system_status" in
    ok) system_color="\033[32m" ;;
    initializing) system_color="\033[33m" ;;
    *) system_color="\033[31m" ;;
  esac
  
  printf "State: ${state_color}%s${reset}  |  Instance: ${instance_color}%s${reset}  |  System: ${system_color}%s${reset}" \
    "$state" "$instance_status" "$system_status"
}

show_usage() {
  cat <<EOF
Usage: $(basename "$0") <instance-id>

Monitor AWS EC2 instance console screenshots in real-time.
Displays instance state and status checks, with desktop notification
when the instance is ready to connect.

Arguments:
    instance-id    EC2 instance ID (must start with i-)
                   If omitted, launches interactive fzf selector

Environment variables:
    XDG_CACHE_HOME    Cache directory (default: ~/.cache)
    
Requirements:
    - aws-cli
    - Compatible terminal (Ghostty, iTerm2, kitty, or wezterm)
    - fzf (optional, for interactive instance selection)
    - figurine (optional, for ASCII art header)

Features:
    - Real-time console screenshot display
    - Instance state and status check monitoring
    - Desktop notification when instance is ready (macOS/Linux)
    - Color-coded status indicators

Example:
    $(basename "$0") i-1234567890abcdef0
    $(basename "$0")  # Interactive selection
EOF
  exit 1
}

# Main Script
main() {
  # If help flag, show usage
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    show_usage
  fi

  # If no argument, launch fzf selection
  if [[ $# -eq 0 ]]; then
    check_dependencies
    if ! command -v fzf &>/dev/null; then
      msg:error "fzf is required for interactive instance selection. Please install fzf."
    fi
    msg:info "Fetching EC2 instances..."
  INSTANCE_LINE=$(aws ec2 describe-instances --filters Name=instance-state-name,Values=running --query 'Reservations[].Instances[].[InstanceId, Tags[?Key==`Name`].Value | [0]]' --output text | awk '{printf "%s\t%s\n", $1, ($2 ? $2 : "<NoName>")}' | fzf --prompt="Select EC2 instance: " --header="INSTANCE-ID\tNAME")
    if [[ -z "$INSTANCE_LINE" ]]; then
      msg:error "No instance selected. Exiting."
    fi
    INSTANCE=$(echo "$INSTANCE_LINE" | awk '{print $1}')
    msg:info "Selected instance: $INSTANCE"
  else
    INSTANCE=$1
    check_instance_id "$INSTANCE"
    check_dependencies
  fi

  SCREENSHOT="$CACHE_DIR/ssm-connect-screenshot-$INSTANCE.jpg"
  verify_aws_instance "$INSTANCE"
  INSTANCE_NAME=$(get_instance_name)

  mkdir -p "$CACHE_DIR"

  # Set up traps for cleanup
  trap cleanup INT TERM
  trap 'tput rmcup' EXIT

  tput smcup

  while true; do
    get_screenshot &
    spinner $!
    wait $!

    local status_info state instance_status system_status
    status_info=$(get_instance_status)
    read -r state instance_status system_status <<< "$status_info"

    clear
    display_header "$(basename "$0")"
    display_image

    echo "--------------------------------------------------"
    if [[ -n "$INSTANCE_NAME" && "$INSTANCE_NAME" != "None" ]]; then
      echo "Instance: $INSTANCE_NAME ($INSTANCE)"
    else
      echo "Instance: $INSTANCE"
    fi
    echo -e "$(format_status_line "$state" "$instance_status" "$system_status")"
    
    if check_and_notify_ready "$state" "$instance_status" "$system_status"; then
      echo -e "\033[32m✓ Ready to connect\033[0m"
    else
      echo -e "\033[33m⏳ Waiting for instance to be ready...\033[0m"
    fi
    echo "--------------------------------------------------"
    echo "Press Ctrl+C to exit..."
    echo "--------------------------------------------------"
    countdown_timer $SLEEP_TIME
  done
  \rm "$SCREENSHOT"
}

main "$@"
