#!/usr/bin/env bash

#==============================================================================
# Homebrew Interactive Package Manager with fzf
#==============================================================================
# Description: Interactive Homebrew package search, install, uninstall, and
#              homepage browsing using fzf. Results are cached for 24 hours
#              (~/.cache/silentcastle/brew-search.cache) for fast startup.
# Author: Robert Wallace
# Dependencies: brew, fzf, jq, open (macOS) or xdg-open (Linux)
# Usage: ./brew.sh [initial_search_query]
#        ./brew.sh --url <package_name>
#        ./brew.sh --refresh   # force cache refresh
#==============================================================================

#==============================================================================
# EARLY BASH VERSION CHECK (MUST BE FIRST)
# Uses $BASH_VERSINFO — a built-in array, no subprocesses needed.
#==============================================================================

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
	echo "╔══════════════════════════════════════════════════════════════════════════════╗" >&2
	echo "║                            BASH VERSION ERROR                                ║" >&2
	echo "╚══════════════════════════════════════════════════════════════════════════════╝" >&2
	echo "" >&2
	echo "Current bash version: ${BASH_VERSION}" >&2
	echo "Required bash version: 4.0+" >&2
	echo "" >&2
	echo "This script uses modern bash features that require bash 4.0 or higher:" >&2
	echo "  • Arrays and associative arrays" >&2
	echo "  • Advanced parameter expansion" >&2
	echo "  • Modern string manipulation" >&2
	echo "" >&2
	case "${OSTYPE:-$(uname -s)}" in
	darwin* | Darwin)
		echo "macOS UPGRADE INSTRUCTIONS:" >&2
		echo "  1. Install modern bash: brew install bash" >&2
		echo "  2. Add to allowed shells: echo \"\$(brew --prefix)/bin/bash\" | sudo tee -a /etc/shells" >&2
		echo "  3. Change default shell: chsh -s \"\$(brew --prefix)/bin/bash\"" >&2
		echo "  4. Restart terminal and verify: bash --version" >&2
		;;
	*)
		echo "LINUX UPGRADE INSTRUCTIONS:" >&2
		echo "  Ubuntu/Debian: sudo apt update && sudo apt upgrade bash" >&2
		echo "  RHEL/CentOS:   sudo yum update bash" >&2
		echo "  Fedora:        sudo dnf update bash" >&2
		echo "  Arch Linux:    sudo pacman -Syu bash" >&2
		;;
	esac
	echo "" >&2
	exit 4
fi

set -euo pipefail # Exit on error, undefined vars, pipe failures
IFS=$'\n\t'       # Secure Internal Field Separator

#==============================================================================
# CONFIGURATION AND CONSTANTS
#==============================================================================

readonly SCRIPT_NAME="${0##*/}"
readonly SCRIPT_PATH="${BASH_SOURCE[0]}"

# Color codes for output formatting
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_FAILURE=1
readonly EXIT_MISSING_DEPS=2
readonly EXIT_INVALID_ARGS=3

# Cache configuration
readonly CACHE_DIR="${HOME}/.cache/silentcastle"
readonly CACHE_FILE="${CACHE_DIR}/brew-search.cache"
readonly CACHE_TTL_SECONDS=86400 # 24 hours

# Required dependencies
readonly REQUIRED_DEPS=("brew" "fzf")
readonly OPTIONAL_DEPS=("jq")

#==============================================================================
# LOGGING FUNCTIONS
#==============================================================================

_log() {
	local level="${1:-INFO}"
	local message="${2:-}"
	case "${level}" in
	ERROR) echo -e "${RED}[ERROR] ${message}${NC}" >&2 ;;
	WARN) echo -e "${YELLOW}[WARN]  ${message}${NC}" >&2 ;;
	INFO) echo -e "${GREEN}[INFO]  ${message}${NC}" >&2 ;;
	DEBUG) [[ "${DEBUG:-0}" == "1" ]] && echo -e "${BLUE}[DEBUG] ${message}${NC}" >&2 ;;
	*) echo -e "[${level}] ${message}" >&2 ;;
	esac
	return 0
}

# Convenience logging functions
_log_error() { _log "ERROR" "${1}"; }
_log_warn() { _log "WARN" "${1}"; }
_log_info() { _log "INFO" "${1}"; }
_log_debug() { _log "DEBUG" "${1}"; }

#==============================================================================
# UTILITY FUNCTIONS
#==============================================================================

# Display usage information
_show_usage() {
	cat <<EOF
Usage: ${SCRIPT_NAME} [OPTIONS] [SEARCH_QUERY]

Interactive Homebrew package manager with fzf integration.
Package list is cached for 24 hours for fast startup.

OPTIONS:
    --url PACKAGE    Open the homepage of the specified package
    --refresh        Force a cache refresh before searching
    --refresh-only   Refresh the cache and exit
    --help, -h       Show this help message
    --version, -v    Show version information

SEARCH_QUERY:
    Optional initial search query for package filtering

EXAMPLES:
    ${SCRIPT_NAME}                    # Start interactive search (uses cache)
    ${SCRIPT_NAME} python             # Start with 'python' pre-filled
    ${SCRIPT_NAME} --refresh          # Refresh cache and search
    ${SCRIPT_NAME} --refresh-only     # Refresh cache and exit
    ${SCRIPT_NAME} --url git          # Open git package homepage

KEYBINDINGS (in fzf interface):
    Ctrl+n           Install selected package
    Ctrl+u           Uninstall selected package
    Ctrl+c           Cancel/exit
    Esc              Cancel/exit
    Tab              Open package homepage
    ?                Toggle preview pane
    Shift+Up/Down    Scroll preview pane
    Enter            Do nothing (prevents accidental actions)

COMPATIBILITY:
    This script requires bash 4.0+ for modern array functionality.

EOF
}

# Display version information
_show_version() {
	echo "${SCRIPT_NAME} v2.0.0 - Enhanced Homebrew Package Manager"
}

# Check if command exists
_command_exists() {
	command -v "${1}" &>/dev/null
}

# Check for required dependencies
_check_dependencies() {
	local missing_deps=()
	local missing_optional=()

	# Check required dependencies
	for dep in "${REQUIRED_DEPS[@]}"; do
		if ! _command_exists "${dep}"; then
			missing_deps+=("${dep}")
		fi
	done

	# Check optional dependencies
	for dep in "${OPTIONAL_DEPS[@]}"; do
		if ! _command_exists "${dep}"; then
			missing_optional+=("${dep}")
		fi
	done

	# Report missing required dependencies
	if [[ ${#missing_deps[@]} -gt 0 ]]; then
		_log_error "Missing required dependencies: ${missing_deps[*]}"
		_log_error "Please install the missing dependencies and try again."
		return ${EXIT_MISSING_DEPS}
	fi

	# Report missing optional dependencies
	if [[ ${#missing_optional[@]} -gt 0 ]]; then
		_log_warn "Missing optional dependencies: ${missing_optional[*]}"
		_log_warn "Some features may not work properly."
	fi

	return ${EXIT_SUCCESS}
}

# Validate input arguments
_validate_args() {
	if [[ $# -gt 2 ]]; then
		_log_error "Too many arguments provided."
		_show_usage
		return ${EXIT_INVALID_ARGS}
	fi

	if [[ "${1:-}" == "--url" && -z "${2:-}" ]]; then
		_log_error "Package name required when using --url option."
		_show_usage
		return ${EXIT_INVALID_ARGS}
	fi

	return ${EXIT_SUCCESS}
}

# Get appropriate open command for the platform
_get_open_command() {
	if _command_exists "open"; then
		echo "open" # macOS
	elif _command_exists "xdg-open"; then
		echo "xdg-open" # Linux
	elif _command_exists "start"; then
		echo "start" # Windows (Git Bash/WSL)
	else
		_log_error "No suitable open command found for this platform"
		return ${EXIT_FAILURE}
	fi
}

# Safely execute command with error handling
_safe_execute() {
	local cmd="${1}"
	local error_msg="${2:-Command execution failed}"

	_log_debug "Executing: ${cmd}"

	if ! eval "${cmd}"; then
		_log_error "${error_msg}"
		return ${EXIT_FAILURE}
	fi

	return ${EXIT_SUCCESS}
}

#==============================================================================
# CORE FUNCTIONS
#==============================================================================

# Check if the cache is valid (exists and is less than TTL seconds old)
_cache_is_valid() {
	[[ -f "${CACHE_FILE}" ]] || return 1
	local now mtime age
	now=$(date +%s)
	# stat -f %m is macOS; stat -c %Y is Linux
	mtime=$(stat -f %m "${CACHE_FILE}" 2>/dev/null || stat -c %Y "${CACHE_FILE}" 2>/dev/null) || return 1
	age=$((now - mtime))
	[[ ${age} -lt ${CACHE_TTL_SECONDS} ]]
}

# Refresh the cache from Homebrew (blocks until done)
_refresh_cache() {
	mkdir -p "${CACHE_DIR}"
	local tmp="${CACHE_FILE}.tmp.$$"
	local err="${CACHE_FILE}.err.$$"
	local refresh_status=0
	local had_warnings=0

	set +e
	brew search --eval-all --desc "" 2>"${err}" | sed -e '/^==>/d' >"${tmp}"
	refresh_status=$?
	set -e

	# Homebrew can emit a non-zero exit status for a broken local formula/cask
	# while still returning a usable package list. Keep the cache fresh if we got data.
	if [[ -s "${tmp}" ]]; then
		mv "${tmp}" "${CACHE_FILE}"
		if [[ ${refresh_status} -ne 0 ]]; then
			had_warnings=1
			_log_warn "Cache refreshed with Homebrew warnings; check brew search --eval-all --desc \"\" for details"
		fi
		_log_debug "Cache refreshed: ${CACHE_FILE}"
		rm -f "${err}"
		return 0
	else
		rm -f "${tmp}"
		rm -f "${err}"
		_log_warn "Cache refresh failed; results may be stale"
		return 1
	fi
}

# Return the package list — from cache when valid, otherwise fetch fresh.
# If cache is stale, shows cached data immediately and refreshes in background.
_get_package_list() {
	local force_refresh="${1:-0}"

	if [[ "${force_refresh}" == "1" ]]; then
		_log_info "Refreshing Homebrew package cache..."
		if ! _refresh_cache; then
			if [[ ! -f "${CACHE_FILE}" ]]; then
				return 1
			fi
		fi
	fi

	if _cache_is_valid; then
		# Serve from cache; trigger a background refresh when older than half TTL
		local now mtime age half_ttl
		now=$(date +%s)
		mtime=$(stat -f %m "${CACHE_FILE}" 2>/dev/null || stat -c %Y "${CACHE_FILE}" 2>/dev/null)
		age=$((now - mtime))
		half_ttl=$((CACHE_TTL_SECONDS / 2))
		if [[ ${age} -gt ${half_ttl} ]]; then
			_log_debug "Cache is aging (${age}s old); refreshing in background"
			(_refresh_cache &>/dev/null &)
		fi
		cat "${CACHE_FILE}"
	else
		_log_info "Building package cache (first run or expired)..."
		if ! _refresh_cache && [[ ! -f "${CACHE_FILE}" ]]; then
			return 1
		fi
		cat "${CACHE_FILE}"
	fi
}

# Interactive fzf-based Homebrew package search and management
brew_fzf_search() {
	local initial_query="${1:-}"
	local force_refresh="${2:-0}"
	local selected
	local shell_cmd

	# Use bash for fzf shell commands to avoid zsh quirks with read -p
	shell_cmd="$(command -v bash 2>/dev/null || command -v sh)"
	if [[ -z "${shell_cmd}" ]]; then
		_log_error "No suitable shell found for fzf execution"
		return ${EXIT_FAILURE}
	fi

	# Define install and uninstall commands with proper error handling
	local install_command="echo '==> Attempt to install {1}. Confirm with y/n: '; read -r key && [[ \$key == [yY] ]] && (brew install {1} && echo 'Installation completed successfully' || echo 'Installation failed') && read -n 1 -r -p 'Press any key to continue...' key"
	local uninstall_command="echo '==> Attempt to uninstall {1}. Confirm with y/n: '; read -r key && [[ \$key == [yY] ]] && (brew uninstall {1} && echo 'Uninstallation completed successfully' || echo 'Uninstallation failed') && read -n 1 -r -p 'Press any key to continue...' key"

	# Execute fzf with comprehensive error handling
	selected=$(SHELL="${shell_cmd}" _get_package_list "${force_refresh}" |
		fzf \
			-d ':' \
			--query="${initial_query}" \
			--with-nth=1,2 \
			--layout=reverse \
			--exact \
			--ansi \
			--prompt="🍺 Search Homebrew packages > " \
			--wrap \
			--wrap-sign='↲' \
			--ignore-case \
			--no-sort \
			--header='📦 Homebrew Package Manager | Ctrl+n: install | Ctrl+u: uninstall | Ctrl+c: cancel | Tab: open URL | Esc: exit' \
			--bind="ctrl-n:execute(${install_command})" \
			--bind="ctrl-u:execute(${uninstall_command})" \
			--bind='ctrl-c:abort' \
			--bind="tab:execute-silent:${SCRIPT_PATH} --url {1}" \
			--preview-window=right:40%:wrap \
			--preview="HOMEBREW_COLOR=1 brew info {1} 2>/dev/null || echo 'Preview not available'" \
			--preview-label=' [ 📋 Package Info | Shift+↑/↓: scroll | ?: toggle preview ] ' \
			--bind='?:toggle-preview' \
			--bind='shift-up:preview-page-up' \
			--bind='shift-down:preview-page-down' \
			--bind="enter:ignore" \
			--no-mouse)

	# Handle fzf exit codes properly
	local exit_code=$?
	case ${exit_code} in
	0)
		# Normal exit (user made selection or pressed escape)
		if [[ -n "${selected}" ]]; then
			_log_debug "Package selected: ${selected}"
		else
			_log_info "Search exited normally (no selection made)"
		fi
		;;
	1)
		# No match found or general error
		_log_info "Search completed with no results or user cancelled"
		;;
	2)
		# Error in fzf execution
		_log_error "fzf encountered an error during execution"
		return ${EXIT_FAILURE}
		;;
	130)
		# User interrupted with Ctrl+C
		_log_info "Search cancelled by user (Ctrl+C)"
		;;
	*)
		# Other unexpected exit codes
		_log_error "fzf search failed with unexpected exit code: ${exit_code}"
		return ${EXIT_FAILURE}
		;;
	esac

	_log_debug "Selected package: ${selected:-none}"
	return ${EXIT_SUCCESS}
}

# Open package homepage in default browser
open_package_url() {
	local package_name="${1}"
	local json_output
	local homepage
	local open_cmd

	if [[ -z "${package_name}" ]]; then
		_log_error "Package name is required"
		return ${EXIT_INVALID_ARGS}
	fi

	_log_info "Opening homepage for package: ${package_name}"

	# Check for required dependencies for URL opening
	if ! _command_exists "jq"; then
		_log_error "jq is required to open package URLs but is not installed"
		_log_error "Please install jq: brew install jq"
		return ${EXIT_MISSING_DEPS}
	fi

	# Get appropriate open command
	if ! open_cmd="$(_get_open_command)"; then
		return ${EXIT_FAILURE}
	fi

	# Get package information
	_log_debug "Fetching package information for: ${package_name}"
	if ! json_output="$(brew info --json=v2 "${package_name}" 2>/dev/null)"; then
		_log_error "Failed to get information for package: ${package_name}"
		return ${EXIT_FAILURE}
	fi

	if [[ -z "${json_output}" ]]; then
		_log_error "No information available for package: ${package_name}"
		return ${EXIT_FAILURE}
	fi

	# Extract homepage URL based on package type (formula or cask)
	if echo "${json_output}" | jq -e '.formulae | length > 0' &>/dev/null; then
		homepage="$(echo "${json_output}" | jq -r '.formulae[0].homepage // empty')"
		_log_debug "Found formula homepage: ${homepage}"
	elif echo "${json_output}" | jq -e '.casks | length > 0' &>/dev/null; then
		homepage="$(echo "${json_output}" | jq -r '.casks[0].homepage // empty')"
		_log_debug "Found cask homepage: ${homepage}"
	else
		_log_error "Package '${package_name}' not found or has no homepage information"
		return ${EXIT_FAILURE}
	fi

	# Validate and open homepage
	if [[ -n "${homepage}" && "${homepage}" != "null" ]]; then
		_log_info "Opening homepage: ${homepage}"
		if ! _safe_execute "${open_cmd} '${homepage}'" "Failed to open homepage"; then
			return ${EXIT_FAILURE}
		fi
	else
		_log_error "No homepage available for package: ${package_name}"
		return ${EXIT_FAILURE}
	fi

	return ${EXIT_SUCCESS}
}

#==============================================================================
# SIGNAL HANDLERS
#==============================================================================

# Cleanup function for graceful exit
_cleanup() {
	_log_debug "Performing cleanup..."
	# Add any cleanup tasks here if needed
}

# Signal handler for graceful shutdown
_signal_handler() {
	local signal="${1}"
	_log_info "Received signal: ${signal}. Exiting gracefully..."
	_cleanup
	exit ${EXIT_SUCCESS}
}

# Set up signal handlers
trap '_signal_handler SIGINT' INT
trap '_signal_handler SIGTERM' TERM
trap '_cleanup' EXIT

#==============================================================================
# MAIN FUNCTION
#==============================================================================

main() {
	# Enable debug mode if DEBUG environment variable is set
	[[ "${DEBUG:-0}" == "1" ]] && _log_debug "Debug mode enabled"

	# Parse command line arguments
	case "${1:-}" in
	--help | -h)
		_show_usage
		exit ${EXIT_SUCCESS}
		;;
	--version | -v)
		_show_version
		exit ${EXIT_SUCCESS}
		;;
	--url)
		if ! _validate_args "$@"; then
			exit ${EXIT_INVALID_ARGS}
		fi
		if ! _check_dependencies; then
			exit ${EXIT_MISSING_DEPS}
		fi
		if ! open_package_url "${2:-}"; then
			exit ${EXIT_FAILURE}
		fi
		exit ${EXIT_SUCCESS}
		;;
	--refresh)
		if ! _check_dependencies; then
			exit ${EXIT_MISSING_DEPS}
		fi
		if ! brew_fzf_search "" "1"; then
			exit ${EXIT_FAILURE}
		fi
		exit ${EXIT_SUCCESS}
		;;
	--refresh-only)
		if ! _check_dependencies; then
			exit ${EXIT_MISSING_DEPS}
		fi
		_log_info "Refreshing Homebrew package cache..."
		if _refresh_cache; then
			exit ${EXIT_SUCCESS}
		fi
		if [[ -f "${CACHE_FILE}" ]]; then
			exit ${EXIT_SUCCESS}
		fi
		exit ${EXIT_FAILURE}
		;;
	-*)
		_log_error "Unknown option: ${1}"
		_show_usage
		exit ${EXIT_INVALID_ARGS}
		;;
	*)
		# Default behavior: start interactive search
		if ! _validate_args "$@"; then
			exit ${EXIT_INVALID_ARGS}
		fi
		if ! _check_dependencies; then
			exit ${EXIT_MISSING_DEPS}
		fi
		if ! brew_fzf_search "${1:-}"; then
			exit ${EXIT_FAILURE}
		fi
		exit ${EXIT_SUCCESS}
		;;
	esac
}

#==============================================================================
# SCRIPT EXECUTION
#==============================================================================

# Only run main if script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	main "$@"
fi
