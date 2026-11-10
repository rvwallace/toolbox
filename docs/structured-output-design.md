# Toolbox Structured Output Design

**Status:** Proposed for review  
**Date:** 2026-09-27  
**Scope:** Architecture audit and incremental migration plan; no command behavior is changed by this document.

## Executive summary

Toolbox is already a useful portable collection, but it does not yet have one
output model. It contains Python CLIs built with Typer, Click, Textual, and
Rich; Go CLIs and Bubble Tea TUIs; Bash helpers; and Nushell modules. A few
Python commands already emit JSON, but the flags, shapes, diagnostic streams,
and exit semantics are command-specific.

The recommended direction is:

1. Make JSON the one canonical machine-readable format.
2. Add `--json` only to commands that produce query/report/check data.
3. Keep the default human output and existing command names intact.
4. Treat `--json` as a strict stdout mode: exactly one JSON value, followed by
   a newline; diagnostics, progress, and warnings go to stderr.
5. Use `--jsonl` only for an explicitly documented stream of independent
   records. It is not a second spelling of ordinary JSON.
6. Do not add YAML, CSV, TOML, or TSV as toolbox-wide output formats. Consumers
   can transform JSON with Nushell, `jq`, Python, or another tool.
7. Separate command execution failure from a completed health/check result in
   exit codes.

This is a compatibility-preserving capability, not a repository-wide rewrite.
The first pilots should be `httpkit`, `aws-ec2`, `aws-eks`, `netbird-status`,
and `k8s-hpa-analyzer`, because together they test existing JSON support,
AWS SDK data, an upstream JSON boundary, Kubernetes client objects, and rich
human presentation.

## 1. Current architecture

### Repository shape

The repository installs tools from `scripts/<domain>/` and `cmd/<tool>/` into
`bin/`. The root `toolbox` Bash proxy delegates to the compiled Go
`bin/toolbox`, building it when necessary. `./toolbox install` symlinks Python
and shell scripts, compiles Swift, and builds Go commands. Platform metadata
can prevent unsupported tools from being installed.

Current implementation families are:

| Family | Current technology | Representative entry points |
|---|---|---|
| Python CLIs | PEP 723 scripts, mostly Typer; some Click/argparse | `scripts/aws/aws-ec2.py`, `scripts/net/httpkit.py`, `scripts/pagerduty/pd-report.py` |
| Python interactive tools | Rich, Textual, InquirerPy, fzf/subprocesses | `ssm-pyconnect.py`, `join-call.py`, `k8s-hpa-analyzer.py`, `ssh-sc.py` |
| Go non-TUI manager | Hand-rolled dispatch and flags | `cmd/toolbox/` |
| Go TUIs | Bubble Tea v2; some standard `flag` parsing | `cmd/ghrel/`, `cmd/ssm-connect/`, `cmd/aws-env/` |
| Bash tools | `set -e`/manual parsing, external CLIs and `jq` | `ssm-parameter.sh`, `k8s-restart-resource.sh`, `upkeep.sh` |
| Swift | Compiled system-information utility | `scripts/net/netinfo.swift` |
| Shell modules | Bash/zsh plus Nushell wrappers and aliases | `shell/modules/*.sh`, `*.bash`, `*.zsh`, `*.nu` |

The Go conventions document already establishes useful output guidance:
primary output on stdout, errors and warnings on stderr, and exit codes 0/1/2.
It also says a TUI with non-interactive output should expose a separate
subcommand or flag-driven path. The structured-output contract should extend
that principle to Python and Bash without forcing identical implementation APIs.

### CLI frameworks and shared code

There is no current shared output package. Python scripts each own their
Typer/Click/argparse setup and their Rich console. Go commands own their
models and renderers; `internal/` is effectively empty. Existing commonality
is convention and dependency choice rather than reusable code.

Important current libraries include:

- Python: Typer, Click, argparse, Rich, `requests`, `httpx`, `boto3`, the
  Kubernetes client, PyYAML, Textual, and InquirerPy.
- Go: standard library JSON and `os/exec`, `gopkg.in/yaml.v3`, Kong for the
  documented convention, and Bubble Tea v2 for existing TUIs. Some current Go
  entry points still use hand-written dispatch or `flag`.
- Bash: standard shell utilities, AWS CLI, `kubectl`, `jq`, `fzf`, Terraform,
  GitHub CLI, Chef/knife, `op`, `ffmpeg`, and package managers.

## 2. Current output patterns

### A. Commands with useful existing structured output

- `aws-ec2 describe --format json` and `aws-eks describe --format json` already
  serialize normalized data. Both also expose YAML, which is useful history but
  should not become the model for new commands.
- `httpkit trace`, `probe`, and `cf-trace` already have `--json`. The internal
  payloads are assembled as dictionaries before rendering, which is close to
  the target architecture.
- `pd-incident --format json` emits the raw incident payload, but currently
  prints a Rich summary and progress around it, so it is not a strict JSON
  stream.
- `pd-report --output json|yaml|markdown` writes a report file, but its normal
  stdout path still prints a Rich report and status messages. Its option means
  report-file format, not a general stdout contract.
- `ssm-pyconnect.py` uses JSON for configuration/cache and has structured
  logging, but it is an interactive connection TUI rather than a data CLI.
- `netbird-status` deliberately calls `netbird status --json` and parses the
  upstream JSON instead of scraping human output. It currently renders only a
  Rich summary/detail view.
- Nushell wrappers already consume AWS and Kubernetes JSON directly, for
  example `aws sts get-caller-identity --output json | from json` and
  `kubectl get ns -o json | from json`.

### B. Structured data exists internally but only human output is exposed

- `aws-ec2 list`, `aws-eks list`, and `aws-find-ip` collect records that could
  be serialized with small renderer changes.
- `cert-check` builds certificate dictionaries and check values, then renders
  panels/tables.
- `k8s-hpa-analyzer` obtains typed Kubernetes objects and computes metrics,
  conditions, scaling behavior, and events before rendering Rich panels.
- `httpkit` is the clearest existing separation: payload dictionaries are
  built before either JSON or human rendering, although diagnostics currently
  share the default console.
- PagerDuty service/maintenance-window commands fetch dictionaries and lists
  suitable for a data renderer, but their API calls and Rich rendering are
  interleaved.

### C. Human-first query/report commands

`aws-token-timeout`, `aws-screen-monitor`, `brew-search`, `upkeep`, `vmrss`,
`merge_zsh_history`, and `netinfo` primarily report or manage local state.
Some could gain JSON, but it is not equally valuable for all of them. `upkeep`
in particular is an interactive multi-package-manager workflow whose current
output is progress-oriented.

### D. Action, state-mutating, or interactive commands

`aws-eks kubeconfig`, `ssm-parameter`, `saml2aws-op`, `netbird-up`,
`k8s-restart-resource`, `mix-audio`, `nerdfont-install`, `op-clip`,
`tmux-exec`, `tssh`, Terraform shell helpers, and the Git/AWS/Chef/Kubernetes
environment modules perform actions or modify the current shell/system.
They should not receive a meaningless JSON flag merely for uniformity. Where
an action has a useful completion record, a future JSON result can be added
deliberately, but it must not pretend that an interactive session is a data
query.

### E. TUIs

`aws-env`, `ghrel`, and `ssm-connect` own the terminal while running. JSON
should not be mixed into their Bubble Tea view. If a non-interactive query is
needed, add a separate command or a clearly separate mode with its own data
loader; do not make a TUI renderer conditionally print JSON from inside the
view lifecycle. `join-call` and the Textual path in `ssm-pyconnect` are in the
same category.

### Stream and diagnostic problems found

The current code has several migration hazards:

- Most Rich consoles default to stdout. `httpkit`, `aws-ec2`, `aws-eks`,
  `netbird-status`, `cert-check`, and Kubernetes analysis print status/error
  messages through that console. A later JSON branch must move progress and
  diagnostics to stderr or suppress them.
- `pd-incident` intentionally creates `Console(stderr=True)`, which is a good
  pattern, but it still prints the final selected document with plain `print`.
  Its summary/status behavior must be disabled when machine output is selected.
- `pd-report` prints a Rich report and then writes a JSON file. Its `--output`
  name is therefore ambiguous with stdout format and should not be copied.
- `k8s-restart-resource.sh` already obtains Kubernetes JSON, but immediately
  reduces it to scalar fields with `jq` and logs colored text. A JSON result
  would need a deliberate result object and separation of logs from data.
- `aws-screen-monitor.sh` and several shell tools use command substitution,
  `awk`, `grep`, or `--output text`; this is appropriate for terminal control
  but is not a stable structured-data boundary.
- Some scripts write errors to stdout (`aws-token-timeout.py` is a clear
  example), while others return 1 for every failure type. These are compatibility
  issues to fix only as each command is migrated.
- External command stderr is sometimes merged into stdout (`netbird-up.py`),
  or printed through the same Rich console as normal output. That behavior is
  correct for an interactive progress UI but must be prohibited in strict JSON
  mode.

## 3. Proposed output contract

### Invocation

For commands that support structured output:

```text
default       human-readable terminal output
--json        one JSON value on stdout
--jsonl       one JSON object per output record, only where documented
--quiet       reduce optional human informational output
```

`--json` and `--jsonl` are mutually exclusive. Do not add a global toolbox
wrapper that tries to reinterpret child-command output; the command that owns
the data must own serialization.

Existing commands with `--format json` keep that spelling for compatibility.
During migration, `--json` may be added as a convenient alias, with one
internal output selection. Existing `--format yaml` and report-file options do
not need to be removed immediately, but new commands should not add YAML.

### JSON shape

The successful JSON root should be the natural value for the command:

- collection/list query: an array, so `jq '.[]'` and Nushell `from json`
  work without an invented wrapper;
- one-object query: an object;
- one scalar query: a documented scalar, although an object is preferable when
  the value may gain related fields;
- multi-part report: one object with named fields, such as `{ "hops": [...] }`.

Do not require a universal `{data,meta,error}` envelope for every success.
That adds ceremony and makes simple pipelines less useful. Commands may include
stable metadata fields in a documented object when the metadata is part of the
result, such as AWS profile/region or an HTTP request method.

Field names should be stable, lower-case snake_case, and represent typed values
where practical. Avoid terminal decorations, Rich markup, localized text,
humanized durations, or ANSI escape sequences in JSON. Preserve upstream
fields when `--raw` is the explicitly documented behavior; otherwise expose a
small normalized contract rather than leaking every provider-specific field.

### JSONL

JSONL is justified for a command that can produce a large or incremental set of
independent records, or that can stream records without waiting for the whole
operation. It is not justified merely because a command returns a list.

Good future candidates are a paginated AWS listing, a long PagerDuty incident
report, or a streaming monitor. `httpkit trace` does not need JSONL by default:
its ordinary JSON object containing `hops` is easier to consume atomically.
`--jsonl` must be documented as records only, with no header, footer, progress,
or summary record unless those are part of a versioned record schema.

### stdout and stderr

When `--json` or `--jsonl` is active:

- stdout contains only the requested JSON value or JSON records;
- stdout ends with a newline and contains no Rich status, spinner, banner,
  warning, success message, or debug line;
- diagnostics, warnings, progress, retry notices, and upstream stderr go to
  stderr;
- secrets and credentials never appear in either stream unless the command
  explicitly returns them as its requested data;
- a successful empty result is valid JSON (`[]`, `{}`, or a documented null),
  not a human sentence;
- a serialization failure is an operational error, not a partial successful
  document.

For default human mode, retain current presentation where practical. A
terminal-aware spinner can remain in human mode, but it must be disabled in
machine modes. `--quiet` suppresses optional progress and success chatter in
human mode; it does not change the JSON schema and should not suppress error
diagnostics.

Errors should remain human-readable on stderr in the first contract version.
Do not emit a JSON error object on stdout after a non-zero exit: that makes
shell capture ambiguous and causes consumers to parse both success and failure
schemas. A future `--json-errors` or a versioned error protocol can be
considered only if automation needs it.

### Exit codes

Adopt this baseline for migrated commands:

| Code | Meaning |
|---:|---|
| 0 | The command executed successfully. For a check command, the checked condition is healthy/pass. |
| 1 | The command executed and returned a valid negative result: unhealthy, failed check, rollout not complete, or requested item not found where the command defines that as a negative result. |
| 2 | Invalid invocation, conflicting options, invalid input, or unusable local configuration. |
| 3 | The command could not perform the operation: missing dependency, authentication failure, network/provider failure, malformed upstream response, or serialization failure. |

Code 3 should be introduced only where the distinction is useful; existing
commands can remain on code 1 until migrated and documented. Do not assign
provider-specific codes yet.

The key rule is that “the check ran and found a problem” is different from
“the checker could not run.” For example, a certificate check that connects
successfully and finds an expired certificate may return 1; failure to resolve
the host or load TLS data should return 3. A query returning zero records is
normally a successful query with `[]` and code 0, unless its command explicitly
defines “not found” as a failed check.

This preserves useful monitoring behavior without making a transient AWS,
Kubernetes, or network API error look like a healthy check or an ordinary
negative result.

## 4. Internal design

The desired flow is:

```text
provider/API/upstream JSON
        |
        v
typed or normalized result + command outcome
        |
        +--> human renderer (stdout)
        +--> JSON renderer (stdout)
        +--> JSONL renderer (stdout, when supported)
        +--> diagnostics/progress (stderr)
```

The data collection layer must not know whether the caller chose Rich, JSON,
or JSONL. The renderer must not re-query a provider or parse a human table.

### Python

Use a command-local result type where the command has meaningful domain data:
dataclasses, typed dictionaries, or ordinary dictionaries when the upstream
schema is already the useful contract. Keep `collect_*`/`fetch_*` functions
free of printing. Have `render_human(result)` and `render_json(result)` return
strings or write through an explicitly selected stream.

For Typer commands, parse `--json`, `--jsonl`, and `--quiet` at the command
boundary. Use a dedicated `Console(stderr=True)` for diagnostics and a plain
stdout writer for serialized data. `json.dumps(..., default=...)` should be
used only with an explicit normalization policy; silently stringifying dates,
Decimals, or provider objects can make schemas unstable.

Best existing examples to follow are `httpkit`'s payload construction,
`netbird-status`'s upstream JSON parsing, and `aws-ec2`'s normalization
helpers. The first refactor should move their collection and error handling
away from Rich calls, not introduce a Python framework.

### Go

For a non-TUI command, use a typed result struct and separate `Run() error`,
human rendering, and JSON encoding. `encoding/json.Encoder` should write only
to the selected stdout stream. Keep process exit handling in `main.go`, as the
Go conventions already require.

Do not put JSON into Bubble Tea `View()`. For `aws-env`, `ghrel`, and
`ssm-connect`, retain the interactive path and add a separate non-interactive
subcommand only if a real automation use case appears. The existing AWS
`ssm-connect` code is a strong data-boundary candidate if it later exposes a
list/query mode because it already requests AWS JSON and unmarshals typed
records.

A small Go helper could eventually provide `OutputMode`, `WriteJSON`, and
common exit classification, but it should wait until two or three commands
need the same behavior. Do not create a cross-language serialization layer.

### Bash

Bash tools should implement the contract directly only when their data is
small and already available as JSON from an upstream command. Use `jq` to
select or construct JSON, and use `printf` to write the final value. Keep
logs on stderr. Avoid building JSON by concatenating unescaped strings.

For more complicated data collection, a small Python or Go command is a better
boundary, but do not rewrite a stable action tool solely to gain a JSON flag.
`k8s-restart-resource.sh` is a reasonable future Bash pilot because it already
gets a complete Kubernetes object as JSON; it needs a result object and a log
stream, not a broad rewrite. A shared shell helper is worthwhile only for
flag parsing and stream selection, for example a tiny convention around
`TOOLBOX_OUTPUT_JSON`; it should not attempt to serialize arbitrary shell
variables or normalize provider schemas.

### Nushell

Nushell remains a consumer and interactive composition layer. The existing
Nushell modules demonstrate the intended direction: obtain JSON from AWS or
Kubernetes, parse it with `from json`, and return Nushell records. Toolbox
commands should make that same capability available from Bash, zsh, SSH, CI,
Python, and `jq` without importing Nushell or duplicating SRE logic in `.nu`
files.

Nushell-specific wrappers remain appropriate for environment mutation,
aliases, selection, and ergonomic defaults. A wrapper should not be required
to turn a human toolbox table into records.

## 5. Migration categories

Classification is about structured-output value and refactor size, not tool
quality.

| Category | Commands | Recommendation |
|---|---|---|
| A: small addition | `httpkit`; `aws-ec2 describe`; `aws-eks describe`; `pd-incident` | Already build structured payloads or have JSON. Isolate diagnostics and make serialization strict. Preserve existing format aliases. |
| B: small refactor | `aws-ec2 list`; `aws-eks list`; `aws-find-ip`; `cert-check`; `netbird-status`; `pyduty` list/display subcommands | Add a result/renderer boundary and normalize provider data. These are strong query candidates. |
| C: substantial refactor | `k8s-hpa-analyzer`; `pd-report`; `k8s-restart-resource.sh`; `aws-screen-monitor.sh`; `upkeep` | Data and progress are deeply interleaved, or the tool is a long-running/action workflow. Migrate only around a concrete automation need. |
| D: little or inappropriate value | `aws-env`; `ghrel`; `ssm-connect`; `join-call`; `netbird-up`; `saml2aws-op`; `ssm-parameter`; `mix-audio`; `nerdfont-install`; `op-clip`; `tmux-exec`; `tssh`; `vmrss`; `netinfo`; Terraform/Git/Chef/Kubernetes shell state helpers | Keep human/interactive behavior. Add a structured completion result only when a consumer need is clear. |
| D: file/document output is the product | `merge_zsh_history`; `terraform.plan.save`; `terraform.state.show.save`; PagerDuty Markdown/report-file paths | Keep their domain-specific file formats. Do not conflate a saved artifact format with stdout JSON. |

`aws-token-timeout` could be a B candidate if it becomes a reusable check;
today it is a small legacy script with stdout error paths and weak separation
between parsing and display. `ssh-sc` has useful structured key records, but
most subcommands mutate keys, the agent, or known_hosts, so only `list-keys`
is an obvious future query mode.

## 6. Initial migration candidates

1. **`httpkit`** — tests the contract against an existing `--json` interface,
   multiple subcommands, redirect lists, HTTP failures, and a rich renderer.
   First work should confirm exact shapes and move all diagnostics away from
   stdout; it should not add YAML/JSONL by default.
2. **`aws-ec2 list` and `describe`** — tests AWS SDK collection, dates and
   Decimals, empty results, normalized versus raw fields, and compatibility
   with the existing `--format json|yaml` describe path. It also provides a
   direct Nushell/`jq` use case.
3. **`aws-eks list` and `describe`** — tests a related command family and
   verifies that the same external behavior can be achieved without forcing a
   shared Python implementation. `kubeconfig` should remain an action path.
4. **`netbird-status`** — tests the preferred upstream boundary: JSON in from
   `netbird`, typed/normalized data internally, and human summary/detail out.
   It also exposes the question of whether raw provider fields belong in the
   public schema.
5. **`k8s-hpa-analyzer`** — tests the substantial case: typed Kubernetes
   objects, computed health information, optional interactive selection, and
   large Rich output. Add a non-interactive JSON path for `--hpa`/`--all-hpas`
   first; leave the prompt-driven path human-only.

This set exercises simple query, AWS, upstream JSON, Kubernetes, and rich
presentation without making a broad migration commitment.

## 7. Shared code opportunities

Start with documentation and tests, then extract only proven repetition.

Useful small shared concepts are:

- a per-command output mode enum: human, JSON, JSONL;
- one stream rule: data writer on stdout, diagnostic console/logger on stderr;
- JSON serialization tests that assert parseability and absence of ANSI/Rich
  markup;
- a result classification used by the process boundary: success, negative
  check, usage/configuration, operational failure;
- fixture-based tests for upstream JSON normalization.

Python can keep these helpers local until several scripts genuinely share
behavior. Go can add a small root `internal/output` package after the first
two non-TUI Go commands need it. Bash should use local conventions and `jq`
rather than a large sourced framework. Cross-language parity belongs in a
contract test matrix, not in one implementation library.

## 8. Risks and compatibility controls

- **Existing `--format` meanings:** `pd-report --output` is file-oriented,
  while AWS `--format` is stdout-oriented. Preserve both and document the
  difference; do not rename flags in the pilot.
- **Human output changes:** keep default tables, panels, colors, and prompts
  stable unless a command must split its collector from its renderer.
- **Stdout-sensitive workflows:** `aws-env set/profile/region` intentionally
  prints shell `export` statements to stdout for `eval`. Never apply a generic
  JSON or diagnostic policy to those paths.
- **Exit-code drift:** changing “not found” or “unhealthy” from 1 to 0/1/3
  can affect monitoring. Introduce distinctions only with docs and tests.
- **Provider schema drift:** raw AWS, Kubernetes, NetBird, and PagerDuty
  payloads are large and provider-owned. Prefer a deliberately documented
  normalized schema, with raw mode only when there is a clear use case.
- **Progress and buffering:** spinners, pagers, Textual, Bubble Tea, and
  subprocess output can deadlock or contaminate JSON if not isolated. Use
  captured subprocess streams and stderr diagnostics in machine mode.
- **Secrets:** AWS, PagerDuty, SSH, SAML, and 1Password paths can expose
  credentials or sensitive URLs. Structured output needs explicit redaction
  review, not just `json.dumps`.
- **Partial results:** network/API failures after some records are collected
  must not produce a successful-looking partial JSON document unless the
  command explicitly defines partial-result semantics.
- **Testing environments:** live AWS/Kubernetes/PagerDuty checks are not
  suitable as the only validation. Add pure fixture tests for renderers and
  use live checks only as supplemental verification.

## 9. Proposed phases

### Phase 1 — approve the contract

Decide the success root-shape rule, exit-code distinction, whether `--json` is
the preferred spelling everywhere, and which existing format flags remain
supported. Record the contract in `docs/tool-authoring.md` and the Go CLI
conventions.

### Phase 2 — establish testable boundaries

Add no broad behavior changes. Define per-command collector/result/renderer
interfaces in the pilot commands. Add tests for strict stdout, stderr
diagnostics, valid JSON, empty results, and exit status. Keep shared helpers
command-local until duplication is demonstrated.

### Phase 3 — migrate the pilots

Migrate `httpkit`, AWS EC2/EKS query paths, `netbird-status`, and the
non-interactive HPA path. Update each command guide and add a dated changelog
entry for user-visible contract changes. Validate from Bash, `jq`, Python,
and Nushell where available.

### Phase 4 — evaluate the contract

Review schema stability, error handling, check semantics, performance, and
whether JSONL was actually needed. Decide whether a shared Python or Go helper
has earned its maintenance cost. Do not add JSONL until a real large/streaming
consumer exists.

### Phase 5 — incremental migration

Prioritize B-category query commands and selected C-category tools when a
concrete automation need appears. Leave D-category interactive/action tools
alone. For every migration, preserve the default human path, add docs/tests,
and state whether zero records, not-found, unhealthy, and provider failure
have distinct outcomes.

## 10. Open questions

1. Should the public contract use raw natural roots (`[]`/object) everywhere,
   or is there a specific need for a common success envelope with metadata?
2. Is `--json` the only new spelling, with `--format json` retained only as a
   compatibility alias, or should a future `--output json` be canonical?
3. Should code 3 become mandatory for provider/dependency failures, or should
   the first version document only 0/1/2 and defer the distinction?
4. For check commands, which cases are “negative result” (code 1) versus
   “item not found” or “no data” (code 0)? This needs command-specific policy.
5. Should normalized JSON schemas include execution context such as profile,
   region, namespace, and source timestamps by default?
6. Is a `--raw` escape hatch desirable for provider payloads, or would stable
   normalized data plus direct upstream CLI access be safer?
7. Which commands, if any, need JSON error objects for CI? The initial design
   intentionally leaves errors on stderr.
8. Is there a concrete streaming workload that justifies JSONL in the first
   year? If not, defer it and keep the contract smaller.

## Audit references

The audit was based on the current repository, including:

- all command sources under `scripts/` and `cmd/`;
- Bash/zsh/Nushell modules under `shell/`;
- `README.md`, `CONTEXT.md`, `docs/tool-authoring.md`, `docs/go-cli.md`, and
  per-command documentation;
- current JSON/format/renderer/subprocess/exit paths identified in the source.

No code, command behavior, or existing human output was changed as part of this
audit.
