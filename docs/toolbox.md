# Toolbox manager, bootstrap, and shell

This repo’s **`toolbox`** command is a small **Go** program (`cmd/toolbox`). The repo root **`toolbox`** file is a **bash proxy**: it runs `bin/toolbox`, or builds it with `go` if missing.

## Quick reference

| Action | Command |
|--------|---------|
| Install symlinks + build Go/Swift | `./toolbox install` |
| List `bin/` | `./toolbox list` |
| Remove dead symlinks | `./toolbox clean` |
| New machine setup | `./bootstrap.sh` |
| Reload shell after editing modules | `toolbox_reload` (after sourcing `init.sh`) |

Full CLI help: `./toolbox help`.

## Platform-aware install

`toolbox install` only installs tools that support the current OS.

- Missing platform metadata means `all`
- Python and shell scripts use `# toolbox-platforms: ...`
- Swift scripts use `// toolbox-platforms: ...`
- Go commands can use `cmd/<name>/toolbox.yaml`

Supported values are `all`, `linux`, and `darwin` (`macos` is accepted as an alias for `darwin`).

If a tool is not supported on the current OS, `toolbox install` skips it and removes any stale `bin/` entry for that command.

See `docs/tool-authoring.md` for the standard.

## Prerequisites

| Platform | Required | Notes |
|----------|----------|--------|
| **Any** | **Go** (to build `bin/toolbox` the first time), **uv**, **go** on `PATH` | `go` is both the toolchain and a runtime dependency for scripts that invoke `go build`. |
| **macOS** | **Homebrew** (+ **Homebrew Bundle** for `brew bundle`), **Swift** / **swiftc** | Bootstrap generates a **temporary** `Brewfile` under `/tmp` from `deps/*.yaml` and suggests `brew bundle install --file=…`. |
| **Linux** | **uv**, **go** | No Homebrew. Use your distro packages. **Swift** optional; Swift tools build only when `swiftc` exists. |

## `bootstrap.sh`

- **macOS:** Checks `brew` (including `brew bundle` — run `brew tap Homebrew/bundle` if needed), `uv`, `go`, `swift`, `swiftc`. Builds `bin/toolbox` if needed. For each of **two** batches (`deps/toolbox.yaml` then `deps/tools.yaml` `brew:` lists), writes a **temp** `Brewfile`, prints a sample `brew bundle install --file=…` line, and optionally runs **`brew bundle install`** after **y/N**. Then runs `uv_tool_installs`.
- **Linux:** Checks `uv` and `go`. Builds `bin/toolbox` if needed. Runs **`toolbox bootstrap linux-install`** (see below), then runs `uv_tool_installs`.

### Linux package manager detection

`linux-install` probes for package managers in this order and uses the first one found:

| Package manager | Distro | Install command |
|-----------------|--------|-----------------|
| `paru` | Arch (AUR helper) | `paru -S --needed --noconfirm` |
| `pacman` | Arch | `sudo pacman -S --needed --noconfirm` |
| `apt` | Debian / Ubuntu | `sudo apt install -y` |
| `dnf` | Fedora | `sudo dnf install -y` (after RPM Fusion setup) |

If none of the above are found, or if the install command fails, it falls back to **`linux-print`** which shows copy-paste hints for `apt` and `dnf`.

**Fedora / RPM Fusion:** Before running `dnf install`, bootstrap checks whether `rpmfusion-free-release` is already installed (`rpm -q`). If not, it detects the current Fedora version via `rpm -E %fedora` and installs both the free and nonfree RPM Fusion repos. This is required because `ffmpeg` is not in Fedora's default repositories.

### Arch: paru auto-install

On Linux, before running `linux-install`, bootstrap checks whether `paru` is available. If `pacman` is present but `paru` is not, it installs `paru` from the AUR using `makepkg`:

1. `sudo pacman -S --needed --noconfirm base-devel git`
2. `git clone https://aur.archlinux.org/paru.git` into a temp dir
3. `makepkg -si --noconfirm`

Once installed, `linux-install` will pick up `paru` as the preferred Arch package manager.

### `uv_tool_installs`

Both macOS and Linux bootstrap paths run `uv_tool_installs` after package installs. This creates `~/.local/bin` (required by `uv tool install` if it does not already exist) and installs the following tools via `uv tool install`:

- `rich-cli`

### LazyVim setup

Both macOS and Linux bootstrap paths run `setup_lazyvim` after `uv_tool_installs`, but only if `nvim` is on PATH. If `~/.config/nvim` already exists the user is prompted `[y/N]` before proceeding.

Steps performed:

1. Back up `~/.config/nvim` → `~/.config/nvim.bak` (and `~/.local/share/nvim`, `~/.local/state/nvim`, `~/.cache/nvim` if present).
2. `git clone https://github.com/LazyVim/starter ~/.config/nvim`
3. `rm -rf ~/.config/nvim/.git`

After bootstrap, run `nvim` once to let LazyVim download and install its plugins. Run `:LazyHealth` inside Neovim to verify everything loaded correctly.

## Dependency files (`deps/`)

| File | Purpose |
|------|---------|
| `deps/toolbox.yaml` | Extra packages beyond core prereqs (e.g. `jq`, `fzf`). `brew:` drives **generated** macOS Brewfiles; `apt_packages`, `dnf_packages`, `pacman_packages` for Linux auto-install and paste lines. |
| `deps/tools.yaml` | Optional “usual tools” list (second macOS batch; extra Linux install block). Can be empty. |

Each file supports these keys:

```yaml
brew:           # Homebrew formula names (macOS)
apt_packages:   # Debian / Ubuntu package names
dnf_packages:   # Fedora package names
pacman_packages: # Arch Linux package names (used for both pacman and paru)
```

### Package name verification

Package names differ across distros and must be verified against the actual repos before adding or changing them. When editing `deps/*.yaml`, confirm each name is correct for:

| Key | Verify against |
|-----|---------------|
| `brew` | `brew search <name>` or [formulae.brew.sh](https://formulae.brew.sh) |
| `apt_packages` | Ubuntu 24.04 LTS — `apt-cache show <name>` or [packages.ubuntu.com](https://packages.ubuntu.com) |
| `dnf_packages` | Fedora (current stable) — `dnf info <name>` or [packages.fedoraproject.org](https://packages.fedoraproject.org) |
| `pacman_packages` | Arch (current) — `pacman -Si <name>` or [archlinux.org/packages](https://archlinux.org/packages) |

Common differences to watch for:

- `fd` on Arch and Homebrew vs `fd-find` on apt and dnf
- `bat` binary is `batcat` on older Ubuntu (package name `bat` is correct on 24.04+)
- `ffmpeg` requires RPM Fusion on Fedora (handled automatically by bootstrap); it is in default repos on Ubuntu and Arch
- `yazi` is in Arch official repos and Homebrew but not in Ubuntu apt or Fedora dnf — omit from `apt_packages`/`dnf_packages`; install manually via `sudo snap install yazi --classic` or from the binary releases at github.com/sxyazi/yazi

## Shell config (`shell.yaml`)

Path: `~/.config/silentcastle/toolbox/shell.yaml` (or `$XDG_CONFIG_HOME/silentcastle/toolbox/shell.yaml`).

```yaml
disabled_modules:
  - zmx
```

Disabling stem **`zmx`** skips `shell/modules/zmx.sh`, `shell/modules/zmx.bash` (if present), and `shell/modules/zmx.zsh`.

### Effective disabled set

Stems that are **not** sourced:

1. `disabled_modules` in `shell.yaml`
2. **Union** `TOOLBOX_SHELL_DISABLED` (comma-separated)
3. **Minus** `TOOLBOX_SHELL_ENABLED` (comma-separated; wins over file + disabled env)

`init.sh` runs `bin/toolbox shell effective` and skips matching stems. Treat `effective` as internal plumbing; use `toolbox shell list` for the user-facing view.

Simple version:

- `shell.yaml` sets the default disabled modules
- `TOOLBOX_SHELL_DISABLED` temporarily disables more modules for this shell session
- `TOOLBOX_SHELL_ENABLED` temporarily re-enables modules and wins over both of the above

## `toolboxctl`

Sourced from `shell/init.sh`. Wraps `bin/toolbox` and adds:

| Flag | Meaning |
|------|---------|
| `-r` / `--reload` | After the command, run `toolbox_reload`. |
| `-t` / `--temporary` | With `disable` / `enable`: change **session** env only (`TOOLBOX_SHELL_DISABLED` / `TOOLBOX_SHELL_ENABLED`); **do not** edit `shell.yaml`. |

Examples:

```bash
toolboxctl disable zmx          # persist in shell.yaml
toolboxctl disable zmx -r       # persist + reload shell
toolboxctl disable zmx -t       # session only (export TOOLBOX_SHELL_DISABLED)
toolboxctl enable zmx -t        # session override (TOOLBOX_SHELL_ENABLED)
toolboxctl list                 # same as toolbox shell list
toolboxctl install              # forwards to bin/toolbox install
```

Subcommands `disable`, `enable`, `list`, `path`, and `effective` map to `toolbox shell …`. In practice, `effective` is mostly internal; use `list` unless you specifically want the raw disabled stem list. Anything else is passed through (`install`, `clean`, `deps scan`, …).

### `toolbox shell list` columns

`toolbox shell list` always shows all known module stems.

- `ENABLED` - final yes/no after applying `shell.yaml` plus env overrides
- `DEFAULT` - whether the module is disabled by default in `shell.yaml`
- `OVERRIDE` - whether this shell session changed the default with `TOOLBOX_SHELL_DISABLED` or `TOOLBOX_SHELL_ENABLED`
- `RUNTIME` - what happened when `init.sh` tried to source the module in this shell session
- `WHY` - short reason for `unavailable`, such as `missing:kubectl`, `missing:zmx`, or `outside:tmux`

`RUNTIME` values:

- `disabled` - skipped because the final enabled state is no
- `active` - sourced successfully in the current shell session
- `unavailable` - a top-level module guard bailed out in the current shell session
- `loaded` - not disabled, but no session runtime status was exported; this usually means `init.sh` has not been sourced in the current shell

## Shell module authoring

Toolbox shell modules use a companion-file pattern when a helper needs shell-specific behavior:

- Put cross-shell sourced helpers in `shell/modules/*.sh`
- Put zsh-only widgets, keybindings, and completions in `shell/modules/*.zsh`
- Put bash-only widgets, keybindings, and completions in `shell/modules/*.bash` (**Note**: requires Bash v4+; macOS users should update via `brew install bash`)
- Keep toolbox-owned completions beside the toolbox helper they complete

Examples in this repo:

- `shell/modules/tmux.sh` defines `tp`; `shell/modules/tmux.zsh` adds zsh completion
- `shell/modules/git.sh` defines `git.ignore.add` and git helper functions; `shell/modules/git.zsh` adds zsh completion
- `shell/modules/cmux.sh` defines `cssh` / `csshjc`; `shell/modules/cmux.zsh` adds zsh completion for `cmux` and the wrapper helpers
- `shell/modules/ai.zsh` combines zsh widget behavior and `aichat` completion
- `shell/modules/aws.sh` defines `aws.env`; `shell/modules/aws.bash` and `shell/modules/aws.zsh` provide respective cross-shell autocomplete hooks

This is intentionally different from a separate autoloaded `functions/` and `completions/` tree. For toolbox-owned shell behavior, prefer sourced modules so the helper and its integration live in one place.

## Other `toolbox` commands

- **`toolbox deps scan`** — Advisory: scans `scripts/**/*.sh` for `command -v` / `$(which …)` tokens; use to refresh `deps/toolbox.yaml` manually.
- **`toolbox bootstrap linux-install`** — Detects the package manager, optionally sets up RPM Fusion on Fedora, and runs a batch install from `deps/*.yaml`. Falls back to `linux-print` on failure or unknown distro. Used by `bootstrap.sh` on Linux.
- **`toolbox bootstrap linux-print`** — Print Linux hints with copy-paste `apt` and `dnf` install lines. Fallback used when no supported package manager is found or install fails.
- **`toolbox bootstrap brew-bundle`** — Writes a **temporary** `Brewfile` from `brew:` keys in `deps/*.yaml` and prints a sample **`brew bundle install --file='…'`** command (nothing committed under `deps/`). Flags: **`--only=toolbox`**, **`--only=tools`**, or **`--only=all`** (default `all`); **`--path-only`** prints just the Brewfile path on stdout for scripts. `bootstrap.sh` uses `--only=toolbox` and `--only=tools` in two steps.

## Environment

| Variable | Purpose |
|----------|---------|
| `TOOLBOX_ROOT` | Repo root. Set by the `toolbox` proxy and `bootstrap.sh`. Default: parent of `bin/` when running `bin/toolbox`. |
| `TOOLBOX_SHELL_DISABLED` | Comma-separated stems; extra disables for this session. |
| `TOOLBOX_SHELL_ENABLED` | Comma-separated stems; force load even if disabled in file or env disabled. |

## Implementation notes

- Reloading the interactive shell **must** stay in shell code (`toolbox_reload`); a Go process cannot re-source your `.zshrc`.
- If `bin/toolbox` is missing (fresh clone, before first build), `init.sh` still loads **all** modules; run `./toolbox install` or `./bootstrap.sh` to build the binary so `shell.yaml` is honored.
