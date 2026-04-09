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

> **⚠️ WARNING**: AI-generated commands are inserted into the buffer but **NOT** executed automatically. You must review all commands before pressing `Enter`. AI can occasionally hallucinate dangerous commands. These widgets are conveniences, not guarantees of correctness. Always verify AI output before execution, especially for destructive operations.

### Keybindings (ZLE Widgets)

#### `Alt-E` (`^[e`): Generate Command via `aichat`
Takes your current input buffer, replaces it with a temporary `⌛` to indicate it is working, and requests an AI-generated command from `aichat`.

*   **Prerequisites**: Requires the `aichat` CLI.
*   **Usage**: 
    1. Type a natural language prompt directly into your terminal (e.g., `list files sorted by size`).
    2. Press **`Alt-E`**.
    3. Wait a moment while `aichat` processes the prompt.
    4. The buffer is replaced with the generated command. Review the command, then press `Enter` to run it.
