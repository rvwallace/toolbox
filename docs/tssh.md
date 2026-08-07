# tssh

`tssh` manages interactive SSH connections as windows in one dedicated local
tmux session named `tssh`. OpenSSH remains responsible for configuration,
authentication, proxies, and keys.

```bash
tssh
tssh user@host
tssh -p 2222 user@host
tssh --label "Production DB" -- server-alias
tssh --window 3
tssh --recent "Production DB"
tssh --split
```

Remote commands are intentionally unsupported. Use `ssh` directly for one-off
commands that do not need a persistent interactive tmux window.

## Connection menu

Running `tssh` without arguments opens an `fzf` menu. Active managed windows
appear first with their tmux window indexes and pane counts:

```text
● 2:prod-db                  2 panes
● 5:web-01                   1 pane
↻ Recent connections…
＋ New connection…
✎ Edit recent hosts…
```

Selecting an active entry switches to that window. Recent connections open in
a fuzzy-searchable submenu. The editor action opens the history file with
`$VISUAL`, `$EDITOR`, or `vi`, in that order, and reloads the menu afterward.

The new-connection action prompts for a destination and an optional label. Use
the CLI when the connection needs additional SSH options.

## CLI lookup

A single plain argument is resolved in this order:

1. An active tssh window with that exact label.
2. A recent connection with that exact label.
3. A new SSH destination.

Use `--host` to bypass label lookup, `--window INDEX` to select a live window,
or `--recent LABEL` to require a stored connection. Duplicate labels produce an
error instead of choosing an arbitrary entry. `--name` remains an alias for
`--label`.

## Window and pane behavior

Each new connection creates a managed window and switches or attaches to it.
The default label is derived through `ssh -G`; `--label` overrides it.

Within a managed window:

- A normally created pane reconnects to the same SSH target.
- `tssh --split` reconnects in a right-hand split.
- `tssh --split-down` reconnects in a downward split.
- A manually created window opens a local shell.

The split commands require both the `tssh` session and a current window with
managed tssh metadata. They refuse to run from another session or from a local
window inside the tssh session.

When SSH exits normally, its managed window closes. When SSH fails, the window
shows the exit status and waits for a keypress so the error remains visible.

## Recent connections

Recent connections are stored at:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/tssh/recent-hosts
```

The directory is mode `700` and the file is mode `600`. Set
`TSSH_HISTORY_FILE` to override the file or `TSSH_HISTORY_LIMIT` to change the
default limit of 50 entries. Use `--no-store` for a connection that should not
be recorded.

The editable file is tab-separated. The first field is the label and every
remaining field is one exact argument passed to `ssh`:

```text
# label<TAB>SSH argument<TAB>SSH argument...
Production DB	-p	2222	admin@db.example.com
Web Server	web-01
Internal Host	-J	bastion.example.com	ops@internal.example.com
```

Tabs and newlines are not allowed inside fields. Reusing a connection moves it
to the top, keeps its newest label, removes older entries with the same SSH
argument vector, and preserves the remaining recency order.

## tmux configuration

The preferred toolbox tmux configuration sets:

```tmux
set-option -g detach-on-destroy off
```

This lets tmux return to the previously active session when the `tssh` session
is destroyed. For portability, `tssh` checks the live global value after the
tmux server is available and sets it to `off` only when necessary.

## Requirements

- Bash
- OpenSSH `ssh`
- tmux
- `fzf` for the interactive menu

Direct connections and noninteractive management commands do not require
`fzf`.
