#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tssh [--name <label>] [--] [ssh-args...]

Open an SSH connection in a window of the local tmux session named "tssh".
New panes in a managed window reconnect to the same target; manually created
windows open a local shell.

Options:
  --name <label>  Override the tmux window name
  -h, --help      Show this help

Examples:
  tssh user@host
  tssh -p 2222 user@host
  tssh --name prod-db -- my-db-alias
  tssh host.example.com sudo systemctl status nginx
EOF
}

die() {
  echo "tssh: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

SESSION_NAME="tssh"
NAME_OVERRIDE=""

while (($#)); do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --name)
      (($# >= 2)) || die "--name requires a value"
      NAME_OVERRIDE="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

(($# > 0)) || die "missing ssh arguments (see tssh --help)"

require_command ssh
require_command tmux

SSH_ARGS=("$@")

resolve_label() {
  local ssh_config user host

  if [[ -n "$NAME_OVERRIDE" ]]; then
    printf '%s\n' "$NAME_OVERRIDE"
    return
  fi

  if ssh_config=$(ssh -G "${SSH_ARGS[@]}" 2>/dev/null); then
    user=$(awk '$1 == "user" { print $2; exit }' <<<"$ssh_config")
    host=$(awk '$1 == "host" { print $2; exit }' <<<"$ssh_config")
    if [[ -n "$host" ]]; then
      if [[ -n "$user" ]]; then
        printf '%s@%s\n' "$user" "$host"
      else
        printf '%s\n' "$host"
      fi
      return
    fi
  fi

  printf 'remote\n'
}

LABEL=$(resolve_label)
SAFE_NAME=$(sed 's/[^[:alnum:]_-]/_/g' <<<"$LABEL")
[[ -n "$SAFE_NAME" ]] || SAFE_NAME="remote"

# Run SSH through Bash so failures remain visible instead of immediately
# destroying the tmux window. A normal logout closes the window as usual.
CMD_ARRAY=(
  bash -c
  'ssh "$@"; status=$?; if [ "$status" -ne 0 ]; then echo; echo "[tssh] SSH exited with status $status."; read -n 1 -s -r -p "Press any key to close window..."; fi'
  _
  "${SSH_ARGS[@]}"
)
WRAPPED_CMD=$(printf '%q ' "${CMD_ARRAY[@]}")

# A split inherits the window option and reconnects to the same target. A new
# window has no @tssh_cmd and intentionally opens a local shell.
SESSION_DEFAULT_CMD="bash -c 'CMD=\$(tmux show-option -w -v @tssh_cmd 2>/dev/null); if [ -n \"\$CMD\" ]; then eval \"\$CMD\"; else exec \"\${SHELL:-/bin/bash}\"; fi'"

if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  TARGET=$(tmux new-session -d -s "$SESSION_NAME" -n "$SAFE_NAME" -P -F "#{session_name}:#{window_id}" "$WRAPPED_CMD")
else
  TARGET=$(tmux new-window -d -P -F "#{session_name}:#{window_id}" -t "$SESSION_NAME:" -n "$SAFE_NAME" "$WRAPPED_CMD")
fi

tmux set-option -w -t "$TARGET" @tssh_cmd "$WRAPPED_CMD"
tmux set-option -t "$SESSION_NAME" default-command "$SESSION_DEFAULT_CMD"

# tmux-conf owns the preferred global default. Keep tssh usable with other
# configurations by correcting the option only when it is not already off.
if [[ "$(tmux show-option -g -v detach-on-destroy 2>/dev/null || true)" != "off" ]]; then
  tmux set-option -g detach-on-destroy off
fi

if [[ -n "${TMUX:-}" ]]; then
  tmux switch-client -t "$TARGET"
else
  exec tmux attach-session -t "$TARGET"
fi
