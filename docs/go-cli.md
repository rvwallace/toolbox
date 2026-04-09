# Go CLI conventions

Repo-wide conventions for Go commands under `cmd/`.

This is the default pattern for new Go commands and the target pattern when existing Go commands are touched.

## Defaults

- Use `github.com/alecthomas/kong` for CLI parsing and help
- Use Bubble Tea v2 for TUIs: `charm.land/bubbletea/v2`
- When a TUI needs common components or styling, stay on the v2 line:
  - `charm.land/bubbles/v2`
  - `charm.land/lipgloss/v2`
- Put user-facing binaries in `cmd/<name>/`
- Put command-local Go logic with the command in `cmd/<name>/`
- Use root `internal/` only for code shared by multiple commands

## Why this standard

- Kong gives nested subcommand help by default, which is a better fit than the current hand-rolled parsing in `cmd/toolbox`
- Bubble Tea v2 is already in use for `ghrel` and `ssm-connect`
- One repo-wide pattern makes new tools easier to add and older tools easier to migrate

## Command structure

For non-TUI commands, prefer:

1. `cmd/<name>/main.go` for wiring and process exit
2. A typed Kong CLI struct for commands, flags, args, and help text
3. Small package-local files for behavior split by concern
4. Keep single-command helpers in `cmd/<name>/` or `cmd/<name>/internal/`
5. Promote code to root `internal/` only when it is genuinely shared across commands

For TUIs, prefer:

1. Kong for top-level flags and startup validation
2. A `newModel(...)` constructor
3. Bubble Tea v2 for the interactive program lifecycle
4. Separate files for config, data loading, and TUI model/update/view logic

## Help and command behavior

- Every Go CLI should provide `--help`
- Nested subcommands should also provide context-sensitive help
- Use Kong help text rather than hand-built help strings where practical
- Command names stay user-facing and kebab-case
- Prefer long flags in kebab-case, for example `--force-refresh`
- Only add short flags when they are common and obvious
- If a command is not a TUI, prefer `Run() error` methods on Kong command structs

## Output and errors

- Primary command output goes to stdout
- Errors and warnings go to stderr
- Error messages should be short and concrete
- Prefer command-prefixed errors when context matters, for example `ssm-connect: AWS region is not set`
- Exit code `0` for success
- Exit code `1` for operational failures
- Exit code `2` for usage or validation errors when the command framework makes that distinction easy

## Config, cache, and env

- Config belongs under `~/.config/silentcastle/<tool>/` or a single clear file under that path
- Cache belongs under `~/.cache/silentcastle/<tool>/`
- Environment variables should use stable, tool-specific names
- Document env precedence clearly when flags, config, and env interact

Recommended precedence:

1. explicit flags
2. environment
3. config file
4. built-in defaults

If a command intentionally differs, document the reason in code help and `docs/<tool>.md`.

## Package boundaries

- `cmd/<name>/` is the default home for code used by only one command
- `cmd/<name>/internal/` is acceptable when a command needs subpackages but the code is still command-local
- Root `internal/` is for sharable libraries used by multiple commands
- Do not move code into root `internal/` just because it is large
- If a package has only one consumer, keep it with that command unless a second consumer is expected immediately and the reuse boundary is already clear

## TUI conventions

- Use Bubble Tea v2 for all new TUIs
- Use alt screen only when it materially improves the workflow
- Keep help text visible in the UI for the main keybindings
- Keep data loading and shell-out logic outside the view code
- Prefer a startup validation phase before entering the TUI
- If a TUI also needs non-interactive output, expose that as a normal Kong subcommand or flag-driven mode instead of overloading the TUI path

## Docs

- If the built-in help is enough, `--help` may be the only documentation
- If a command has workflows, env combinations, auth setup, or multi-step scenarios, add `docs/<tool>.md`
- Keep the long-form docs plain and example-driven

## Testing

- New shared logic in root `internal/` should be unit-testable
- Pure parsing and validation logic should stay outside `main()` where practical
- TUI-heavy code does not need exhaustive snapshot testing by default, but parsing, config, and state transitions should be testable where it pays off

## Migration guidance

- New Go commands should start on Kong
- Existing hand-rolled Go CLIs do not need a blind rewrite
- When an existing Go CLI gets meaningful work, migrate it toward this standard unless there is a strong reason not to
- `ghrel` and `ssm-connect` should stay on Bubble Tea v2; if they gain richer top-level command structure, move their argument parsing to Kong as part of normal maintenance

## Minimal patterns

Non-TUI command shape:

```go
package main

import (
	"fmt"

	"github.com/alecthomas/kong"
)

type listCmd struct {
	JSON bool `help:"Emit JSON."`
}

func (c *listCmd) Run() error {
	fmt.Println("implement me")
	return nil
}

var cli struct {
	Version kong.VersionFlag `help:"Print version."`

	List listCmd `cmd:"" help:"List items."`
}

func main() {
	ctx := kong.Parse(&cli,
		kong.Name("example"),
		kong.Description("One-line command summary."),
	)
	err := ctx.Run()
	ctx.FatalIfErrorf(err)
}
```

TUI command shape:

```go
package main

import (
	tea "charm.land/bubbletea/v2"
	"github.com/alecthomas/kong"
)

var cli struct {
	Profile string `help:"AWS profile." env:"AWS_PROFILE"`
	NoAlt   bool   `help:"Run without alternate screen mode."`
}

func main() {
	kctx := kong.Parse(&cli,
		kong.Name("example-tui"),
		kong.Description("Example TUI command."),
	)

	model, err := newModel(cli.Profile)
	kctx.FatalIfErrorf(err)

	opts := []tea.ProgramOption{}
	if !cli.NoAlt {
		opts = append(opts, tea.WithAltScreen())
	}

	_, err = tea.NewProgram(model, opts...).Run()
	kctx.FatalIfErrorf(err)
}
```
