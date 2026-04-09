# CONTEXT

This file describes my `toolbox` project so an AI assistant can quickly understand the setup.

## Goal

Maintain a single repo for my personal command-line tools:

- Shell scripts
- Python scripts (using `uv run --script` with inline deps)
- Go programs
- Swift tools (e.g. `netinfo` in `scripts/net/`, compiled to `bin/`)
- Other compiled languages as needed

I want:

- All tools versioned together.
- A simple way to install/update everything and expose them on my PATH.
- Freedom to rewrite tools in different languages without changing how I run them.
- Shell session customization (functions, env vars) in the same repo.

## Directory Layout

```text
toolbox/
  README.md               # Overview and quick start
  AGENTS.md               # AI / dev working notes
  CONTEXT.md              # This file

  docs/                   # Long-form guides (httpkit, toolbox, aws, k8s, ...)
  deps/                   # toolbox.yaml + tools.yaml (brew/apt/dnf/pacman package lists for bootstrap)
  bin/                    # Symlinks + compiled binaries (gitignored)
                          # Populated by `toolbox install` (Go)
  toolbox                 # Bash proxy → bin/toolbox
  bootstrap.sh            # New-machine setup (auto-installs via paru/pacman/apt/dnf; uv tool installs)

  scripts/                # CLI tools organized by domain
    aws/
      aws-ec2.py
      aws-eks.py
      aws-find-ip.py
      aws-screen-monitor.sh
      aws-token-timeout.py
      saml2aws-op.py
      ssm-pyconnect.py
    net/
      cert-check.py
      httpkit.py
      netbird-status.py
      netbird-up.py
      netinfo.swift
    k8s/
      k8s-hpa-analyzer.py
      k8s-restart-resource.sh
    ssh/
      ssh-remove-host.sh
      ssh-sc.py
    pagerduty/
      pd-report.py
      pd-incident.py
      pyduty.py
    productivity/
      join-call.py
    # More domains as needed (sys/, git/, media/, etc.)

  cmd/                    # Go CLIs (`cmd/toolbox/`, `cmd/ghrel/`, …)
    toolbox/
      main.go
    ghrel/
      main.go
    ssm-connect/
      main.go

  internal/               # Shared Go packages used by multiple commands only

  shell/                  # Shell session customization
    init.sh               # Sourced from .zshrc/.bashrc; honors ~/.config/silentcastle/toolbox/shell.yaml via `bin/toolbox shell effective`
    toolboxctl.sh         # `toolboxctl` wrapper
    modules/
      aws.sh              # Shell-native functions (e.g. aws.caller_identity)
      # More modules as needed (ai, net, zmx, …)

  go.mod                  # Module: silentcastle/toolbox
```

## Key Conventions

- **Organize by purpose/domain**, not by language.
- Scripts live under `scripts/<domain>/` (e.g. `scripts/net/`, `scripts/aws/`).
- Go CLIs live under `cmd/<name>/` (for example `cmd/toolbox/`, `cmd/ghrel/`, `cmd/ssm-connect/`).
- Shared Go code used by multiple commands lives under `internal/`.
- Command-local Go code stays in `cmd/<name>/` or `cmd/<name>/internal/`.
- Go CLIs standardize on Kong for parsing/help and Bubble Tea v2 for TUIs (see `docs/go-cli.md`).
- Python, shell, Swift, and Go command metadata conventions live in `docs/tool-authoring.md`.
- Compiled binaries and symlinks go in `bin/` (gitignored).
- Shell customization (functions, env vars) lives under `shell/`.
- Longer examples, env vars, and scenarios for specific tools live under `docs/` (see `AGENTS.md` for the list).

## Command Naming

User-facing commands are stable and language-agnostic:

| Command | Implementation |
|---------|----------------|
| `cert-check` | `scripts/net/cert-check.py` |
| `httpkit` | `scripts/net/httpkit.py` |
| `aws-ec2` | `scripts/aws/aws-ec2.py` |
| `netinfo` | `scripts/net/netinfo.swift` |

Inside the repo, scripts have extensions. The `toolbox` manager creates extension-less symlinks in `bin/`:

```text
bin/cert-check  -> ../scripts/net/cert-check.py
bin/aws-ec2     -> ../scripts/aws/aws-ec2.py
bin/netinfo     -> ../scripts/net/netinfo.swift (or compiled binary)
```

If I rewrite `cert-check` in Go, the command name stays `cert-check`; only the symlink target changes.

## Python Scripts

Python scripts use `uv run --script` with inline dependencies (PEP 723). Each script is self-contained:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["typer", "rich"]
# ///

import typer
# ...
```

No shared virtualenv needed. The `toolbox` manager just symlinks them to `bin/`.

Platform-specific tools can declare install metadata. See `docs/tool-authoring.md`.

## Shell Integration

The `shell/init.sh` script is sourced from `.zshrc` or `.bashrc`:

```bash
source ~/path/to/toolbox/shell/init.sh
```

What it does:

1. Adds `toolbox/bin/` to PATH.
2. Runs `bin/toolbox shell effective` (if the binary exists) and skips sourcing disabled **stems** (`shell.yaml` plus optional env overrides; see `docs/toolbox.md`).
3. Sources `shell/modules/*.sh` (cross-shell), then `shell/modules/*.bash` (for Bash 4+) or `shell/modules/*.zsh` (for Zsh).
4. Defines `toolbox_reload`, then sources `shell/toolboxctl.sh` (`toolboxctl` wrapper).

Shell modules contain shell-native customizations that cannot be standalone scripts:

- Functions like `aws.caller_identity` (wraps aws cli with formatting)
- Environment variable defaults
- Shell prompt customization (if any)

Toolbox shell modules now follow a companion-file pattern when needed:

- `shell/modules/*.sh` for cross-shell sourced helpers and aliases/functions
- `shell/modules/*.bash` / `shell/modules/*.zsh` for interactive shell widgets, keybindings, and completions

That lets toolbox own both the command helper and its zsh completion without relying on a separate external `functions/` or `completions/` tree.

## Go setup

Module path: `silentcastle/toolbox` (`go.mod` at repo root).

The **`toolbox`** CLI is a Go program under `cmd/toolbox/`; toolbox-specific logic stays with that command. Other binaries (for example **`ghrel`** in `cmd/ghrel/` and **`ssm-connect`** in `cmd/ssm-connect/`) add their own `main.go` package; `toolbox install` builds every supported `cmd/*/main.go`.

Repo-wide Go standards are documented in **`docs/go-cli.md`**:

- Use `github.com/alecthomas/kong` for Go CLI parsing and nested help
- Use Bubble Tea v2 for TUIs
- Keep command-local code with the command in `cmd/<name>/`
- Use root `internal/` only for code shared across multiple commands

```bash
go build -o bin/<tool-name> ./cmd/<tool-name>
```

The repo root **`toolbox`** file is a thin bash script that `exec`s `bin/toolbox` or runs `go build` first.

## Toolbox manager

Implemented in Go (`cmd/toolbox`):

```bash
./toolbox install       # Link supported py/sh, build supported Swift/Go tools
./toolbox clean
./toolbox list
./toolbox shell …       # shell.yaml / module stems
./toolbox deps scan     # advisory
./toolbox bootstrap …   # linux-print, brew-bundle (temp Brewfile; used by bootstrap.sh)
```

Behavior matches the former bash script with added platform-awareness: it links supported `scripts/**/*.{py,sh}`, compiles supported `*.swift` when `swiftc` exists, builds supported `cmd/*/main.go`, and skips tools whose declared platform metadata does not match the current OS.

See **`docs/toolbox.md`** for bootstrap, `deps/`, `toolboxctl`, and env vars.

## .gitignore

```gitignore
bin/
```

The `bin/` directory is always regenerated by `toolbox install`.

## Migration Notes

This repo consolidates:

- `silentcastle/projects/pyscripts/` - Python CLI tools (moved to `scripts/`)
- `silentcastle/scripts/sc-init.sh` - Shell init (simplified to `shell/init.sh`)
- `silentcastle/scripts/shell.d/` - Shell modules (moved to `shell/modules/`)

## What I Want From the Assistant

- Respect this layout and naming (purpose-driven, not language-driven).
- Help me:
  - Design and improve the `toolbox` manager (Go CLI and bootstrap).
  - Add new tools following this structure.
  - Refactor a script into Go/Swift without breaking the CLI name.
  - Keep `shell/init.sh` readable; prefer shared logic in `bin/toolbox` where appropriate.
  - Add or update `docs/<tool>.md` when a tool needs scenarios beyond `--help`, and keep that style plain (no em dashes as punctuation; see `docs/httpkit.md`).
