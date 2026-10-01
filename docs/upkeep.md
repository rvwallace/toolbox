# upkeep

`upkeep` is an interactive CLI tool and package manager for your developer environment with an `fzf` interface.

It detects and manages packages installed across multiple package managers:
- **Homebrew** (`brew`)
- **DNF** (`dnf`, Fedora)
- **APT** (`apt-get`, Debian and Ubuntu)
- **Pacman** (`pacman`, Arch Linux)
- **uv tool** (`uv tool`)
- **npm** (global packages)
- **Cargo** (`cargo` and `cargo-update`)
- **Go** (`gup` and `go install`)

Only the package managers currently installed and available in your `$PATH` are queried and managed.

---

## Features

- **Update All (`--all` / `-a`)**: Updates packages across all detected package managers in one step.
- **Interactive Update (`--update` / `-u`)**: Queries package managers for outdated packages and presents a multi-select `fzf` menu to choose which ones to update.
- **Browse and Remove (`--remove` / `-r`)**: Displays user-installed packages tagged by ecosystem (`[brew]`, `[dnf]`, `[apt]`, `[pacman]`, `[uv]`, `[npm]`, `[cargo]`, `[go]`), prompts for confirmation, and removes selected packages.
- **Dynamic Detection**: Gracefully handles missing package managers without failing.

System package operations use `sudo` when `upkeep` is not run as root. `--all` runs `dnf upgrade`, `apt-get update` followed by `apt-get upgrade`, or `pacman -Syu` as appropriate.

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
