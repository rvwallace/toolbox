# Toolbox

Personal command-line tools in one repo: shell scripts, Python CLIs (PEP 723 + `uv`), optional Go and Swift builds, and shell modules. One `./toolbox install` wires commands into `bin/`.

## Quick start

```bash
cd ~/toolbox
./toolbox install

# Shell (add to ~/.zshrc or ~/.bashrc)
source ~/toolbox/shell/init.sh

aws-ec2 list
cert-check example.com
netinfo
```

## Features

- **Unified CLI** - Same command names no matter whether the implementation is Python, shell, Go, or Swift
- **Python** - `uv run --script` with inline dependencies (PEP 723), no shared venv
- **Swift / Go** - Built by `toolbox install` when those sources exist
- **Shell modules** - Functions sourced into the current shell (`shell/modules/`)
- **`toolbox` CLI** (Go) — `install`, `list`, `clean`, `shell`, `bootstrap`, `deps`; repo root `./toolbox` is a bash proxy that builds `bin/toolbox` if needed

## Commands

### AWS

| Command | Description |
|---------|-------------|
| `aws-ec2` | EC2 list, describe, find SSH key file |
| `aws-eks` | EKS list, describe, kubeconfig |
| `aws-env` | Profile/region picker TUI; token status — used via `aws.env` shell wrapper |
| `aws-find-ip` | Find an IP across profiles and US regions |
| `aws-screen-monitor` | EC2 console screenshot loop during reboots |
| `aws-token-timeout` | AWS session token expiration |
| `saml2aws-op` | `saml2aws` with 1Password-backed JumpCloud creds |
| `ssm-connect` | Bubble Tea TUI, then `aws ssm start-session` |

### Networking

| Command | Description |
|---------|-------------|
| `cert-check` | TLS certificate inspection |
| `httpkit` | HTTP trace, probe, Cloudflare Rules Trace |
| `netbird-status` | NetBird VPN status |
| `netbird-up` | Connect NetBird |
| `netinfo` | Network interfaces (Swift; `--plain` for text) |

### Kubernetes

| Command | Description |
|---------|-------------|
| `k8s-hpa-analyzer` | Inspect HorizontalPodAutoscaler objects |
| `k8s-restart-resource` | Rolling restart for Deployment or DaemonSet |

### PagerDuty

| Command | Description |
|---------|-------------|
| `pd-incident` | One incident, multiple output formats |
| `pd-report` | Multi-service incident report for a time range |
| `pyduty` | Maintenance windows and service search |

### System

| Command | Description |
|---------|-------------|
| `brew-search` | Homebrew search helper |
| `nerdfont-install` | Nerd Font installer |
| `op-clip` | 1Password clipboard helper |
| `tmux-exec` | Run commands in tmux panes |
| `vmrss` | Process RSS memory |

### SSH

| Command | Description |
|---------|-------------|
| `ssh-remove-host` | Edit `known_hosts` |
| `ssh-sc` | SSH key and host helper (interactive) |

### Productivity

| Command | Description |
|---------|-------------|
| `join-call` | Textual TUI for Teams deeplinks (macOS) |

### GitHub

| Command | Description |
|---------|-------------|
| `ghrel` | Browse releases and download assets (TUI); see [`docs/ghrel.md`](docs/ghrel.md) |

### AI

| Command | Description |
|---------|-------------|
| `ollama-update` | Update Ollama models |

### Media

| Command | Description |
|---------|-------------|
| `mix-audio` | Combine audio files |

## Documentation

Longer guides (examples, env vars, scenarios) live under `docs/`. For the **manager**, bootstrap, `toolboxctl`, and `shell.yaml`, see [`docs/toolbox.md`](docs/toolbox.md). For Go command standards, see [`docs/go-cli.md`](docs/go-cli.md). For Python, shell, Swift, and cross-tool metadata standards, see [`docs/tool-authoring.md`](docs/tool-authoring.md). For HTTP tooling start with `docs/httpkit.md`, or see **Documentation** in `AGENTS.md` for the full list.

## Installation

### Prerequisites

- macOS or Linux
- [Go 1.25+](https://go.dev/dl/) (builds the `toolbox` binary the first time; also used to build other `cmd/*` tools)
- [uv](https://github.com/astral-sh/uv) (Python scripts)
- **macOS:** [Homebrew](https://brew.sh) and **`brew bundle`** (run `brew tap Homebrew/bundle` if `brew bundle` is missing), Swift / Xcode CLT (for Swift tools in `scripts/`)
- **Linux:** your distro’s packages for `go`, `uv`, and anything in `deps/*.yaml` (no Homebrew required)

### Setup

1. Clone and enter the repo (adjust path if yours differs):
   ```bash
   git clone https://github.com/rvwallace/toolbox ~/toolbox
   cd ~/toolbox
   ```

2. **New machine:** run `./bootstrap.sh` (macOS: generates a temp `Brewfile` from `deps/*.yaml` and optional `brew bundle install`; Linux: prints `apt`/`dnf` paste lines). See [`docs/toolbox.md`](docs/toolbox.md).

3. Install commands into `bin/`:
   ```bash
   ./toolbox install
   ```

4. Source shell integration:
   ```bash
   # ~/.zshrc or ~/.bashrc
   source ~/toolbox/shell/init.sh
   ```

5. Reload the shell or open a new terminal.

## Usage

### `toolbox` manager

The repo root `./toolbox` script runs the Go binary in `bin/` (or builds it with `go build`).

```bash
./toolbox install   # Symlinks, compile Swift/Go as configured
./toolbox list
./toolbox clean     # Drop dead symlinks in bin/
./toolbox shell list    # Modules with enabled/override/runtime state
./toolbox help
```

### Shell integration

After `source shell/init.sh`:

- `bin/` is on `PATH`
- Modules under `shell/modules/` load (honors `~/.config/silentcastle/toolbox/shell.yaml` when `bin/toolbox` exists)
- `toolbox_reload` reapplies init after edits
- `toolboxctl` wraps `toolbox` with `-r` / `-t` (see [`docs/toolbox.md`](docs/toolbox.md))

### Shell modules

| Module | Functions |
|--------|-----------|
| `aws.sh` | `aws.caller_identity`; `aws.env` (set/profile/region/show/clear/token-status — wraps `aws-env`) |
| `ai.sh` | `claude.monitor` |
| `ai.zsh` | Alt-e `aichat` dispatcher (`docs/ai.md`) plus zsh completion for `aichat` |
| `cmux.zsh` | zsh completion for `cmux`, `cssh`, and `csshjc` |
| `git.sh` | `git.ignore.add` plus git helper functions |
| `tmux.sh` | `tp` popup helper |
| `git.zsh` | zsh completion for `git.ignore.add` |
| `tmux.zsh` | zsh completion for `tp` |

## Project structure

```text
toolbox/
├── README.md
├── AGENTS.md
├── CONTEXT.md
├── toolbox              # bash proxy → bin/toolbox (builds with go if needed)
├── bootstrap.sh         # deps + build on new systems
├── deps/                # toolbox.yaml + tools.yaml (brew / apt / dnf lists)
├── bin/                 # gitignored; symlinks + compiled binaries
├── docs/                # Optional per-tool markdown guides (+ toolbox.md)
├── scripts/             # By domain: aws/, net/, k8s/, ...
├── cmd/                 # Go CLIs (includes toolbox)
├── internal/            # Shared Go code used by multiple commands only
└── shell/
    ├── init.sh
    ├── toolboxctl.sh
    └── modules/
```

## Adding tools

### Python

1. Add `scripts/<domain>/<name>.py` with `#!/usr/bin/env -S uv run --script` and a PEP 723 block.
2. `chmod +x` the file.
3. `./toolbox install`.
4. If the tool is OS-specific, add `toolbox-platforms` metadata as documented in [`docs/tool-authoring.md`](docs/tool-authoring.md).

### Shell

1. Add `scripts/<domain>/<name>.sh` with `#!/usr/bin/env bash` and `set -euo pipefail` as needed.
2. `chmod +x`, then `./toolbox install`.
3. If the tool is OS-specific, add `toolbox-platforms` metadata as documented in [`docs/tool-authoring.md`](docs/tool-authoring.md).

### Go

1. Add `cmd/<name>/main.go`.
2. `./toolbox install` (when the manager builds that path).
3. Follow [`docs/go-cli.md`](docs/go-cli.md): use Kong for CLI parsing/help; use Bubble Tea v2 for TUIs.
4. If the command is OS-specific, add `cmd/<name>/toolbox.yaml` as documented in [`docs/tool-authoring.md`](docs/tool-authoring.md).

See `AGENTS.md` for templates and conventions.

## Conventions

- Folders follow **purpose** (`scripts/aws/`), not language
- Command names are **kebab-case**
- Python: **typer** + **rich** where it fits; inline deps only
- Python, shell, and Swift tools may declare `toolbox-platforms` metadata; Go commands may declare platforms in `cmd/<name>/toolbox.yaml`
- Go: **Kong** for CLI parsing/help; **Bubble Tea v2** for TUIs; **Bubbles v2** and **Lip Gloss v2** when needed
- Config: `~/.config/silentcastle/<tool>.json` (or tool-specific files in `docs/`); toolbox shell modules: `~/.config/silentcastle/toolbox/shell.yaml` (see `docs/toolbox.md`)
- Cache: `~/.cache/silentcastle/`

## License

MIT — see [LICENSE](LICENSE).
