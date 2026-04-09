#!/usr/bin/env bash

# This script was automatically generated on Sat Jul  6 01:40:44 CDT 2024

# ==========================================================================
#  Ollama Update Script
# ==========================================================================
#
# Description:
#   This script updates all models in the ollama repository.
#
# Usage:
#   ./ollama-update.sh
#
# Dependencies:
#   - ollama
#
# Author: Robert Wallace
# ==========================================================================
# ---> Including msg.sh

RED='\033[0;31m'
NC='\033[0m' # No Color
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'

BFR=$'\r\033[K' # Carriage return and erase line
HOLD="[-]"
CROSS="[✘]"
TICK="[✔]"

declare -A LOG_LEVELS=([DEBUG]=0 [INFO]=1 [WARN]=2 [ERROR]=3)
DEFAULT_LOG_LEVEL=${LOG_LEVEL:-"ERROR"}

set_log_level() {
    local level_name="$1"
    if [[ -v "LOG_LEVELS[$level_name]" ]]; then
        CURRENT_LOG_LEVEL=${LOG_LEVELS[$level_name]}
        # echo "Log level set to $level_name"
    else
        echo "Invalid log level: $level_name. Using default (INFO)." >&2
        CURRENT_LOG_LEVEL=${LOG_LEVELS[INFO]}
    fi
}

if [[ -n "${SC_LOG_LEVEL:-}" ]]; then
    set_log_level "$SC_LOG_LEVEL"
else
    # If not set in environment, use the default or what's set in the script
    set_log_level "${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}"
fi

function log() {
    local level=$1
    shift
    if [[ ${LOG_LEVELS[$level]} -ge $CURRENT_LOG_LEVEL ]]; then

        if [[ "$level" == "ERROR" ]]; then
            msg:error "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] $*" >&2

        elif [[ "$level" == "WARN" ]]; then
            msg:warn "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] $*" >&2

        elif [[ "$level" == "INFO" ]]; then
            msg:info "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] $*" >&2

        elif [[ "$level" == "DEBUG" ]]; then
            msg:debug "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] $*" >&2

        else
            msg:info "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] $*" >&2
        fi
    fi
}

_msg() { printf "%b%s%b\n" "$2" "$1" "${NC}" >&2; }
msg() { _msg "$1" "${NC}"; }
msg:info() { _msg "$1" "${BLUE}"; }
msg:warn() { _msg "$1" "${YELLOW}"; }
msg:error() { _msg "$1" "${RED}"; }
msg:success() { _msg "$1" "${GREEN}"; }
msg:debug() { if $DEBUG; then _msg "$1" "${CYAN}"; fi; }

function status:info() { printf ' %b%s %s%b' "$YELLOW" "$HOLD" "$1" "$NC"; }
function status:update() { printf "${BFR} %b%s %s%b" "$YELLOW" "$HOLD" "$1" "$NC"; }
function status:success() { printf "${BFR} %b%s %s%b\n" "$GREEN" "$TICK" "$1" "$NC"; }
function status:error() { printf "${BFR} %b%s %s%b\n" "$RED" "$CROSS" "$1" "$NC"; }

function msg:confirm() {
    local message="$1"
    local reply

    read -q "reply?${BLUE}${message} [y/N]${NC} "
    echo # Add a newline for visual clarity

    [[ "$reply" =~ ^[Yy]$ ]]
}

echo_repeat() {
    local str="$1"
    local n="$2"
    for i in $(seq 1 $n); do
        echo -n "$str"
    done
    echo
}

# <--- End of msg.sh
# ---> Including bash-verify-version.sh

bash_verify_version() {
    local required_version

    # Require version 4.0 by default
    required_version="${1:-4.0}"

    # Get the current bassh version
    # Check if BASH_VERSION is set
    local current_version
    if [[ -n "${BASH_VERSION}" ]]; then
        current_version="${BASH_VERSION}"
    else
        # If BASH_VERSION is not set, use the following command to get the version
        current_version="$(bash --version | head -n 1 | awk '{print $4}')"
    fi

    # Convert version strings to numbers for comparison
    local required_version_num current_version_num
    required_version_num=$(echo "${required_version}" | awk -F. '{ print ($1 * 10000) + ($2 * 100) + $3 }')
    current_version_num=$(echo "${current_version}" | awk -F. '{ print ($1 * 10000) + ($2 * 100) + $3 }')

    # compare the version numbers
    if ((current_version_num < required_version_num)); then
        # echo "Error: Bash version ${required_version} or later is required"
        # echo "       Current version is ${current_version}"
        return 1
    fi

    return 0

}
# <--- End of bash-verify-version.sh
if ! bash_verify_version 4.0; then
    msg:error "Error: Bash version 4.0 or later is required"
    exit 1
fi
# ---> Including check-dependencies.sh
function check_dependencies() {
    local deps=("$@") # Accept all arguments as an array
    local missing_deps=()

    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &>/dev/null; then
            missing_deps+=("$dep")
        fi
    done

    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo "The following dependencies are required but not installed: ${missing_deps[*]}"
        return 1
    fi
    return 0
}
# <--- End of check-dependencies.sh
check_dependencies "ollama"

################################################################################
# Main Function
#
# Update all models in the ollama repository
#
# Arguments:
#   None
#
main() {
    # Get list of models from ollama
    models=(
        $(ollama list | awk '{print $1}' | tail -n +2)
    )

    # Update each model
    for model in "${models[@]}"; do
        printf "\033[s" # Save cursor position
        msg:info "==> Pulling $model"
        output=$(ollama pull ${model} 2>&1 | tee /dev/tty)
        sleep 1
        printf "\033[u"  # Restore cursor position
        printf "\033[1B" # Move cursor down one line
        printf "\033[J"  # Clear the line from the cursor to the end of the screen
        printf "\033[1A" # Move cursor up one line
        if [ $? -eq 0 ]; then
            status:success "Updated $model"
        else
            status:error "Failed Updating $model"
            echo "$output" | sed 's/^/> /'
        fi
        # echo ""
    done
}

# Run the main function
main
