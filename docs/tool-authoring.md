# Tool authoring conventions

Repo-wide conventions for user-facing tools in `scripts/` and `cmd/`.

Use this with:

- [`docs/go-cli.md`](docs/go-cli.md) for Go command structure and TUI conventions
- [`docs/toolbox.md`](docs/toolbox.md) for installer and shell manager behavior

## Defaults

- Organize tools by domain, not by language
- Keep the user-facing command name stable and kebab-case
- Put Python, shell, and Swift tools under `scripts/<domain>/`
- Put Go commands under `cmd/<name>/`
- If a tool is portable, omit platform metadata and it defaults to `all`

## Platform metadata

`toolbox install` is platform-aware.

- Tools marked for `darwin` install only on macOS
- Tools marked for `linux` install only on Linux
- Missing metadata means `all`

Supported values:

- `all`
- `linux`
- `darwin`
- `macos` as an accepted alias for `darwin`

### Script header metadata

For Python and shell:

```bash
# toolbox-platforms: darwin
```

For Swift:

```swift
// toolbox-platforms: darwin
```

Multiple platforms:

```bash
# toolbox-platforms: linux,darwin
```

If the header is absent, the tool is treated as universal.

### Go command metadata

For Go commands, use an optional sidecar file:

`cmd/<name>/toolbox.yaml`

```yaml
platforms:
  - darwin
```

If `toolbox.yaml` is absent, the command is treated as universal.

## Python scripts

- Use `#!/usr/bin/env -S uv run --script`
- Use a PEP 723 metadata block
- Prefer `typer` for CLI shape and `rich` for presentation when it helps
- Keep config and cache paths under `~/.config/silentcastle/` and `~/.cache/silentcastle/`

Minimal shape:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["typer", "rich"]
# ///
# toolbox-platforms: all

"""One-line description."""
```

## Shell scripts

- Use `#!/usr/bin/env bash`
- Use `set -euo pipefail` unless there is a clear reason not to
- Keep scripts focused on one task
- Prefer clear usage text and concrete stderr errors

Minimal shape:

```bash
#!/usr/bin/env bash
# toolbox-platforms: linux,darwin
set -euo pipefail
```

## Swift scripts

- Use `#!/usr/bin/env swift` for interpreted Swift tools in `scripts/`
- If a Swift tool is compiled by `toolbox install`, keep the source in `scripts/` and let the installer place the binary in `bin/`
- Add platform metadata when the tool uses Apple-only frameworks or other OS-specific APIs

Minimal shape:

```swift
#!/usr/bin/env swift
// toolbox-platforms: darwin
import Foundation
```

## Go commands

- Follow [`docs/go-cli.md`](docs/go-cli.md)
- Standardize on Kong for CLI parsing/help
- Standardize on Bubble Tea v2 for TUIs
- Keep command-local code with the command
- Use root `internal/` only for code shared by multiple commands

## Choosing platform metadata

- Use `darwin` only when the tool truly depends on macOS behavior or frameworks
- Use `linux` only when the tool truly depends on Linux-only behavior
- Use no metadata when the tool should work on both and dependency availability is the real variable
- Do not use platform metadata to represent optional runtime dependencies such as `kubectl`, `fzf`, or `brew`

Platform support and dependency support are different:

- `darwin` means "do not install on Linux"
- missing `kubectl` means "tool may be installed but not usable until deps are present"
