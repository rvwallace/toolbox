#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

readonly SESSION_NAME="tssh"
readonly STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/tssh"
readonly HISTORY_FILE="${TSSH_HISTORY_FILE:-${STATE_DIR}/recent-hosts}"
if [[ "$HISTORY_FILE" == */* ]]; then
  readonly HISTORY_DIR="${HISTORY_FILE%/*}"
else
  readonly HISTORY_DIR="."
fi
readonly HISTORY_LIMIT="${TSSH_HISTORY_LIMIT:-50}"
readonly TAB=$'\t'

usage() {
  cat <<'EOF'
Usage:
  tssh
  tssh [--label <label>] [--host] [--] [ssh-options] destination
  tssh --window <index>
  tssh --recent <label>
  tssh --split | --split-down
  tssh --edit

Manage interactive SSH connections in the local tmux session named "tssh".
With no arguments, choose an active window or manage recent connections.

Options:
  --label <label>   Label a new connection (--name is an alias)
  --host            Force a new connection instead of label lookup
  --window <index>  Switch to an active tssh window by index
  --recent <label>  Reopen a saved connection by exact label
  --split           Split the current managed tssh window to the right
  --split-down      Split the current managed tssh window downward
  --no-store        Do not add the new connection to recent hosts
  --edit            Edit the recent-hosts file with $VISUAL or $EDITOR
  -h, --help        Show this help

Remote commands are intentionally unsupported; tssh manages interactive SSH
connections. Use ssh directly for one-off remote commands.

Examples:
  tssh
  tssh prod-db
  tssh --host prod-db
  tssh -p 2222 admin@example.com
  tssh --label "Production DB" -- -p 2222 admin@example.com
  tssh --window 3
  tssh --recent "Production DB"
  tssh --split
EOF
}

die() {
  echo "tssh: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

ensure_history_file() {
  mkdir -p "$HISTORY_DIR"
  chmod 700 "$HISTORY_DIR"
  if [[ ! -e "$HISTORY_FILE" ]]; then
    printf '# label<TAB>SSH argument<TAB>SSH argument...\n' >"$HISTORY_FILE"
  fi
  chmod 600 "$HISTORY_FILE"
}

validate_field() {
  local field=$1 description=$2
  [[ "$field" != *$'\t'* && "$field" != *$'\n'* && "$field" != *$'\r'* ]] ||
    die "$description may not contain tabs or newlines"
}

record_recent() {
  local label=$1
  shift
  local input_file output_file arg

  ensure_history_file
  validate_field "$label" "label"
  for arg in "$@"; do
    validate_field "$arg" "SSH argument"
  done

  input_file=$(mktemp "${HISTORY_DIR}/recent-hosts.input.XXXXXX")
  output_file=$(mktemp "${HISTORY_DIR}/recent-hosts.output.XXXXXX")
  trap 'rm -f "${input_file:-}" "${output_file:-}"' RETURN

  {
    printf '%s' "$label"
    for arg in "$@"; do
      printf '\t%s' "$arg"
    done
    printf '\n'
    cat "$HISTORY_FILE"
  } >"$input_file"

  awk -F '\t' -v OFS='\t' -v limit="$HISTORY_LIMIT" '
    BEGIN { print "# label<TAB>SSH argument<TAB>SSH argument..." }
    /^[[:space:]]*#/ || /^[[:space:]]*$/ || NF < 2 { next }
    {
      key = ""
      for (i = 2; i <= NF; i++) key = key SUBSEP $i
      if (!seen[key]++ && kept++ < limit) print
    }
  ' "$input_file" >"$output_file"

  chmod 600 "$output_file"
  mv "$output_file" "$HISTORY_FILE"
  rm -f "$input_file"
  trap - RETURN
}

edit_recent() {
  local editor
  local -a editor_command
  ensure_history_file
  editor=${VISUAL:-${EDITOR:-vi}}
  read -r -a editor_command <<<"$editor"
  ((${#editor_command[@]} > 0)) || die "editor is empty"
  command -v "${editor_command[0]}" >/dev/null 2>&1 || die "editor not found: ${editor_command[0]}"
  "${editor_command[@]}" "$HISTORY_FILE"
}

history_matches() {
  local wanted=$1
  ensure_history_file
  awk -F '\t' -v wanted="$wanted" '
    !/^[[:space:]]*#/ && NF >= 2 && $1 == wanted { print }
  ' "$HISTORY_FILE"
}

load_history_line() {
  local line=$1
  IFS="$TAB" read -r -a HISTORY_FIELDS <<<"$line"
  ((${#HISTORY_FIELDS[@]} >= 2)) || die "invalid recent-host entry"
  HISTORY_LABEL=${HISTORY_FIELDS[0]}
  HISTORY_ARGS=("${HISTORY_FIELDS[@]:1}")
}

active_windows() {
  local format
  tmux has-session -t "$SESSION_NAME" 2>/dev/null || return 0
  format="#{window_index}${TAB}#{window_id}${TAB}#{window_panes}${TAB}#{@tssh_label}${TAB}#{@tssh_cmd}"
  tmux list-windows -t "$SESSION_NAME" -F "$format" 2>/dev/null |
    awk -F '\t' 'NF >= 5 && $4 != "" && $5 != "" { print }'
}

switch_to_window() {
  local index=$1 target
  target="${SESSION_NAME}:${index}"
  tmux display-message -p -t "$target" '#{window_id}' >/dev/null 2>&1 ||
    die "no active tssh window with index $index"

  if [[ -n "${TMUX:-}" ]]; then
    tmux switch-client -t "$target"
  else
    tmux select-window -t "$target"
    exec tmux attach-session -t "$SESSION_NAME"
  fi
}

switch_active_label() {
  local wanted=$1 line count=0 index=""
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    IFS="$TAB" read -r candidate_index _ _ candidate_label _ <<<"$line"
    if [[ "$candidate_label" == "$wanted" ]]; then
      index=$candidate_index
      ((count += 1))
    fi
  done < <(active_windows)

  if ((count == 1)); then
    switch_to_window "$index"
    return 0
  fi
  ((count == 0)) && return 1
  die "multiple active windows use label '$wanted'; use tssh --window <index>"
}

open_recent_label() {
  local wanted=$1 line count=0 selected=""
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    selected=$line
    ((count += 1))
  done < <(history_matches "$wanted")

  ((count > 0)) || die "no recent connection labeled '$wanted'"
  ((count == 1)) || die "multiple recent connections use label '$wanted'; edit recent hosts to make labels unique"
  load_history_line "$selected"
  open_connection "$HISTORY_LABEL" "${HISTORY_ARGS[@]}"
}

resolve_label() {
  local name_override=$1
  shift
  local ssh_config user host

  if [[ -n "$name_override" ]]; then
    printf '%s\n' "$name_override"
    return
  fi

  if ssh_config=$(ssh -G "$@" 2>/dev/null); then
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

validate_interactive_ssh_args() {
  local expect_value=0 destination_seen=0 arg
  for arg in "$@"; do
    if ((expect_value)); then
      expect_value=0
      continue
    fi
    ((destination_seen == 0)) || die "remote commands are unsupported; use ssh directly"
    case "$arg" in
      --)
        ;;
      -[BbCcDEeFIiJLlmOoPpQRSWw])
        expect_value=1
        ;;
      -[BbCcDEeFIiJLlmOoPpQRSWw]?*)
        ;;
      -*)
        ;;
      *)
        destination_seen=1
        ;;
    esac
  done
  ((expect_value == 0)) || die "SSH option requires a value"
  ((destination_seen == 1)) || die "expected one SSH destination and no remote command"
}

open_connection() {
  local label=$1
  shift
  local safe_name target wrapped_cmd
  local -a ssh_args=("$@") cmd_array

  validate_interactive_ssh_args "${ssh_args[@]}"
  validate_field "$label" "label"
  safe_name=$(sed 's/[^[:alnum:]_-]/_/g' <<<"$label")
  [[ -n "$safe_name" ]] || safe_name="remote"

  cmd_array=(
    bash -c
    'ssh "$@"; status=$?; if [ "$status" -ne 0 ]; then echo; echo "[tssh] SSH exited with status $status."; read -n 1 -s -r -p "Press any key to close window..."; fi'
    _
    "${ssh_args[@]}"
  )
  wrapped_cmd=$(printf '%q ' "${cmd_array[@]}")

  if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    target=$(tmux new-session -d -s "$SESSION_NAME" -n "$safe_name" -P -F '#{session_name}:#{window_id}' "$wrapped_cmd")
  else
    target=$(tmux new-window -d -P -F '#{session_name}:#{window_id}' -t "${SESSION_NAME}:" -n "$safe_name" "$wrapped_cmd")
  fi

  tmux set-option -w -t "$target" @tssh_cmd "$wrapped_cmd"
  tmux set-option -w -t "$target" @tssh_label "$label"
  tmux set-option -w -t "$target" @tssh_target "${ssh_args[${#ssh_args[@]}-1]}"
  tmux set-option -t "$SESSION_NAME" default-command "$SESSION_DEFAULT_CMD"

  if [[ "$STORE_CONNECTION" == true ]]; then
    record_recent "$label" "${ssh_args[@]}"
  fi

  if [[ "$(tmux show-option -g -v detach-on-destroy 2>/dev/null || true)" != "off" ]]; then
    tmux set-option -g detach-on-destroy off
  fi

  switch_to_window "${target#*:}"
}

split_current_connection() {
  local direction=$1 session command
  [[ -n "${TMUX:-}" ]] || die "$direction requires a managed window in the tssh session"
  session=$(tmux display-message -p '#S')
  [[ "$session" == "$SESSION_NAME" ]] || die "$direction requires a managed window in the tssh session"
  command=$(tmux show-option -w -v @tssh_cmd 2>/dev/null || true)
  [[ -n "$command" ]] || die "$direction requires a managed window in the tssh session"

  if [[ "$direction" == "--split-down" ]]; then
    tmux split-window -v "$command"
  else
    tmux split-window -h "$command"
  fi
}

recent_menu() {
  local selected
  ensure_history_file
  selected=$(awk -F '\t' '!/^[[:space:]]*#/ && NF >= 2 { print }' "$HISTORY_FILE" |
    fzf --delimiter="$TAB" --with-nth=1.. --height=80% --reverse --border \
      --prompt='Recent SSH connections > ' \
      --header='Enter: reconnect  Esc: back') || return 1
  [[ -n "$selected" ]] || return 1
  load_history_line "$selected"
  open_connection "$HISTORY_LABEL" "${HISTORY_ARGS[@]}"
}

new_connection_prompt() {
  local destination label default_label
  printf 'SSH destination: ' >&2
  IFS= read -r destination
  [[ -n "$destination" ]] || return 0
  validate_field "$destination" "SSH destination"
  default_label=$(resolve_label "" "$destination")
  printf 'Label [%s]: ' "$default_label" >&2
  IFS= read -r label
  label=${label:-$default_label}
  open_connection "$label" "$destination"
}

main_menu() {
  local selected kind value line index panes label
  require_command fzf

  while true; do
    selected=$(
      {
        while IFS= read -r line; do
          [[ -n "$line" ]] || continue
          IFS="$TAB" read -r index _ panes label _ <<<"$line"
          printf 'window\t%s\t● %s:%s\t%s pane%s\n' "$index" "$index" "$label" "$panes" "$([[ "$panes" == 1 ]] && printf '' || printf 's')"
        done < <(active_windows)
        printf 'action\trecent\t↻ Recent connections…\n'
        printf 'action\tnew\t＋ New connection…\n'
        printf 'action\tedit\t✎ Edit recent hosts…\n'
      } | fzf --delimiter="$TAB" --with-nth=3.. --height=80% --reverse --border \
        --prompt='tssh > ' --header='Enter: select  Esc: close'
    ) || return 0

    IFS="$TAB" read -r kind value _ <<<"$selected"
    case "$kind:$value" in
      window:*) switch_to_window "$value"; return ;;
      action:recent) recent_menu && return ;;
      action:new) new_connection_prompt; return ;;
      action:edit) edit_recent ;;
    esac
  done
}

readonly SESSION_DEFAULT_CMD="bash -c 'CMD=\$(tmux show-option -w -v @tssh_cmd 2>/dev/null); if [ -n \"\$CMD\" ]; then eval \"\$CMD\"; else exec \"\${SHELL:-/bin/bash}\"; fi'"

main() {
  local name_override="" force_host=false action="" action_value=""
  local -a ssh_args=()
  STORE_CONNECTION=true

  require_command ssh
  require_command tmux

  while (($#)); do
    case "$1" in
      -h | --help) usage; return 0 ;;
      --label | --name)
        (($# >= 2)) || die "$1 requires a value"
        name_override=$2
        shift 2
        ;;
      --host) force_host=true; shift ;;
      --window | --recent)
        (($# >= 2)) || die "$1 requires a value"
        [[ -z "$action" ]] || die "only one action may be specified"
        action=$1
        action_value=$2
        shift 2
        ;;
      --split | --split-down | --edit)
        [[ -z "$action" ]] || die "only one action may be specified"
        action=$1
        shift
        ;;
      --no-store) STORE_CONNECTION=false; shift ;;
      --) shift; ssh_args+=("$@"); break ;;
      *) ssh_args+=("$1"); shift ;;
    esac
  done

  case "$action" in
    --window) ((${#ssh_args[@]} == 0)) || die "--window does not accept SSH arguments"; switch_to_window "$action_value"; return ;;
    --recent) ((${#ssh_args[@]} == 0)) || die "--recent does not accept SSH arguments"; open_recent_label "$action_value"; return ;;
    --split | --split-down) ((${#ssh_args[@]} == 0)) || die "$action does not accept SSH arguments"; split_current_connection "$action"; return ;;
    --edit) ((${#ssh_args[@]} == 0)) || die "--edit does not accept SSH arguments"; edit_recent; return ;;
  esac

  if ((${#ssh_args[@]} == 0)); then
    [[ -z "$name_override" && "$force_host" == false ]] || die "missing SSH destination"
    main_menu
    return
  fi

  if [[ "$force_host" == false && -z "$name_override" && ${#ssh_args[@]} -eq 1 && ${ssh_args[0]} != -* ]]; then
    switch_active_label "${ssh_args[0]}" && return
    if [[ -n "$(history_matches "${ssh_args[0]}")" ]]; then
      open_recent_label "${ssh_args[0]}"
      return
    fi
  fi

  open_connection "$(resolve_label "$name_override" "${ssh_args[@]}")" "${ssh_args[@]}"
}

main "$@"
