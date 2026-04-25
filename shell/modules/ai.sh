#!/usr/bin/env bash
# AI-related aliases and shared helpers (sourced by bash and zsh).

# claude-monitor via uv tool
if command -v claude &>/dev/null && command -v uv &>/dev/null; then
	claude.monitor() {
		uv tool run claude-monitor "$@"
	}
fi

# Strip one leading '#' from $1, then trim leading whitespace from the result.
# Prints the trimmed string (may be empty).
_toolbox_aichat_strip_hash_leading_ws() {
	local rest="${1#\#}"
	rest="${rest#"${rest%%[![:space:]]*}"}"
	printf '%s' "$rest"
}

# Single-quote $1 for safe embedding in a shell command (readable; handles embedded ').
_toolbox_shell_sq() {
	local s="$1"
	printf "'"
	while [[ "$s" == *\'* ]]; do
		printf '%s' "${s%%\'*}"
		printf '%s' $'\'\\\'\''
		s="${s#*\'}"
	done
	printf '%s' "$s"
	printf "'"
}

# Run aichat for the Alt+e / Readline widget: one line in, replacement text on stdout.
# One-liner (no leading #, or # then space/tab): run aichat -S -e; print model output (suggested shell command).
# Modes (#ex / #rv / #er / #ask / …): print one line
#   __TOOLBOX_AICHAT_SUBMIT__ aichat -S -r '<role>' '<payload>'
# (single-quoted role and payload; newlines in payload flattened to spaces for one-line submit).
# zsh: widget puts the line in BUFFER and runs zle .accept-line (shell runs aichat). bash: no accept-line from bind -x — widget evals the same line.
# Uses -S (--no-stream) for -e capture into the buffer.
toolbox_aichat_widget_run() {
	local line="$1"
	local payload="" role="" err=""
	local _tb_tab=$'\t'

	if ! command -v aichat &>/dev/null; then
		printf '%s' "# aichat: command not found in PATH"
		return 1
	fi

	if [[ -z "$line" ]]; then
		return 0
	fi

	# One-liner: no # at BOL
	if [[ "$line" != \#* ]]; then
		err=$(aichat -S -e "$line" 2>&1) || {
			printf '%s' "# aichat: ${err//$'\n'/ }"
			return 1
		}
		printf '%s' "$err"
		return 0
	fi

	# Line starts with #
	if [[ "$line" == "#" ]]; then
		printf '%s' "# aichat: use '# text' for a command, or #ex / #rv / #er / #ask + prompt"
		return 1
	fi

	# One-liner: # then space or tab (# shell comment, NL -> command)
	if [[ "$line" == \#\ * || "$line" == \#"${_tb_tab}"* ]]; then
		payload="$(_toolbox_aichat_strip_hash_leading_ws "$line")"
		if [[ -z "$payload" ]]; then
			printf '%s' "# aichat: empty prompt after '#'"
			return 1
		fi
		err=$(aichat -S -e "$payload" 2>&1) || {
			printf '%s' "# aichat: ${err//$'\n'/ }"
			return 1
		}
		printf '%s' "$err"
		return 0
	fi

	# Mode: #<keyword> with boundary (space, tab, or end of line after keyword)
	local suffix="${line#\#}"
	if [[ "$suffix" == explain\ * || "$suffix" == explain ]]; then
		role="%explain-shell%"
		payload="${suffix#explain}"
	elif [[ "$suffix" == ex\ * || "$suffix" == ex ]]; then
		role="%explain-shell%"
		payload="${suffix#ex}"
	elif [[ "$suffix" == review\ * || "$suffix" == review ]]; then
		role="review"
		payload="${suffix#review}"
	elif [[ "$suffix" == rv\ * || "$suffix" == rv ]]; then
		role="review"
		payload="${suffix#rv}"
	elif [[ "$suffix" == er\ * || "$suffix" == er ]]; then
		role="explain-review"
		payload="${suffix#er}"
	elif [[ "$suffix" == ask\ * || "$suffix" == ask ]]; then
		role="ask"
		payload="${suffix#ask}"
	else
		printf '%s' "# aichat: unknown '#…' prefix (try #ex, #rv, #er, #ask, or '# ' for a one-liner)"
		return 1
	fi

	payload="${payload#"${payload%%[![:space:]]*}"}"
	if [[ -z "$payload" ]]; then
		printf '%s' "# aichat: add text after the mode keyword"
		return 1
	fi

	payload="${payload//$'\r'/}"
	payload="${payload//$'\n'/ }"

	printf '__TOOLBOX_AICHAT_SUBMIT__ aichat -S -r %s %s' "$(_toolbox_shell_sq "$role")" "$(_toolbox_shell_sq "$payload")"
	printf '\n'
	return 0
}
