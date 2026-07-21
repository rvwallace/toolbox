# tssh

`tssh` opens SSH connections as windows in one dedicated local tmux session
named `tssh`. OpenSSH remains responsible for configuration, authentication,
proxies, keys, and remote commands.

```bash
tssh user@host
tssh -p 2222 user@host
tssh server-alias sudo systemctl status nginx
tssh --name prod-db -- server-alias
```

## Window and pane behavior

Each invocation creates a managed window and switches or attaches to it. The
window name is derived through `ssh -G`, so SSH options and trailing remote
commands do not get mistaken for the destination. Use `--name` to override the
name.

Within a managed window:

- A new pane reconnects to the same SSH target.
- A manually created window opens a local shell.
- Running `tssh` again from that local window creates another managed SSH
  window without changing tmux sessions.

When SSH exits normally, its managed window closes. When SSH fails, the window
shows the exit status and waits for a keypress so the error remains visible.

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

Both macOS and Linux toolbox dependency lists already include tmux.
