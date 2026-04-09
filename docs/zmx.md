# zmx Helpers

Provides interactive shell integration (fzf-based) for the `zmx` session manager, along with zsh-specific keybindings and completion handling.

These helpers are loaded automatically via the toolbox's `shell/init.sh`.

## Shell Helpers (`shell/modules/zmx.sh`)

These functions are available in both `bash` and `zsh` environments. They simplify interacting with `zmx` sessions through fuzzy-finding (`fzf`).

### `zmx.select`
Interactive session manager interface. Displays active `zmx` sessions alongside their metadata (pid, client count, directory). Preview window automatically shows the history of the currently highlighted session.

*   **Usage**: Run `zmx.select`
*   **Keybindings**:
    *   `Enter`: Attach to the selected session.
    *   `Ctrl-N`: Create/attach to a new session (names the session after the search query, or defaults to the current directory basename if empty).
    *   `Ctrl-K`: Kill the selected session.
    *   `Ctrl-D`: Detach the selected session.
    *   `Ctrl-E`: Export the selected session's history to a temp file and open it in your `$EDITOR`.

### `zmx.history [session_name]`
Browse session scrollback dynamically inside an `fzf` viewer.

*   **Usage**: Run `zmx.history` to select a session via fuzzy finder, or provide one as an argument: `zmx.history <name>`.
*   **Keybindings**:
    *   `Enter`/`Esc`: Close viewer.
    *   `Ctrl-S`: Export the full session history to a timestamped file in the current working directory.
    *   `Ctrl-E`: Open the full session history in your `$EDITOR`.

### `zmx.kill [session_name]`
Kill a session. If no session name is provided, prompts you to select one interactively via `fzf`.

### `zmx.detach [session_name]`
Detach from the specified session, or the current one if no name is provided.

### `zmx.wait [session_name...]`
Wait for one or more sessions to exit. If no arguments are provided, opens an `fzf` multi-select menu allowing you to pick the sessions to wait for.

---

## ZSH Integration (`shell/modules/zmx.zsh`)

These enhancements are exclusively available for interactive `zsh` users. They provide quick keyboard shortcuts and initialize shell completions cleanly.

### Keybindings (ZLE Widgets)
*   **`Alt-A`** (`^[a`): Automatically attach to a `zmx` session named after the current directory (`basename $PWD`). This allows you to rapidly jump into context-aware sessions.
*   **`Alt-D`** (`^[d`): Faster shortcut to detach from the current `zmx` session.

### Completions Optimization
*   The module ensures `zmx` completions are loaded for your shell.
*   **Async Loading**: It detects if the `zinit` plugin manager is installed. If so, it asynchronously loads completions in the background (`wait"1"`) to prevent blocking or slowing down your initial shell launch.
*   **Fallback**: If `zinit` is not available, it safely falls back to standard synchronous `eval "$(zmx completions zsh)"`.
