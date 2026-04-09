#!/usr/bin/env bash
# shellcheck shell=bash
#
# Toolbox shell initialization
# Source this file from ~/.bashrc or ~/.zshrc:
#   source ~/path/to/toolbox/shell/init.sh

# Prevent double-loading
[[ -n "${TOOLBOX_LOADED:-}" ]] && return 0
TOOLBOX_LOADED=1

# Resolve paths (works in both bash and zsh)
if [[ -n "${BASH_VERSION:-}" ]]; then
	if (( BASH_VERSINFO[0] < 4 )); then
		echo "[Toolbox] WARNING: Bash v4+ is recommended for full feature support." >&2
		if [[ "$(uname)" == "Darwin" ]]; then
			echo "[Toolbox] Suggestion: Update via Homebrew -> brew install bash" >&2
		fi
	fi
	_toolbox_source="${BASH_SOURCE[0]}"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
	# shellcheck disable=SC2296
	_toolbox_source="${(%):-%x}"
else
	_toolbox_source="$0"
fi

TOOLBOX_ROOT="$(cd "$(dirname "$_toolbox_source")/.." && pwd)"
export TOOLBOX_ROOT
unset _toolbox_source

# Add bin/ to PATH (prepend so toolbox commands take priority)
case ":${PATH}:" in
	*":$TOOLBOX_ROOT/bin:"*) ;;
	*) export PATH="$TOOLBOX_ROOT/bin:$PATH" ;;
esac

_toolbox_csv_contains() {
	local needle="$1"
	local haystack="$2"
	case ",${haystack}," in
		*",$needle,"*) return 0 ;;
		*) return 1 ;;
	esac
}

_toolbox_csv_add() {
	local current="$1"
	local item="$2"
	if [[ -z "$item" ]] || _toolbox_csv_contains "$item" "$current"; then
		printf '%s' "$current"
		return 0
	fi
	if [[ -n "$current" ]]; then
		printf '%s,%s' "$current" "$item"
	else
		printf '%s' "$item"
	fi
}

_toolbox_status_remove_active() {
	local stem="$1"
	local current="${TOOLBOX_SHELL_ACTIVE:-}"
	local out="" part rest="$current"
	while [[ -n "$rest" ]]; do
		if [[ "$rest" == *,* ]]; then
			part="${rest%%,*}"
			rest="${rest#*,}"
		else
			part="$rest"
			rest=""
		fi
		[[ -z "$part" || "$part" == "$stem" ]] && continue
		out=$(_toolbox_csv_add "$out" "$part")
	done
	export TOOLBOX_SHELL_ACTIVE="$out"
}

_toolbox_status_set_unavailable() {
	local stem="$1"
	local reason="$2"
	local current="${TOOLBOX_SHELL_UNAVAILABLE:-}"
	local out="" entry key value
	local updated=0
	local rest="$current"

	while [[ -n "$rest" ]]; do
		if [[ "$rest" == *";"* ]]; then
			entry="${rest%%;*}"
			rest="${rest#*;}"
		else
			entry="$rest"
			rest=""
		fi
		[[ -z "$entry" ]] && continue
		key="${entry%%=*}"
		value="${entry#*=}"
		if [[ "$key" == "$stem" ]]; then
			updated=1
		fi
		if [[ -n "$out" ]]; then
			out="${out};${entry}"
		else
			out="${entry}"
		fi
	done

	if [[ $updated -eq 0 ]]; then
		if [[ -n "$out" ]]; then
			out="${out};${stem}=${reason}"
		else
			out="${stem}=${reason}"
		fi
	fi

	_toolbox_status_remove_active "$stem"
	export TOOLBOX_SHELL_UNAVAILABLE="$out"
}

_toolbox_status_clear_unavailable() {
	local stem="$1"
	local current="${TOOLBOX_SHELL_UNAVAILABLE:-}"
	local out="" entry key rest="$current"
	while [[ -n "$rest" ]]; do
		if [[ "$rest" == *";"* ]]; then
			entry="${rest%%;*}"
			rest="${rest#*;}"
		else
			entry="$rest"
			rest=""
		fi
		[[ -z "$entry" ]] && continue
		key="${entry%%=*}"
		[[ "$key" == "$stem" ]] && continue
		if [[ -n "$out" ]]; then
			out="${out};${entry}"
		else
			out="${entry}"
		fi
	done
	export TOOLBOX_SHELL_UNAVAILABLE="$out"
}

toolbox_mark_module_active() {
	local stem="${1:-${_toolbox_current_stem:-}}"
	[[ -z "$stem" ]] && return 0
	_toolbox_status_clear_unavailable "$stem"
	export TOOLBOX_SHELL_ACTIVE="$(_toolbox_csv_add "${TOOLBOX_SHELL_ACTIVE:-}" "$stem")"
}

toolbox_mark_module_unavailable() {
	local stem="${1:-${_toolbox_current_stem:-}}"
	local reason="$2"
	[[ -z "$reason" ]] && reason="unavailable"
	[[ -z "$stem" ]] && return 0
	_toolbox_current_unavailable="$reason"
	_toolbox_status_set_unavailable "$stem" "$reason"
}

toolbox_require_commands() {
	local stem="${1:-${_toolbox_current_stem:-}}"
	shift || true
	local missing="" cmd
	for cmd in "$@"; do
		if ! command -v "$cmd" >/dev/null 2>&1; then
			if [[ -n "$missing" ]]; then
				missing="${missing}+${cmd}"
			else
				missing="${cmd}"
			fi
		fi
	done
	if [[ -n "$missing" ]]; then
		toolbox_mark_module_unavailable "$stem" "missing:${missing}"
		return 1
	fi
	return 0
}

toolbox_require_interactive() {
	local stem="${1:-${_toolbox_current_stem:-}}"
	if [[ -n "${ZSH_VERSION:-}" ]]; then
		[[ -o interactive ]] && return 0
	else
		[[ $- == *i* ]] && return 0
	fi
	toolbox_mark_module_unavailable "$stem" "noninteractive"
	return 1
}

toolbox_require_tmux_session() {
	local stem="${1:-${_toolbox_current_stem:-}}"
	[[ -n "${TMUX:-}" ]] && return 0
	toolbox_mark_module_unavailable "$stem" "outside:tmux"
	return 1
}

export TOOLBOX_SHELL_ACTIVE=""
export TOOLBOX_SHELL_UNAVAILABLE=""

# Effective disabled module stems (see docs/toolbox.md)
_toolbox_eff_file=""
if [[ -x "$TOOLBOX_ROOT/bin/toolbox" ]]; then
	_toolbox_eff_file=$(mktemp "${TMPDIR:-/tmp}/toolbox-eff.XXXXXX" 2>/dev/null || true)
	if [[ -n "$_toolbox_eff_file" ]]; then
		"$TOOLBOX_ROOT/bin/toolbox" shell effective 2>/dev/null >"$_toolbox_eff_file" || true
	fi
fi

_toolbox_stem_disabled() {
	local stem="$1"
	[[ -z "$_toolbox_eff_file" ]] && return 1
	[[ ! -s "$_toolbox_eff_file" ]] && return 1
	grep -Fxq "$stem" "$_toolbox_eff_file" 2>/dev/null
}

# Source shell modules (*.sh for bash+zsh; *.zsh for zsh-only e.g. ZLE)
if [[ -d "$TOOLBOX_ROOT/shell/modules" ]]; then
	for _toolbox_module in "$TOOLBOX_ROOT/shell/modules"/*.sh; do
		[[ -f "$_toolbox_module" ]] || continue
		_tb_stem="${_toolbox_module##*/}"
		_tb_stem="${_tb_stem%.sh}"
		if _toolbox_stem_disabled "$_tb_stem"; then
			continue
		fi
		_toolbox_current_stem="$_tb_stem"
		unset _toolbox_current_unavailable
		# shellcheck source=/dev/null
		. "$_toolbox_module"
		[[ -z "${_toolbox_current_unavailable:-}" ]] && toolbox_mark_module_active "$_tb_stem"
	done
	if [[ -n "${ZSH_VERSION:-}" ]]; then
		for _toolbox_module in "$TOOLBOX_ROOT/shell/modules"/*.zsh; do
			[[ -f "$_toolbox_module" ]] || continue
			_tb_stem="${_toolbox_module##*/}"
			_tb_stem="${_tb_stem%.zsh}"
			if _toolbox_stem_disabled "$_tb_stem"; then
				continue
			fi
			_toolbox_current_stem="$_tb_stem"
			unset _toolbox_current_unavailable
			# shellcheck source=/dev/null
			. "$_toolbox_module"
			[[ -z "${_toolbox_current_unavailable:-}" ]] && toolbox_mark_module_active "$_tb_stem"
		done
		# Update completions
		autoload -Uz compinit
		compinit
	elif [[ -n "${BASH_VERSION:-}" ]]; then
		for _toolbox_module in "$TOOLBOX_ROOT/shell/modules"/*.bash; do
			[[ -f "$_toolbox_module" ]] || continue
			_tb_stem="${_toolbox_module##*/}"
			_tb_stem="${_tb_stem%.bash}"
			if _toolbox_stem_disabled "$_tb_stem"; then
				continue
			fi
			_toolbox_current_stem="$_tb_stem"
			unset _toolbox_current_unavailable
			# shellcheck source=/dev/null
			. "$_toolbox_module"
			[[ -z "${_toolbox_current_unavailable:-}" ]] && toolbox_mark_module_active "$_tb_stem"
		done
	fi
	unset _toolbox_module _tb_stem _toolbox_current_stem _toolbox_current_unavailable

fi

if [[ -n "$_toolbox_eff_file" ]]; then
	rm -f "$_toolbox_eff_file"
	unset _toolbox_eff_file
fi
unset -f _toolbox_stem_disabled
unset -f _toolbox_csv_contains
unset -f _toolbox_csv_add
unset -f _toolbox_status_remove_active
unset -f _toolbox_status_set_unavailable
unset -f _toolbox_status_clear_unavailable
unset -f toolbox_mark_module_active
unset -f toolbox_mark_module_unavailable
unset -f toolbox_require_commands
unset -f toolbox_require_interactive
unset -f toolbox_require_tmux_session

# Reload function for development
toolbox_reload() {
	unset TOOLBOX_LOADED
	# shellcheck source=/dev/null
	. "$TOOLBOX_ROOT/shell/init.sh"
	echo "Toolbox reloaded from $TOOLBOX_ROOT"
}

# shellcheck source=/dev/null
if [[ -f "$TOOLBOX_ROOT/shell/toolboxctl.sh" ]]; then
	# shellcheck source=/dev/null
	. "$TOOLBOX_ROOT/shell/toolboxctl.sh"
fi
