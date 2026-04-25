# AI Helpers

Provides AI-related shell aliases, widgets, and keybindings for interacting with AI tools directly from the command line.

These helpers are loaded automatically via the toolbox's `shell/init.sh`.

## Shell Helpers (`shell/modules/ai.sh`)

These functions are available in both `bash` and `zsh` environments.

### `claude.monitor`
Runs `claude-monitor` via `uv tool`. 
*   **Prerequisites**: Requires `claude` and `uv` to be installed and available in `$PATH`.
*   **Usage**: Run `claude.monitor [args...]` to start monitoring Claude usage.

---

## ZSH Integration (`shell/modules/ai.zsh`)

These enhancements are available exclusively for interactive `zsh` users, providing quick keyboard shortcuts for AI generation explicitly within the shell line editor (ZLE).

> **⚠️ WARNING**: **One-liner** paths (`-e`): the widget runs `aichat -S -e` and replaces the buffer with the suggested command (press Enter yourself). **`#ex` / `#rv` / `#er` / `#ask`**: the widget only **composes** `aichat -S -r '<role>' '<payload>'` — it does **not** call `aichat` inside the helper. **zsh** puts that line in `BUFFER` and uses **`zle .accept-line`** so the shell runs it like a normal submitted line. **bash** cannot do that from `bind -x`, so it **`eval`**s the same composed line (equivalent effect).

### Keybindings (ZLE Widgets)

#### `Alt-E` (`^[e`): `aichat` dispatcher (zsh)

Takes the current line, shows `⌛` while waiting. **One-liners:** `toolbox_aichat_widget_run` invokes `aichat -S -e` and prints the model’s one-liner into the buffer. **Modes (`#ex`, …):** the helper prints `__TOOLBOX_AICHAT_SUBMIT__` plus a single-line `aichat -S -r '<role>' '<payload>'` (payload newlines flattened to spaces; embedded `'` escaped as `'\''`). The widget strips the marker, sets **`BUFFER`** to the `aichat` line, and runs **`zle .accept-line`** — **no** `aichat` subprocess inside the helper for modes.

*   **Prerequisites**: Requires the `aichat` CLI. Optional custom roles live under `contrib/aichat-roles/`; run `contrib/aichat-roles/install-roles.sh` (symlinks by default) or see that README if you use `#rv`, `#er`, or `#ask`.

**One-liner (natural language → shell command)**

| Line shape | `aichat` invocation |
|------------|-------------------|
| Does not start with `#` | `aichat -S -e` + whole line |
| Starts with `#` then **space or tab** (shell-comment style) | `aichat -S -e` + text after `#` and leading whitespace |

**Modes** (line starts with `#` but **not** `#` + space/tab — i.e. `#keyword…`)

After the keyword, add **space + prompt** or end after keyword is not allowed (empty payload errors).

| Prefix | Role | Notes |
|--------|------|--------|
| `#explain` … | `%explain-shell%` | Explain shell; long form matched before `#ex`. |
| `#ex` … | `%explain-shell%` | Short form; use a boundary so `#example` is not treated as `#ex`. |
| `#review` … | `review` | Custom role — install from `contrib/aichat-roles/review.md`. |
| `#rv` … | `review` | Short form. |
| `#er` … | `explain-review` | Explain + review — install from `contrib/aichat-roles/explain-review.md`. |
| `#ask` … | `ask` | General CLI/shell Q&A — install from `contrib/aichat-roles/ask.md`. |

Modes: the helper prints `__TOOLBOX_AICHAT_SUBMIT__` plus the composed `aichat` line (see above). **zsh:** strip marker → `BUFFER` → `.accept-line`. **bash:** strip marker → `eval` (readline cannot submit programmatically).

Unknown `#foo` (not in the table and not `#` + whitespace) produces a short `# aichat: …` error line in the buffer.

*   **Usage (one-liner)**:
    1. Type a natural language prompt (e.g. `list files sorted by size`) or `# list files sorted by size` (comment-safe on Enter).
    2. Press **`Alt-E`**.
    3. The buffer becomes the suggested command; edit if needed, then Enter to run.

*   **Usage (modes, e.g. `#ex …`)**:
    1. Type `#ex` (or `#rv`, …) and your prompt; press **`Alt-E`**.
    2. **zsh:** the line becomes `aichat -S -r '…' '…'` and is submitted like Enter; **bash:** the same command runs via `eval`. Read the reply in the scrollback.

#### Bash (`shell/modules/ai.bash`)

Same dispatch via `toolbox_aichat_widget_run` in `ai.sh`; **Alt-e** (`\ee` bind). Modes: `eval` on the composed line (no `⌛` refresh in bash readline).
