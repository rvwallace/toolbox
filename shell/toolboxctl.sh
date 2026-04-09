# shellcheck shell=bash
# toolboxctl — wrapper for bin/toolbox with -r (reload) and -t (session env).
# Sourced from init.sh after toolbox_reload is defined.

# Comma-separated lists: TOOLBOX_SHELL_DISABLED, TOOLBOX_SHELL_ENABLED

_toolboxctl_csv_contains() {
	local needle="$1"
	local haystack="$2"
	case ",${haystack}," in
		*",$needle,"*) return 0 ;;
		*) return 1 ;;
	esac
}

_toolboxctl_env_disable_add() {
	local d="${TOOLBOX_SHELL_DISABLED:-}"
	local a
	for a in "$@"; do
		[[ -z "$a" ]] && continue
		if _toolboxctl_csv_contains "$a" "$d"; then
			continue
		fi
		if [[ -n "$d" ]]; then
			d="$d,$a"
		else
			d="$a"
		fi
	done
	export TOOLBOX_SHELL_DISABLED="$d"
}

_toolboxctl_env_enable_add() {
	local d="${TOOLBOX_SHELL_ENABLED:-}"
	local a
	for a in "$@"; do
		[[ -z "$a" ]] && continue
		if _toolboxctl_csv_contains "$a" "$d"; then
			continue
		fi
		if [[ -n "$d" ]]; then
			d="$d,$a"
		else
			d="$a"
		fi
	done
	export TOOLBOX_SHELL_ENABLED="$d"
}

toolboxctl() {
	local _reload=0 _tmp=0
	while [[ $# -gt 0 ]]; do
		case "$1" in
			-r|--reload) _reload=1; shift ;;
			-t|--temporary) _tmp=1; shift ;;
			*) break ;;
		esac
	done

	local _bin="$TOOLBOX_ROOT/bin/toolbox"
	if [[ ! -x "$_bin" ]]; then
		echo "toolboxctl: $_bin not found (run ./toolbox install from repo root)" >&2
		return 1
	fi

	if [[ $# -lt 1 ]]; then
		echo "usage: toolboxctl [-r] [-t] <command> ..." >&2
		echo "       shortcuts: disable|enable|list|path|effective → shell subcommands" >&2
		return 1
	fi

	local cmd="$1"
	shift

	case "$cmd" in
		disable|enable|list|path|effective)
			case "$cmd" in
				disable)
					if [[ $_tmp -eq 1 ]]; then
						_toolboxctl_env_disable_add "$@"
					else
						"$_bin" shell disable "$@" || return
					fi
					;;
				enable)
					if [[ $_tmp -eq 1 ]]; then
						_toolboxctl_env_enable_add "$@"
					else
						"$_bin" shell enable "$@" || return
					fi
					;;
				list) "$_bin" shell list "$@" || return ;;
				path) "$_bin" shell path "$@" || return ;;
				effective) "$_bin" shell effective "$@" || return ;;
			esac
			;;
		*)
			"$_bin" "$cmd" "$@" || return
			;;
	esac

	if [[ $_reload -eq 1 ]]; then
		toolbox_reload
	fi
}
