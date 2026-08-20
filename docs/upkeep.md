# upkeep

`upkeep` is an interactive CLI tool and package manager for your developer environment with an `fzf` interface.

It detects and manages packages installed across multiple package managers:
- **Homebrew** (`brew`)
- **uv tool** (`uv tool`)
- **Cargo** (`cargo` and `cargo-update`)
- **Go** (`gup` and `go install`)

Only the package managers currently installed and available in your `$PATH` are queried and managed.

---

## Features

- **Update All (`--all` / `-a`)**: Updates packages across all detected package managers in one step.
- **Interactive Update (`--update` / `-u`)**: Queries package managers for outdated packages and presents a multi-select `fzf` menu to choose which ones to update.
- **Browse and Remove (`--remove` / `-r`)**: Displays all installed packages tagged by ecosystem (`[brew]`, `[uv]`, `[cargo]`, `[go]`), prompts for confirmation, and removes selected packages.
- **Dynamic Detection**: Gracefully handles missing package managers without failing.

---

## Prerequisites

- `fzf` (required for interactive menus)

### Optional Helper Tools

For full outdated detection and updates across Cargo and Go:
- **`cargo-update`**: Required to check and update Cargo packages.
  ```bash
  cargo install cargo-update
  ```
- **`gup`**: Recommended for Go binary checking and updates.
  ```bash
  go install github.com/nao1215/gup@latest
  ```

---

## Usage

### Interactive Mode

Run without arguments to select an action from the mode menu:

```bash
upkeep
```

### Direct Commands

Run with command flags:

```bash
# Update all packages across all detected ecosystems
upkeep --all

# Interactively check for and update outdated packages
upkeep --update

# Browse all installed packages and choose which to uninstall
upkeep --remove

# Show help
upkeep --help
```

---

## Menu Controls

| Key | Action |
| :--- | :--- |
| `TAB` | Select or deselect one or more items |
| `ENTER` | Confirm selection |
| `ESC` / `Ctrl+C` | Cancel operation |
