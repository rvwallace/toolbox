# Toolbox Development Guide

Working instructions for AI assistants and future sessions.

## Quick Reference

```bash
# New machine: temp Brewfile + brew bundle (mac) or apt/dnf paste lines (Linux)
./bootstrap.sh

# Install/update (symlinks scripts, compiles Go/Swift)
./toolbox install

# List available commands
./toolbox list

# Remove dead symlinks
./toolbox clean

# Shell modules (see docs/toolbox.md)
./toolbox shell list
toolboxctl disable zmx -r

# Reload shell environment (after sourcing init.sh)
toolbox_reload
```

When something in the plan or repo looks wrong or contradictory, **ask the user** before plowing ahead (see `docs/toolbox.md` / pushback habit).

## Current State

**Migration complete.** The repo currently defines 28 user-facing CLI tools plus the **`toolbox`** manager binary. Actual `bin/` contents after `./toolbox install` vary by platform because install now skips tools that declare unsupported OS metadata.

| Category | Commands |
|----------|----------|
| aws | `aws-ec2`, `aws-eks`, `aws-env`, `aws-find-ip`, `aws-screen-monitor`, `aws-token-timeout`, `saml2aws-op`, `ssm-connect`, `ssm-pyconnect` |
| net | `cert-check`, `httpkit`, `netbird-status`, `netbird-up`, `netinfo` |
| k8s | `k8s-hpa-analyzer`, `k8s-restart-resource` |
| pagerduty | `pd-incident`, `pd-report`, `pyduty` |
| productivity | `join-call` |
| github | `ghrel` |
| sys | `brew-search`, `nerdfont-install`, `op-clip`, `tmux-exec`, `vmrss` |
| ai | `ollama-update` |
| media | `mix-audio` |
| ssh | `ssh-remove-host`, `ssh-sc` |
| manager | `toolbox` |

Shell modules:
- `ai.sh` / `ai.bash` / `ai.zsh` - `claude.monitor`; adds the Alt-e `aichat` widget and completions for `aichat`
- `aws.sh` / `aws.bash` / `aws.zsh` - `aws.caller_identity` function; `aws.env` shell wrapper (delegates set/profile/region/show/token-status to `aws-env` binary; handles `clear` in shell); profile cache and completions
- `chef.sh` / `chef.bash` / `chef.zsh` - Chef environment helper functions
- `cmux.sh` / `cmux.zsh` - `cmux.ssh`, `cmux.ssh.jc`, `cssh`, `csshjc` and completions
- `git.sh` / `git.bash` / `git.zsh` - `git.ignore.add`, git helper functions and completions
- `kube.sh` / `kube.bash` / `kube.zsh` - Kubernetes interactive shell module (`k.env` helper)
- `net.sh` - network-related shell helpers
- `tfswitch.bash` / `tfswitch.zsh` - shell integrations for `tfswitch` (if installed)
- `tmux.sh` / `tmux.bash` / `tmux.zsh` - `tp` tmux popup helper and completions
- `zmx.sh` / `zmx.bash` / `zmx.zsh` - `zmx.select`, `zmx.history`, `zmx.kill`, `zmx.detach`, `zmx.wait` (requires `zmx` and `fzf`); keybindings: Alt-a → `zmx attach $(basename $PWD)`; Alt-d → `zmx detach`

Shell module pattern:
- Put cross-shell sourced helpers in `shell/modules/*.sh`
- Put zsh-only widgets, keybindings, and completions in `shell/modules/*.zsh`
- Put bash-only widgets, keybindings, and completions in `shell/modules/*.bash`
- Prefer toolbox-owned completions to live beside the toolbox helper they complete

Compiled tools:
- `netinfo` - Swift binary (icons by default, use `--plain` for text)

Go CLIs (beyond `toolbox`):
- `ghrel` - GitHub release TUI (`cmd/ghrel/`, Bubble Tea v2)
- `ssm-connect` - EC2 Session Manager TUI (`cmd/ssm-connect/`, Bubble Tea v2)
- `aws-env` - AWS profile/region picker TUI + token-status (`cmd/aws-env/`, Bubble Tea v2); used via `aws.env` shell wrapper in `shell/modules/aws.sh`

Go CLI pattern:
- Use `docs/go-cli.md` for repo-wide Go command conventions
- Standardize on `github.com/alecthomas/kong` for CLI parsing/help
- Standardize on Bubble Tea v2 for TUIs; use Bubbles v2 and Lip Gloss v2 when needed

## httpkit (`scripts/net/httpkit.py`)

HTTP utilities (Typer + Rich + httpx, PEP 723). After `./toolbox install`, run as `httpkit`. Examples and scenarios: `docs/httpkit.md`.

| Subcommand | Purpose |
|------------|---------|
| `trace <url>` | Walk redirect chain hop-by-hop (default `HEAD`; `-X GET` if origin rejects HEAD). |
| `probe <url>` | Single request; `-L` / `--follow` follows redirects with a max (httpx). |
| `cf-trace <url>` | [Cloudflare Rules Trace API](https://developers.cloudflare.com/api/resources/request_tracers/subresources/traces/methods/create/) - simulates how zone rules apply to a URL. |

**cf-trace credentials:** **`--account-id`** / `CLOUDFLARE_ACCOUNT_ID` (required in the API path) and **`--api-token`** / `CLOUDFLARE_API_TOKEN`. Token needs **Account → Request Tracer → Read** (see `scripts/net/httpkit.py` module docstring).

**cf-trace output:** The API returns nested `trace` arrays (rulesets/rules); the CLI prints a readable multiline summary. Use **`--json`** for the raw envelope when something is missing from the table. Matched steps are highlighted in green.

## Migration Complete

Migrated from:
- `~/silentcastle/projects/pyscripts/packages/` - All Python CLI tools
- `~/silentcastle/scripts/` - Shell scripts and netinfo.swift
- `~/.myenv/zsh/environments/default/scripts/` - System utilities

**Old repos can be archived:**
- `silentcastle/projects/pyscripts/`
- `silentcastle/scripts/`
- `~/.myenv/zsh/environments/default/scripts/` (scripts migrated)

## Adding a Script

1. Copy to `scripts/<domain>/<name>.py` (or .sh, .swift)
2. Ensure shebang is correct:
   - Python: `#!/usr/bin/env -S uv run --script`
   - Shell: `#!/usr/bin/env bash`
   - Swift: `#!/usr/bin/env swift` (for interpreted) or no shebang (compiled)
3. Make executable: `chmod +x scripts/<domain>/<name>.py`
4. Run `./toolbox install`
5. Test: `<name>` (without extension)

If a tool is OS-specific, add platform metadata as documented in `docs/tool-authoring.md`:
- Python / shell: `# toolbox-platforms: darwin` or `# toolbox-platforms: linux,darwin`
- Swift: `// toolbox-platforms: darwin`

Note: Swift scripts are compiled with `swiftc -O`, not symlinked. The binary is placed directly in `bin/`.

## Adding a Shell Module

Shell modules are for functions that must run in the current shell (not subprocesses):

1. Create `shell/modules/<name>.sh`
2. Add functions (no shebang needed, will be sourced)
3. Run `toolbox_reload` or open new terminal

## Python Script Template

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["typer", "rich"]
# ///
"""One-line description of the tool."""

import typer

app = typer.Typer()

@app.command()
def main():
    """Main command."""
    pass

if __name__ == "__main__":
    app()
```

## Shell Script Template

```bash
#!/usr/bin/env bash
set -euo pipefail

# Tool description

main() {
    echo "Hello"
}

main "$@"
```

## deps/*.yaml package names

Package names differ across distros. Before adding or changing an entry, verify the name exists in the target repo:

| Key | Check against |
|-----|--------------|
| `brew` | `brew search <name>` or formulae.brew.sh |
| `apt_packages` | Ubuntu 24.04 LTS — packages.ubuntu.com |
| `dnf_packages` | Fedora (current stable) — packages.fedoraproject.org |
| `pacman_packages` | Arch (current) — archlinux.org/packages |

Known differences: `fd` (Arch/brew) vs `fd-find` (apt/dnf). `ffmpeg` requires RPM Fusion on Fedora; bootstrap handles this automatically. `yazi` is Arch/brew only — not in Ubuntu apt or Fedora dnf (snap or binary install required).

## Coding Conventions

- Organize by domain/purpose, not by language
- Command names are kebab-case: `cert-check`, `aws-ec2`
- Python uses inline deps (PEP 723), no shared virtualenv
- Use `docs/tool-authoring.md` for Python, shell, Swift, and platform metadata conventions
- Go CLIs use Kong for parsing/help and Bubble Tea v2 for TUIs (see `docs/go-cli.md`)
- Keep scripts focused on one task
- Use `typer` for Python CLIs, `rich` for output formatting
- Store config in `~/.config/silentcastle/<tool>.json` (toolbox shell: `~/.config/silentcastle/toolbox/shell.yaml`)
- Store cache in `~/.cache/silentcastle/`

## Next Steps

1. Test all commands work correctly in new shell
2. Archive old repos (`pyscripts/` and `scripts/`)
3. Consider adding more tools or rewriting existing ones in Go

## Documentation

Extended guides (same style as `docs/httpkit.md`) live under `docs/`:

- `docs/httpkit.md`
- `docs/go-cli.md`
- `docs/tool-authoring.md`
- `docs/pagerduty.md` (`pyduty`, `pd-incident`, `pd-report`)
- `docs/ssm-connect.md`
- `docs/saml2aws-op.md`
- `docs/aws-ec2.md`
- `docs/aws-eks.md`
- `docs/k8s-hpa-analyzer.md`
- `docs/k8s-restart-resource.md`
- `docs/aws-screen-monitor.md`
- `docs/join-call.md`
- `docs/mix-audio.md`
- `docs/ghrel.md`
- `docs/ai.md`, `docs/zmx.md`
- `docs/toolbox.md` — manager (`cmd/toolbox`), proxy, bootstrap, `deps/*.yaml`, user `shell.yaml`, `toolboxctl`

## File Reference

| File | Purpose |
|------|---------|
| `README.md` | Human overview, command tables, quick start |
| `CONTEXT.md` | Architecture and design documentation |
| `docs/<tool>.md` | Optional per-tool docs (see **Documentation** above) |
| `AGENTS.md` | This file - working instructions |
| `toolbox` | Bash proxy → `bin/toolbox` (Go); builds with `go` if missing |
| `bootstrap.sh` | New-system deps (`deps/*.yaml`); macOS temp Brewfile + `brew bundle install` w/ confirm; Linux: installs paru from AUR if on Arch without it, then auto-installs via paru/pacman/apt/dnf (falls back to paste-line hints); both paths run `uv tool install` and set up LazyVim |
| `deps/toolbox.yaml` | Extra prereqs: `brew`, `apt_packages`, `dnf_packages`, `pacman_packages` |
| `deps/tools.yaml` | Optional usual tools (second mac batch; Linux install block); same four keys |
| `go.mod` / `go.sum` | Go module `silentcastle/toolbox` |
| `shell/init.sh` | Shell initialization (source from .zshrc) |
| `shell/toolboxctl.sh` | `toolboxctl` function (`-r` / `-t`; sourced by `init.sh`) |
| `shell/modules/*.sh` | Shell-native functions (sourced in bash and zsh) |
| `shell/modules/*.bash` | bash-only modules (widgets, completions; sourced for bash v4+) |
| `shell/modules/*.zsh` | zsh-only modules (ZLE, etc.; sourced when `init.sh` runs under zsh) |
| `scripts/<domain>/*.py` | Python CLI tools (e.g. `scripts/net/httpkit.py` → `httpkit`) |
| `cmd/<tool>/main.go` | Go CLI tools (`cmd/toolbox`, `cmd/ghrel`, `cmd/ssm-connect`, …) |
| `internal/*` | Shared Go packages used by multiple commands only |
| `scripts/<domain>/*.swift` | Swift tools (compiled to bin/) |
| `bin/` | Symlinks + compiled binaries (gitignored) |
