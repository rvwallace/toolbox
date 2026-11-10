# Toolbox AWS Architecture Discovery

**Status:** Planning reference; EC2 structured-output v1 implemented; broader AWS migration remains planning-only  
**Date:** 2026-09-27  
**Scope:** AWS inventory, architecture boundaries, language assessment, and future migration planning. The approved `aws-ec2` structured-output v1 contract is now implemented; unrelated AWS migrations remain planning-only.

## Executive summary

Toolbox has several AWS surfaces with different responsibilities rather than one AWS implementation:

    shell startup / Nushell helpers
            |
            +--> environment mutation and selection --> aws-env
            +--> direct provider queries ------------> AWS CLI / boto3
            +--> interactive actions ----------------> SSM / SAML / EKS / EC2

The strongest existing boundary is aws-env: the standalone Go command owns
profile/region selection and token inspection, while shell functions apply
environment changes or provide completions. The same pattern should be
considered for reusable query behavior, but not applied mechanically to every
shell function or TUI.

Key findings:

- aws-ec2, aws-eks, and aws-find-ip are Python/boto3 query tools and are the
  clearest structured-output candidates.
- ssm-connect is a Go TUI that preserves AWS CLI JSON at its data boundary, but
  overlaps substantially with the older Python/Textual ssm-pyconnect.py.
  The Go `ssm-connect` TUI is the intended successor to the Python implementation; the TUI path should remain interactive, and retirement validation should precede any removal.
- aws-env deliberately emits shell exports on stdout for eval; this is a shell
  protocol, not an accidental violation of a JSON stdout contract.
- Account identity and token expiration are duplicated across shell helpers,
  aws-env, aws-token-timeout.py, and the SSM tools, with different sources,
  defaults, and failure semantics.
- aws-screen-monitor, saml2aws-op, ssm-parameter, and the SSM session tools are
  action or interactive workflows. They should not receive JSON only for
  uniformity.

The owner has now confirmed that `ssm-connect` supersedes the legacy Python
SSM TUI. The remaining planning questions are retirement dependencies,
portable EC2 query ownership, token semantics, and which AWS data schemas
should become stable public interfaces. No language change is justified by
this audit alone.

## 1. AWS tool map

Structured output describes current behavior, not a recommendation.

| Tool / module | Location | Language | Type | AWS interface | Human output | Structured output | Shell dependency |
|---|---|---|---|---|---|---|---|
| aws-env | cmd/aws-env/ | Go | interactive, query, shell integration | AWS CLI configure list-profiles; direct credentials parsing | Bubble Tea picker on stderr; status on stdout | Shell export lines on stdout; no JSON | Bash/zsh eval; Nushell parses exports |
| aws.caller_identity | shell/modules/aws.sh | Bash | query/helper | AWS CLI STS YAML | column -t table | None | AWS CLI, column, sourced shell |
| aws.env | shell/modules/aws.sh | Bash | shell integration, environment mutation | Delegates to aws-env; unsets variables for clear | Human status/help | Export protocol from aws-env | Bash/zsh, aws-env |
| AWS zsh helper | shell/modules/aws.zsh | zsh | completion, prompt check | Cached profile list; direct credentials parsing | Completion; prompt TTL variable | Scalar shell variable only | Interactive zsh, AWS CLI for cache refresh |
| AWS Bash completion | shell/modules/aws.bash | Bash | completion | Profile cache and hardcoded regions | Completion candidates | None | Interactive Bash |
| aws.env Nushell | shell/modules/aws.nu | Nushell | shell integration, environment mutation | Delegates to aws-env | Nushell messages and env changes | Parses export lines internally | Nushell, aws-env |
| Nushell aws.caller_identity | shell/modules/aws.nu | Nushell | query | AWS CLI STS JSON | None by default | Returns parsed Nushell record | Nushell, AWS CLI |
| Nushell aws.ec2 | shell/modules/aws.nu | Nushell | query/composition | AWS CLI EC2 JSON | Pipeline/table behavior | Normalized or raw records | Nushell, AWS CLI |
| Nushell aws.ec2-key | shell/modules/aws.nu | Nushell | query/local lookup | Uses aws.ec2, then local key search | Error/path messages | Returns a path scalar | Nushell, filesystem |
| aws-ec2 | scripts/aws/aws-ec2.py | Python/Typer | query, report, local lookup | boto3 EC2 | Rich tables/panels/status | describe --format json|yaml; list none | uv, boto3, AWS config |
| aws-eks | scripts/aws/aws-eks.py | Python/Typer | query, action | boto3 EKS; AWS CLI for kubeconfig | Rich table/status/instructions | describe --format json|yaml; list none | uv, boto3, AWS CLI |
| aws-find-ip | scripts/aws/aws-find-ip.py | Python/Typer | query/report | boto3 EC2 ENI and STS | Rich progress/panels | Normalized dicts internally; no mode | uv, boto3, AWS config |
| aws-token-timeout | scripts/aws/aws-token-timeout.py | Python/argparse | check/query | Direct credentials-file parsing | Duration or scalar lines | Plain scalar/line output | uv, credentials file |
| aws-screen-monitor | scripts/aws/aws-screen-monitor.sh | Bash | action/check/interactive monitor | AWS CLI EC2 status and screenshot | Full-screen image/status/notification | AWS data reduced to text; none | AWS CLI, terminal image tools, fzf optional |
| saml2aws-op | scripts/aws/saml2aws-op.py | Python/argparse | action/auth/interactive fallback | 1Password CLI and saml2aws login | Rich logs/prompts | None; returns provider status | uv, op, saml2aws |
| ssm-parameter | scripts/aws/ssm-parameter.sh | Bash | query/secret retrieval/selection | AWS CLI SSM | Selection/status/value | quiet is one plaintext value | AWS CLI, fzf for selection |
| ssm-pyconnect | scripts/aws/ssm-pyconnect.py | Python/Textual | interactive/TUI/session | boto3 EC2/SSM/STS; AWS CLI session | Textual TUI, log, session | JSON config/log; no result mode | uv, boto3, Textual, AWS CLI, plugin |
| ssm-connect | cmd/ssm-connect/ | Go/Bubble Tea | interactive/TUI/session | AWS CLI EC2/SSM JSON and session | Bubble Tea TUI and session | JSON input/cache; no result mode | Binary, AWS CLI, Session Manager plugin |
| Terraform AWS pass-through | shell/modules/terraform.sh | Bash | shell integration | Passes AWS env/config into Docker Terraform | Terraform output | Terraform owns output | Bash, Terraform, Docker |

Scope exclusions: ghrel uses GitHub credentials, not AWS. Kubernetes tools may
operate against EKS, but their provider boundary is Kubernetes/kubectl.
toolbox and Terraform AWS mounts are installation/pass-through concerns, not
AWS query commands.

## 2. Architecture diagram

    Users / CI / SSH / Nushell / Bash / zsh
       |                 |                 |
       v                 v                 v
    shell adapters     aws-env          query/action tools
    (env, completion)  (Go picker)      (Python, Bash, Go)
       |                 |                 |
       +-----------------+-----------------+
                         |
              AWS CLI or boto3
                 |       |       |
                 v       v       v
            AWS config  AWS APIs  SSM plugin
            credentials (STS/EC2/  interactive
            and env     EKS/SSM)
                         |
                    local state
             (caches, kubeconfig, key files)

This is not a proposal to make all AWS code one binary. Shell owns current
shell mutation and completion ergonomics. Standalone tools own reusable
provider queries or actions. Renderers should consume structured data rather
than become data collectors.

## 3. Detailed assessments

### aws-env — already correctly extracted

It selects profiles/regions, shows effective AWS variables, and inspects
SAML-style token expiration. Profile discovery calls AWS CLI configure
list-profiles; region selection uses a compiled display list; token status reads
x_security_token_expires from the credentials file.

set, profile, and region emit shell-safe exports to stdout. Bubble Tea uses
stderr, and failures use stderr. show and token-status are human stdout queries.
This is an intentional dual-stream interface.

Keep Go. A compiled selector is already used from multiple shells and owns the
interactive terminal lifecycle. Shell must continue to apply the exports because
a child process cannot mutate its parent shell.

### aws-ec2 — Python query boundary

It lists instances, describes one by ID/name, and finds a local private key
matching an EC2 key-pair name. Typer options and AWS_PROFILE, AWS_REGION, and
AWS_DEFAULT_REGION provide context; AWS_EC2_KEY_DIR controls local lookup.

All provider data comes from boto3. The script already normalizes dates,
Decimals, tags, platform values, IAM role names, and security groups.
find-key then crosses into local filesystem behavior.

Keep Python. boto3, Typer, and Rich are appropriate; no latency or binary need
justifies Go. Future work is collector/renderer separation and a strict
existing JSON branch, not a language change.

### aws-eks — Python query plus action

List and describe use boto3 EKS and normalize provider objects. kubeconfig runs
AWS eks update-kubeconfig and writes a local kubeconfig. Keep Python: this split
is understandable and AWS CLI is the correct interface for the action.
Structured output is valuable for list/describe, but little value exists for a
file/context mutation unless a completion record is needed.

### aws-find-ip — concurrent cross-profile query

It parses ~/.aws/config, excludes profiles ending in -do, and searches a
private IP across four hardcoded US regions using concurrent boto3 EC2 calls.
It enriches hits with STS account IDs and returns normalized dictionaries,
including an ISO timestamp for attachment time.

Keep Python. Concurrency and boto3 shaping are appropriate. Before output or
exit changes, decide whether inaccessible profile/region errors are
distinguishable from a confirmed no-hit result.

### aws-token-timeout — approved for future retirement

It only parses x_security_token_expires from a credentials file; it does not
call AWS or STS. It prints seconds, a duration, or a labelled line. Missing
file and parse errors currently use stdout and helper functions exit 1.

The owner has confirmed that user-facing token expiration/status ownership
should move toward `aws-env`. This script is therefore approved for future
retirement,
not a future Python foundation. Before retirement, preserve or replace any
documented direct invocation and decide whether its scalar output has a caller
outside the repository. The issue is semantics, not language: `aws-env`, this
script, the zsh prompt helper, and the legacy SSM TUI implement related expiry
logic differently.

### aws-screen-monitor — terminal-specific action monitor

It selects an EC2 instance, repeatedly captures console screenshots, reads
instance/system status, displays images, and sends desktop notifications. AWS
CLI query/output text values are reduced to tab-separated shell data.

Keep Bash. Terminal image protocols, tput, notifications, and AWS CLI
composition are the product. A future noninteractive readiness check should be
a separate command, not a JSON mode on this monitor.

### saml2aws-op — credential refresh action

It obtains username/password/TOTP from 1Password where possible, falls back to
prompts over SSH, runs saml2aws login, and may retry with a fresh OTP. It is an
authentication workflow, not a query. Keep Python for provider fallback and
subprocess orchestration. Do not serialize credentials or invent a JSON login
result.

### ssm-parameter — secret retrieval action/query

It caches parameter names, optionally selects with fzf, and retrieves a named
parameter with decryption. quiet emits exactly the plaintext value for shell
capture; normal mode prints context plus value. Names are cached, values are
not.

Keep Bash. Exact plaintext is a meaningful interface, and JSON metadata could
increase accidental secret persistence. Do not add JSON without a specific
consumer need for metadata such as version or ARN.

### ssm-pyconnect — superseded legacy TUI

The 1,985-line Textual tool loads config, migrates legacy config, caches EC2
instances as tab-separated text, fetches SSM metadata with boto3 pagination,
checks credentials through expiry plus STS, and invokes AWS CLI
ssm start-session. It also owns themes, filtering, rotating logs, and cache
repair.

The owner has confirmed that `ssm-connect` is its successor. Treat this script
as approved for future retirement. It overlaps with the Go TUI in EC2 discovery, SSM
metadata, cache TTL, profile/region inputs, and session startup. Its JSON
config/log support is not command structured output. Retirement still requires
checking the automatic installer, inventories, legacy configuration/cache
compatibility, and any external user workflows.

### ssm-connect — current Go TUI

It loads EC2 and SSM data through AWS CLI JSON, unmarshals typed Go structures,
handles SSM chunking/pagination fallback, stores a JSON cache envelope, and
hands stdin/stdout/stderr to AWS ssm start-session.

Keep Go. A compiled TUI, typed data, background loading, and terminal/session
lifecycle are concrete reasons. It should not gain JSON on its TUI path. Its
loaders are a possible future noninteractive query boundary only if approved.

## 4. Shell extraction opportunities

| Concept | Current locations | Classification | Assessment |
|---|---|---|---|
| Profile selection | aws-env; AWS shell cache; aws-find-ip parser | Already extracted; keep cache in shell | aws-env owns selection. -do exclusion is a different policy. |
| Region selection | regions.go; aws.sh; SSM resolution; find-IP list | Keep shell completion; document source of truth | Go and shell display lists duplicate data, but consumers differ. |
| Account identity | Bash/Nushell helpers; boto3 in find-IP and Python SSM TUI | Thin wrapper or direct calls | Display, enrichment, and validation are different purposes. |
| Token status | aws-env; aws-token-timeout; zsh prompt; Python SSM TUI | One documented concept, not yet shared code | Decide expiry metadata versus STS validation first. |
| Env setup/clear | Bash and Nushell aws.env | Keep in shell; thin wrapper around aws-env | Parent-shell mutation requires shell code. |
| EC2 query | aws-ec2; Nushell aws.ec2; both SSM TUIs; monitor | Keep standalone query plus shell consumer | Similar data but different shapes, caches, and interaction. |
| EC2 key lookup | aws-ec2 find-key; Nushell aws.ec2-key | Keep as consumer logic | Combines provider metadata with local file rules. |
| EKS kubeconfig | aws-eks kubeconfig | Already correctly extracted | Preserve AWS CLI action behavior. |
| SSM session | ssm-connect; ssm-pyconnect | Extracted, but overlapping | Resolve Go/Python ownership first. |
| SAML refresh | saml2aws-op | Keep standalone action | Secrets and prompts are not startup logic. |

The AWS shell module should remain lightweight. The zsh precmd token refresh
is prompt behavior, not a reason to add network calls to every shell start.

## 5. Duplication map

Profiles: aws-env and aws.sh both call AWS CLI configure list-profiles; the
shell path caches it for completion. aws-find-ip parses ~/.aws/config itself and
excludes -do profiles. These policies are not equivalent, so immediate sharing
could remove useful distinctions.

Regions: regions.go and aws.sh duplicate display data; aws-find-ip has a
separate four-region search list; SSM tools resolve region from flags,
environment, or AWS config. This is maintenance debt, but not evidence for a
cross-language library.

Account identity: Bash and Nushell call STS through AWS CLI; aws-find-ip calls
STS through boto3 and caches it per process; ssm-pyconnect calls STS for
validation; aws-env does not call STS for token status. The same concept serves
display, enrichment, and validation.

Token handling: aws-env, aws-token-timeout, and zsh parse
x_security_token_expires; they differ in profile defaults and file handling.
ssm-pyconnect parses expiry and also calls STS. saml2aws-op refreshes through
op/saml2aws. Decide whether the credentials-file field is a supported toolbox
contract before consolidating.

EC2/SSM discovery: aws-ec2 and Nushell aws.ec2 expose similar instance queries
through boto3 versus AWS CLI JSON. Both SSM TUIs duplicate EC2/SSM discovery
and caching; the Go version uses typed JSON and a JSON cache, while Python uses
boto3 and a tab-separated cache. The screen monitor is a specialized text
workflow. This is the main overlap, but not yet a reason for shared code.

## 6. Structured-output assessment

| Command/subcommand | Value | Why |
|---|---|---|
| aws-ec2 list / describe | High | Natural normalized instance records; describe already supports JSON/YAML; useful to Nushell and jq. |
| aws-ec2 find-key | Possibly useful | Path-only output already serves shell use; JSON metadata is optional. |
| aws-eks list / describe | High | Natural cluster records; existing describe formats can converge on strict JSON. |
| aws-eks kubeconfig | Little | Primary result is a file/context mutation. |
| aws-find-ip | High | Already constructs normalized multi-account/region dictionaries; decide no-hit semantics first. |
| aws-token-timeout | Transition-only | A check result could serve monitoring, but the command overlaps with aws-env and should not gain a new interface before retirement review. |
| aws-screen-monitor | Inappropriate | Full-screen image monitoring and notification are the product. |
| saml2aws-op | Inappropriate | Authentication action with secrets and prompts. |
| aws-env set/profile/region | Inappropriate for JSON | Stdout is an executable export protocol. |
| aws-env show/token-status | Possibly useful | Query/check consumers may benefit, but human masking remains valuable. |
| ssm-connect / ssm-pyconnect TUI | Inappropriate on TUI path | A separate inventory mode could be useful, but the Go TUI is the intended successor and the Python implementation is approved for future retirement. |
| ssm-parameter | Little | Exact plaintext quiet output is intentional and safer than a metadata envelope. |

For high-value query paths, preserve AWS CLI JSON or boto3 objects into
normalized records. Do not convert structured data to human text and parse it
again.

## 7. Exit semantics

No exit codes are changed by this document.

For normal AWS queries/actions, the future baseline is:

    0  operation succeeded
    1  runtime/provider operation failed
    2  invalid usage or configuration

For explicit checks:

    0  condition passed
    1  condition failed after the check ran
    2  invalid usage or configuration
    3  check could not be performed

Empty aws-ec2 list is normally code 0 with an empty collection; it is not an
unhealthy system. aws-find-ip is a query, not a health check, so its current
no-hit code 1 should not be reinterpreted without an explicit decision.
Expired token metadata could be code 1 for aws-env token-status; missing or
unparsable credentials may be code 3 or 2 depending on policy. SSM availability
inside a TUI is not a command exit condition.

Current behavior differs: most Python commands use 1 for all failures;
aws-env uses 1 for invocation, picker abort, token lookup failure, and
expired token; aws-token-timeout prints errors to stdout and exits 1;
aws-find-ip uses 1 for no hit. These differences must be documented before
migration.

## 8. Language assessment summary

| Tool | Decision | Concrete reason |
|---|---|---|
| aws-env | Keep Go | Compiled interactive selector and explicit shell boundary. |
| aws-ec2, aws-eks, aws-find-ip | Keep Python | boto3, data shaping, concurrency, Typer/Rich; no binary or latency need. |
| aws-token-timeout | Approved for future retirement | `aws-env` is the intended user-facing token-status owner; direct callers must be checked first. |
| aws-screen-monitor | Keep Bash | Terminal/notification/AWS CLI composition is the core purpose. |
| saml2aws-op | Keep Python | Credential-provider fallback and subprocess orchestration. |
| ssm-parameter | Keep Bash | Small CLI composition and exact secret-value stdout. |
| ssm-pyconnect | Approved for future retirement | Owner-confirmed successor is `ssm-connect`; first remove dependency ambiguity. |
| ssm-connect | Keep Go | Compiled TUI, typed data, background loading, session lifecycle. |
| AWS shell modules | Keep shell/Nushell | Current-shell mutation and completion are inherently shell responsibilities. |

No tool meets the threshold for a language change in this planning phase.
Any future proposal should state current language, proposed language, reason,
benefit, cost, and migration risk; repository uniformity alone is not a reason.

## 9. Proposed future migration order

1. Document the confirmed SSM ownership: `ssm-connect` is the interactive
   successor; inventory retirement dependencies before deleting the Python TUI.
2. Document aws-env as the reference boundary: selection/query in the command,
   environment mutation in thin shell wrappers.
3. Clarify EC2 query ownership across aws-ec2, Nushell aws.ec2, the SSM loaders,
   and the screen monitor.
4. Pilot query output later with aws-ec2 list/describe, aws-eks list/describe,
   and aws-find-ip; these already own normalized records.
5. Resolve token semantics across aws-env token-status, aws-token-timeout, zsh
   TTL, and SSM validation before sharing behavior.
6. Leave saml2aws-op, ssm-parameter, aws-screen-monitor, and EKS kubeconfig
   unchanged without a concrete automation need.
7. Reassess SSM after ownership. A future noninteractive inventory mode is a
   separate design decision, not JSON added to the TUI path.

## 10. Shared-code boundary

The repository's internal/ directory is for shared Go code used by Go
commands/tools. It is not a general toolbox-wide library location. No shared
package should be created during planning. If future Go commands demonstrate
genuinely identical behavior, a narrowly scoped Go package under internal/ may
eventually hold Go-only decoding or argument-construction logic. It must not
become a reason to move Python or shell tools under internal/.

Python and shell should remain language-idiomatic. Cross-language consistency
should normally be expressed through documented behavior and schemas, not a
shared runtime library.

## 11. Open decisions

1. What validation and user communication are required before retiring ssm-pyconnect, given that ssm-connect is the intended successor?
2. Should aws-env own token metadata status, or should it remain a
   shell/prompt-local concern?
3. Is x_security_token_expires a supported contract, and should token checks
   also call STS?
4. Should aws-find-ip retain its hardcoded regions and -do exclusion?
5. Which EC2 representation should become the future normalized public shape:
   Python aws-ec2, Go Instance, or a new documented schema?
6. Should Nushell aws.ec2 remain native or eventually consume a standalone
   toolbox query command?
7. Are duplicated region lists worth maintaining, or should selection use
   provider discovery?
8. Should aws-env show and token-status gain structured data while preserving
   human output and the export protocol?
9. Is there a real consumer for JSON from ssm-parameter, or is plaintext the
   permanent interface?
10. Which AWS failures should be code 1 versus 2 or 3 for future checks?

## Planning guardrail

> No AWS source code should be changed until this planning document has been
> reviewed and the migration decisions have been approved.
+

## 12. Confirmed consolidation decisions

This section supersedes earlier unresolved ownership questions where they conflict
with the owner-provided context.

### Component state matrix

| Component | Location / language | Responsibility | State | Future owner | Structured-output relevance | Notes |
|---|---|---|---|---|---|---|
| aws-env | cmd/aws-env, Go | Profile/region selection, environment query, token status | KEEP / EVOLVE | aws-env plus thin shell adapters | High for show/token-status; inappropriate for export subcommands | Export stdout is an intentional shell protocol. |
| aws-ec2 | scripts/aws/aws-ec2.py, Python | General EC2 list/describe and local key lookup | EVOLVE | aws-ec2 for portable EC2 queries | High for list/describe; possibly useful for find-key | Existing boto3 normalization is the right boundary. |
| aws-eks | scripts/aws/aws-eks.py, Python | EKS list/describe and kubeconfig action | EVOLVE | aws-eks | High for list/describe; little for kubeconfig | Keep query and local kubeconfig mutation distinct. |
| aws-find-ip | scripts/aws/aws-find-ip.py, Python | Specialized cross-profile/region ENI ownership search | KEEP / EVOLVE | aws-find-ip | High if partial-failure semantics are documented | The -do exclusion is intentional account policy. |
| aws-token-timeout | scripts/aws/aws-token-timeout.py, Python | Legacy credentials-file expiry display | RETIRE | aws-env for user-facing status | Possibly useful only during transition | No repository caller found; README/AGENTS inventory it. |
| aws-screen-monitor | scripts/aws/aws-screen-monitor.sh, Bash | EC2 console screenshot/reboot monitor | SPECIALIZED | This tool | Inappropriate as a general JSON query | Visual terminal monitoring is the product. |
| saml2aws-op | scripts/aws/saml2aws-op.py, Python | 1Password-backed SAML credential refresh | KEEP | saml2aws-op plus saml2aws | Inappropriate | Authentication and secret handling stay separate from aws-env. |
| ssm-parameter | scripts/aws/ssm-parameter.sh, Bash | Parameter selection and secret retrieval | SPECIALIZED | This tool | Little; plaintext quiet mode is intentional | Secret capture is not a generic AWS record query. |
| ssm-pyconnect | scripts/aws/ssm-pyconnect.py, Python/Textual | Superseded EC2/SSM TUI and session launcher | RETIRE | ssm-connect | Inappropriate on the TUI path | No active repository caller found; compatibility review remains. |
| ssm-connect | cmd/ssm-connect, Go/Bubble Tea | Discover SSM-capable instances, select, start session | KEEP | ssm-connect | Inappropriate on TUI path; separate inventory optional | It is the rewrite/successor, not a generic JSON command. |
| AWS Bash module | shell/modules/aws.sh/.bash, Bash | Current-shell mutation, caller identity, completion cache | KEEP / THIN | aws-env plus shell-native helpers | Caller identity may consume a portable query later | Parent-shell mutation and completion belong in shell. |
| AWS zsh module | shell/modules/aws.zsh, zsh | Completion and prompt TTL display | KEEP / THIN | aws-env for status; zsh for prompt | Prompt scalar is not command JSON | Keep prompt behavior local; avoid startup network calls. |
| AWS Nushell module | shell/modules/aws.nu, Nushell | Env mutation, STS/EC2 pipelines, key lookup | THIN with retained ergonomics | aws-env, aws-ec2, and Nushell wrappers | aws.ec2 is high-value consumer; env/key helpers remain native | Do not remove the module wholesale. |

### Target architecture

    authentication and refresh
      1Password -> saml2aws-op -> saml2aws
                                  |
                                  v
                         AWS credentials/config state

    environment and context
      aws-env -> profile/region selection, token metadata status
          |             |
          v             v
      Bash/zsh       Nushell
      eval/unset     load-env/wrappers

    portable provider queries
      aws-ec2 -> EC2 human output or JSON -> Nushell, jq, Python, CI
      aws-eks -> EKS human output or JSON
      aws-find-ip -> specialized cross-account/region result

    interactive access
      ssm-connect -> EC2/SSM discovery -> target selection -> start-session

    specialized workflows
      aws-screen-monitor -> console screenshots and readiness observation
      ssm-parameter -> plaintext secret retrieval
      aws-eks kubeconfig -> local kubeconfig mutation

This deliberately does not make every AWS capability one binary. It gives
authentication, credential state, environment integration, general queries,
specialized queries, interactive access, and specialized workflows distinct
owners.

## 13. Nushell ownership review

The complete AWS Nushell module contains four exported functions and one alias.

| Function | Purpose | AWS interface | Nushell-specific behavior | Portable domain behavior | Future classification | Potential portable owner |
|---|---|---|---|---|---|---|
| aws.env | Select profile/region, show status, clear variables | Delegates to aws-env | load-env, hide-env, completion, parent-shell mutation | Selection/status invocation | KEEP / THIN | aws-env for query/selection; Nushell remains mutation adapter |
| aws.caller_identity | Return current AWS identity | AWS CLI STS JSON | from json returns a Nushell record | STS identity query | THIN convenience | Future portable identity query, or direct AWS CLI wrapper |
| aws.ec2 | List/filter EC2 instances | AWS CLI EC2 JSON | Nushell options, records, where, flatten, pipeline return, raw mode | EC2 filtering and normalization | THIN | aws-ec2 as future portable owner |
| aws.ec2-key | Find local key for an instance | Indirectly uses aws.ec2, then filesystem | Nushell glob/path/pipeline operations | EC2 key lookup plus local matching | KEEP / THIN | aws-ec2 find-key for provider lookup; Nushell may retain path ergonomics |
| aws-ec2-nu alias | Compatibility alias | Calls aws.ec2 | Alias naming and pipeline ergonomics | None beyond underlying query | KEEP temporarily / THIN later | Decision after portable EC2 ownership |

aws.env should remain a real Nushell function because it mutates the current
Nushell environment. aws.ec2-key also has meaningful Nushell ergonomics:
filesystem globbing, path handling, and returning a path into a pipeline. It
does not need to disappear if provider lookup moves behind aws-ec2.

aws.ec2 is different. Its filters and record mapping are reusable AWS domain
behavior, and it predates the portable JSON contract. The target direction is:

    aws-ec2
       +--> human output
       +--> JSON
                |
                +--> Nushell from json
                +--> jq / Python / CI

This does not mean every internal EC2 call should shell out to aws-ec2.
ssm-connect, aws-find-ip, and aws-screen-monitor have distinct provider
requirements. The concern is the duplicate user-facing EC2 query surface, not
every EC2 API call.

aws.caller_identity is a thin query convenience. It may remain direct AWS CLI
composition because its implementation is tiny and Nushell's structured
pipeline is useful. Extraction is lower priority than aws.ec2.

## 14. EC2 ownership map

| Location | Why it queries EC2 | User-facing query or internal dependency | Future treatment |
|---|---|---|---|
| aws-ec2 list/describe | General instance inventory | User-facing query | Preferred portable general EC2 query candidate |
| aws-ec2 find-key | Resolve key name before local search | User-facing hybrid query | Keep subcommand; local path behavior remains explicit |
| Nushell aws.ec2 | Interactive/pipeline inventory | User-facing query | Thin consumer later; retain Nushell ergonomics during transition |
| Nushell aws.ec2-key | Resolve key name and find local key | User-facing hybrid query | May consume portable query; local path search remains native |
| aws-find-ip | Find ENI owner across profiles/regions | Specialized user-facing query | Keep independent; not an aws-ec2 wrapper |
| ssm-connect | Build selectable list and SSM availability | Internal dependency of TUI | Keep provider calls local to Go TUI |
| ssm-pyconnect | Same purpose as ssm-connect | Internal dependency of superseded TUI | Approved for future retirement; no future ownership |
| aws-screen-monitor | Select/verify target and observe reboot state | Internal dependency of monitor | Keep local to specialized workflow |

The future default for general user-facing EC2 inventory should be the
portable aws-ec2 surface with human and JSON renderers. This is not a mandate
that other tools invoke it as a subprocess. Internal provider calls are
appropriate where they reduce coupling or preserve an interactive workflow.

## 15. aws-find-ip policy and failure model

The profile exclusion is intentional. In the user's convention, a read-only
profile and its corresponding admin profile ending in -do refer to the same
account. Searching both duplicates work and can produce redundant matches.
The exclusion is policy, not arbitrary legacy behavior.

The four-region list is separate. It is concrete operational scope, not a
general AWS region discovery mechanism. It may fit the current US-focused
workflow, but it is not portable across all accounts or products. Future
options are to retain and document the fixed list, make the region set
configurable, discover regions behind an explicit allowlist, or accept a
targeted region input. No choice is made here; expansion affects latency,
rate limits, permissions, and confidence about regions not searched.

Current per-task provider failures are swallowed as no result. This can return
useful matches, but makes not-found indistinguishable from could-not-inspect.
A future result model should distinguish confirmed no match, inaccessible
profile/region, transient provider failure, and successful match. Partial
matches should remain usable, but the command should communicate whether the
search was complete.

## 16. Token ownership map

| Implementation | What it checks | Expiration source | STS call | Profile rules | Consumers / behavior | Future owner |
|---|---|---|---|---|---|---|
| aws-env token-status | Human token status and expired state | credentials file x_security_token_expires | No | Explicit profile, then SAML2AWS_PROFILE, AWS_SSO_PROFILE, AWS_PROFILE, default | Human status; expired exits 1 | aws-env |
| aws-token-timeout | Remaining time/scalar output | Credentials file key | No | Script-specific argparse/default handling | README-listed; no repository caller found | Retire after direct-use review |
| zsh prompt helper | Prompt TTL display | Credentials file key | No | SC_AWS_TOKEN_PROFILE, default techops | Sets SC_AWS_TOKEN_TTL; precmd cache interval | zsh prompt remains local temporarily |
| ssm-pyconnect | TUI credential/token display and invalidation | Credentials file key, auto-discovery/TOKEN_PROFILE | Yes, for validation | CLI profile plus config TOKEN_PROFILE | Status bar, cache clearing, warnings | Retire with TUI |
| ssm-connect | Current Go TUI AWS context and SSM availability | No user-facing token-expiry implementation | AWS CLI calls for EC2/SSM | Profile/region flags/env/config | TUI startup and session workflow | Keep TUI-specific validation |
| saml2aws-op | Credential refresh/authentication | Provider-managed credential creation | Indirectly through saml2aws | Alias and forwarded saml2aws args | Updates credentials file | Keep authentication owner |

Keep these separate: recorded expiration timestamp, calculated credential
TTL, metadata says expired, AWS accepts/rejects credential, refresh should be
attempted, and prompt display of remaining TTL.

aws-env owns user-facing token expiration/status. It does not own authentication
refresh, and ssm-connect does not become a token-status command. The zsh prompt
may retain local display parsing until its dependency is deliberately reviewed.

## 17. Retirement dependency analysis

### ssm-pyconnect

| Dependency area | Finding | Future retirement requirement |
|---|---|---|
| Direct callers | No repository shell function, alias, script, or wrapper found | Check external dotfiles, personal scripts, and user workflows |
| Shell callers | None in shell modules or init files | Confirm no machine-local invocation is documented elsewhere |
| Documentation | Self-documentation only; no dedicated docs page; general inventory in AGENTS/CONTEXT; not in README AWS table | Update inventories and legacy references only in approved retirement |
| Installer | No explicit entry; automatic script discovery exposes the script as ssm-pyconnect | Stop exposing it and remove stale symlink safely |
| Tests | No dedicated tests found | Validate successor workflows before deletion |
| Configuration | Reads/writes ssm-connect.config and ssm-connect.json; theme, log, cache TTL, token profile | Decide config transition and whether Go compatibility parsing remains |
| Cache/log state | Python uses tab-separated profile/region cache and ssm-connect.log; Go uses JSON cache paths | Do not delete user state automatically; document stale-state handling |
| Other dependencies | cmd/ssm-connect/config.go understands Python JSON CACHE_TTL shape | Preserve or intentionally retire compatibility only after review |
| Replacement | cmd/ssm-connect | Compare discovery, filtering, token display, cache refresh, session launch, config |
| Future migration | External-use audit, communication, successor validation, installer/inventory cleanup, then separate deletion | No removal now |

The evidence supports RETIRE architecturally, but not immediate deletion. The
main hidden-dependency risk is outside the repository: direct use after install.

### aws-token-timeout

| Dependency area | Finding | Future retirement requirement |
|---|---|---|
| Direct callers | No repository caller found | Check shell history, personal scripts, CI, external dotfiles |
| Shell callers | No direct AWS module call; zsh parsing is independent | Decide whether prompt behavior needs a replacement |
| Documentation | Listed in README and AGENTS; no dedicated guide | Update inventories and explain aws-env replacement |
| Installer | No explicit entry; automatic script discovery exposes it | Remove automatic exposure and stale symlink safely |
| Tests | No dedicated tests found | Validate aws-env semantics first |
| Config dependencies | Direct credentials-file parser; no toolbox config | Define supported profile/file semantics in aws-env |
| Replacement | aws-env token-status | Compare output, profile precedence, expiry parsing, exit behavior |
| Other dependencies | None found | Review external users because installed name is public |
| Future migration | Confirm coverage, communicate replacement, update docs/inventories, retire separately | No removal now |

## 18. Future migration phases

### Phase 1 — record confirmed ownership

Goal: make ssm-connect the documented successor and record the two legacy tools
as approved for future retirement without deleting them.
Affected tools: SSM TUI, token status, inventories and docs.
Dependencies: owner approval and external-use audit.
Risk: users may still invoke installed legacy names.
Validation: repository references, installer discovery, successor workflow review.

### Phase 2 — establish portable EC2 query ownership

Goal: define aws-ec2 as preferred general user-facing EC2 query while keeping
internal EC2 calls in specialized tools.
Affected tools: aws-ec2, Nushell aws.ec2, aws-find-ip, SSM histories, monitor.
Dependencies: stable field/schema and profile/region decisions.
Risk: Nushell users rely on current fields and filters.
Validation: compare current Nushell and Python records and workflows.

### Phase 3 — thin the Nushell EC2 domain layer

Goal: Nushell consumes portable query for general inventory while retaining
aws.env, aws.ec2-key path ergonomics, aliases, and pipelines.
Affected tools: shell/modules/aws.nu and aws-ec2.
Dependencies: Phase 2 schema and structured-output approval.
Risk: record shape, empty results, and error propagation change.
Validation: Bash/zsh/Nushell/SSH/CI examples and representative filters.

### Phase 4 — establish structured output for portable queries

Goal: add reviewed human/JSON renderer separation to aws-ec2, aws-eks, and
aws-find-ip.
Affected tools: Python query commands and docs.
Dependencies: general structured-output approval and partial-failure semantics.
Risk: stdout contamination, schema drift, changed no-hit behavior.
Validation: JSON parsing, stderr capture, empty/partial results, jq, Nushell,
Python, and CI-style pipelines.

### Phase 5 — resolve token dependencies

Goal: make aws-env the user-facing token-status owner while preserving the
difference between metadata expiry and actual AWS credential validity.
Affected tools: aws-env, aws-token-timeout, zsh helper, SSM history.
Dependencies: approved semantics and external-use audit.
Risk: prompt regressions and false confidence from metadata-only status.
Validation: expired, missing, ambiguous, long-lived, and STS-rejected fixtures.

### Phase 6 — retire superseded implementations

Goal: remove only approved legacy tools after callers and state compatibility
requirements are handled.
Affected tools: ssm-pyconnect, aws-token-timeout, installer, inventories, docs.
Dependencies: earlier phases, external-use confirmation, owner approval.
Risk: hidden personal workflows and stale symlinks/configuration.
Validation: fresh install inventory, stale-link sweep, successor workflows,
documentation consistency.

### Phase 7 — maintain specialized workflows

Goal: keep screen monitoring, SSM parameter retrieval, SAML refresh, and SSM
TUI behavior specialized unless a concrete need appears.
Affected tools: aws-screen-monitor, ssm-parameter, saml2aws-op, ssm-connect,
EKS kubeconfig.
Dependencies: a specific user or automation requirement.
Risk: artificial interfaces that weaken security or terminal ergonomics.
Validation: workflow-specific tests, not generic JSON tests.

## 19. Consolidation summary for review

1. Confirmed decisions: ssm-connect supersedes ssm-pyconnect; aws-env owns
   user-facing token status; saml2aws-op owns authentication/refresh;
   aws-screen-monitor remains specialized; shell owns parent-shell mutation;
   internal/ remains Go-only shared-code space.
2. Classifications: aws-env KEEP/EVOLVE; aws-ec2 and aws-eks EVOLVE;
   aws-find-ip KEEP/EVOLVE; Nushell aws.ec2 THIN; aws-token-timeout RETIRE;
   ssm-pyconnect RETIRE; ssm-connect KEEP; saml2aws-op KEEP. The two RETIRE
   states are approved for future retirement, subject to dependency validation;
   no deletion is approved in this phase.
   aws-screen-monitor and ssm-parameter SPECIALIZED; AWS shell modules
   KEEP/THIN according to function.
3. Retirement dependencies: no active repository callers, shell callers,
   dedicated tests, or dedicated docs were found for either candidate. Both
   are automatically exposed by script discovery and remain in README/AGENTS
   or legacy references. ssm-pyconnect also owns legacy config/cache/log
   state and a Python-shaped config compatibility path in Go.
4. AWS/Nushell ownership: retain env mutation, key-path ergonomics, aliases,
   and pipeline composition in Nushell. Move general EC2 domain querying
   toward aws-ec2's portable human/JSON boundary later; keep specialized
   internal EC2 calls local to their workflows.
5. Token ownership: aws-env owns user-facing metadata status; zsh may retain
   prompt display temporarily; SSM validation and saml2aws refresh are
   distinct; metadata expiry is not equivalent to STS acceptance.
6. Target architecture: authentication -> credentials/config -> aws-env
   context -> portable query commands -> Nushell/jq/Python/CI, with
   independent specialized workflows and an interactive ssm-connect boundary.
7. Remaining owner input: external-use confirmation for retirement, normalized
   EC2 schema, aws-find-ip region policy, token semantics/STS policy, and
   whether a separate noninteractive SSM inventory is wanted.

## Planning guardrail

No source code should be changed. No migration should begin. No RETIRE
candidate should be deleted. No command interface should be modified. No
structured-output flags should be added.

No AWS source code should be changed until this planning document has been
reviewed and the migration decisions have been approved.

## 20. AWS EC2 portable query contract

This section is the final planning pass for the future public structured-output
interface of `aws-ec2`. It defines a proposed contract only. It does not add
`--json`, change existing output, or begin the Nushell migration.

### 20.1 Current Python and Nushell interfaces

The two implementations overlap in purpose but do not currently expose the
same data model.

| Surface | Current operations and inputs | Current data behavior | Current compatibility behavior |
|---|---|---|---|
| Python `aws-ec2 list` | `--name`/`-n` Name-tag substring; `--state` exact EC2 state-name; global `--profile`/`-p` and `--region`/`-r` | Boto3 paginator returns provider instances; human table displays name, ID, state, type, OS, key, public IP, and private IP | Requires a profile from `--profile` or `AWS_PROFILE`, and a region from `--region`, `AWS_REGION`, or `AWS_DEFAULT_REGION`; no JSON mode; empty result prints a message and exits 0 |
| Python `aws-ec2 describe` | Positional ID or Name-tag substring; `--format`/`-f` table, json, yaml; global profile/region | ID uses `InstanceIds`; name uses a server-side `tag:Name` substring filter; table selects fields; json/yaml serializes the provider instance after generic normalization | No match and ambiguous name both print human diagnostics and exit 1; multiple name matches are not serialized; existing `--format json` is provider-shaped rather than the proposed normalized schema |
| Python `aws-ec2 find-key` | Positional ID or Name; `--keys-dir`/`AWS_EC2_KEY_DIR`; `--key-file-only` | Resolves an EC2 key pair, searches the local filesystem, and prints a human panel or shell-escaped path | The path-only form is already a useful scripting interface; missing key name or file exits 1 |
| Nushell `aws.ec2` | Optional positional filter; `--name`/`-n`; `--state`/`-s`; `--profile`/`-p`; `--region`/`-r`; `--raw` | Calls AWS CLI `describe-instances --output json`, parses JSON, and returns either raw provider records or mapped Nushell records | Optional profile and region are passed to AWS CLI; AWS CLI's normal credential and region resolution remains available; provider failure is printed to stderr but the function does not explicitly preserve the provider exit code |
| Nushell `aws.ec2-key` | Positional ID or Name; `--keys-dir`/`AWS_EC2_KEY_DIR`; profile and region | Calls `aws.ec2`, takes the first match, reads its key field, then performs Nushell glob/path matching | Returns a path scalar on success and diagnostics on stderr; local filesystem policy remains Nushell-specific |

Important current differences:

- Python list has no current structured result. Its provider records are used
  only to build a Rich table.
- Python describe's current JSON is not the same as a normalized toolbox
  record. `normalize()` preserves AWS field names and nesting, converts dates
  to ISO strings, and converts `Decimal` values to strings.
- Nushell's mapped record uses `name`, `id`, `state`, `type`, `os`, `key`,
  `public_ip`, `private_ip`, `launch_time`, and a tag record. Its `--raw`
  branch bypasses that mapping and returns AWS CLI records.
- Python list applies `--name` and `--state` as EC2 API filters. Nushell does
  the same for those options, but its positional filter is local: an instance
  ID is exact, while other input matches the name or an ID substring.
- Python `find-key` matches a non-ID Name tag exactly, case-insensitively, and
  chooses the first key name after sorting the set. Nushell's positional
  `aws.ec2` filter uses a Name substring and then takes the first returned
  record. These are not equivalent lookup semantics.
- Python explicitly requires profile and region resolution before the command
  runs. Nushell delegates optional context to AWS CLI, so its default
  credential-chain behavior is broader.

### 20.2 Field comparison and proposed public fields

The proposed schema is based on stable toolbox concepts, not on the complete
`describe-instances` response. Provider-specific fields remain available from
the AWS CLI for users who need them.

| Concept | Python current field/display | Nushell current field | AWS source | Type | Difference | Proposed public field |
|---|---|---|---|---|---|---|
| Instance identifier | `InstanceId` in table and normalized describe JSON | `id` | `InstanceId` | string | Different name | `instance_id` required |
| Name | `Name` tag through `instance_name()` | `name` from `Name` tag | `Tags[Key=Name].Value` | string or null | Python uses empty string when absent; Nushell defaults empty string | `name` nullable; absent tag is `null` |
| State | `State.Name` | `state` | `State.Name` | string | Same value, different field name | `state` required |
| Instance type | `InstanceType` | `type` | `InstanceType` | string | Different field name | `instance_type` required |
| OS/platform | `PlatformDetails` then `Platform`, or human `Unknown` | `os`, `PlatformDetails` then `Platform`, default `Linux/UNIX` | `PlatformDetails` / `Platform` | string or null | Different absent-value defaults and terminology | `os` nullable; use provider value, do not invent a default |
| Architecture | Present only in raw provider data, not human/mapped output | Present only in raw provider data | `Architecture` | string or null | Not currently normalized | `architecture` nullable; useful stable instance property |
| Image | Human table does not show it; describe table shows `ImageId` | Not in mapped record | `ImageId` | string or null | Python exposes it only in describe | `image_id` nullable |
| Availability zone | Describe table shows `Placement.AvailabilityZone` | Not in mapped record | `Placement.AvailabilityZone` | string or null | Python-only human field | `availability_zone` nullable |
| Key pair | `KeyName` in list/describe/find-key | `key` | `KeyName` | string or null | Different field name and absent-value defaults | `key_name` nullable |
| IAM role | Derived from `IamInstanceProfile.Arn` in describe table | Not in mapped record | `IamInstanceProfile.Arn` | string or null | Python derives only the final ARN component | `iam_role` nullable; expose role name only |
| Private IP | `PrivateIpAddress` | `private_ip` | `PrivateIpAddress` | string or null | Same concept | `private_ip` nullable |
| Public IP | `PublicIpAddress` | `public_ip` | `PublicIpAddress` | string or null | Same concept | `public_ip` nullable |
| Private DNS | `PrivateDnsName` in describe table | Not in mapped record | `PrivateDnsName` | string or null | Python-only human field | `private_dns_name` nullable |
| VPC | `VpcId` in describe table | Not in mapped record | `VpcId` | string or null | Python-only human field | `vpc_id` nullable |
| Subnet | `SubnetId` in describe table | Not in mapped record | `SubnetId` | string or null | Python-only human field | `subnet_id` nullable |
| Security groups | Human-only combined `name (id)` string | Not in mapped record | `SecurityGroups` | array of objects | Current human representation loses structure | `security_groups` array of `{id, name}` objects |
| Launch time | Stringified boto3 datetime in table; ISO string after `normalize()` in JSON | `launch_time` provider string | `LaunchTime` | RFC3339 string or null | Current formats depend on renderer/provider | `launch_time` nullable RFC3339 UTC string |
| Tags | Raw AWS list in describe JSON | `tags` record keyed by tag name | `Tags` | object of string values | Nushell is convenient; raw AWS list preserves entry shape | `tags` object with string values |

The public record deliberately does not include every AWS field. It excludes
reservation IDs, network-interface detail, block-device mappings, monitoring
state, placement metadata beyond availability zone, and the full IAM instance
profile object. Those are provider details rather than demonstrated general
toolbox concepts.

### 20.3 Implemented `aws-ec2 list --json`

The root is a JSON array. Each element is one normalized instance record. A
representative result is:

```json
[
  {
    "instance_id": "i-0123456789abcdef0",
    "name": "web-01",
    "state": "running",
    "instance_type": "t3.small",
    "os": "Linux/UNIX",
    "architecture": "x86_64",
    "image_id": "ami-0123456789abcdef0",
    "availability_zone": "us-east-1a",
    "key_name": "prod-web",
    "iam_role": "WebInstanceRole",
    "private_ip": "10.0.12.34",
    "private_dns_name": "ip-10-0-12-34.ec2.internal",
    "public_ip": "203.0.113.42",
    "vpc_id": "vpc-0123456789abcdef0",
    "subnet_id": "subnet-0123456789abcdef0",
    "security_groups": [
      {
        "id": "sg-0123456789abcdef0",
        "name": "web"
      }
    ],
    "launch_time": "2026-09-27T14:32:11Z",
    "tags": {
      "Name": "web-01",
      "Environment": "prod"
    }
  }
]
```

Field rules:

| Field | JSON type | Required or nullable | Normalization and stability rule |
|---|---|---|---|
| `instance_id` | string | required | Copy `InstanceId`; stable EC2 identifier |
| `name` | string or null | nullable | Promote the `Name` tag; preserve the tag separately; use `null` when absent |
| `state` | string | required | Copy `State.Name`, such as `running` or `stopped` |
| `instance_type` | string | required | Copy `InstanceType` |
| `os` | string or null | nullable | Prefer `PlatformDetails`, then `Platform`; no synthetic `Linux/UNIX` default when the provider omits both |
| `architecture` | string or null | nullable | Copy `Architecture` when returned |
| `image_id` | string or null | nullable | Copy `ImageId` |
| `availability_zone` | string or null | nullable | Copy `Placement.AvailabilityZone` |
| `key_name` | string or null | nullable | Copy `KeyName`; null when no key pair is assigned |
| `iam_role` | string or null | nullable | Extract the role/profile name after the final `/` in the instance-profile ARN; null when absent |
| `private_ip` | string or null | nullable | Copy `PrivateIpAddress` |
| `private_dns_name` | string or null | nullable | Copy `PrivateDnsName` |
| `public_ip` | string or null | nullable | Copy `PublicIpAddress` |
| `vpc_id` | string or null | nullable | Copy `VpcId` |
| `subnet_id` | string or null | nullable | Copy `SubnetId` |
| `security_groups` | array of objects | required | Empty array when absent; each object has string `id` and `name`, with null only if the provider omits that member |
| `launch_time` | string or null | nullable | Convert the provider timestamp to UTC RFC3339 with `Z`; do not humanize it |
| `tags` | object of string values | required | Map unique AWS tag keys to values; empty object when no tags exist |

AWS tag keys are unique within an EC2 resource, so an object is the most useful
contract for Nushell, jq, and Python. It supports direct access such as
`.tags.Environment` and preserves the AWS key names. A tag list would preserve
the wire representation but add iteration for the common lookup case. The
promoted `name` field remains because it is the primary human identity and a
common filter.

### 20.4 Context fields

The v1 record should include `availability_zone` because it is an intrinsic
instance placement property. It should not include `profile`, `region`, or
`account_id` in every record:

| Context | Decision | Reason |
|---|---|---|
| `availability_zone` | Include in each record | It describes where the instance is placed and is already shown by Python `describe`. |
| `profile` | Exclude from each record; defer multi-context metadata | It is an invocation context, not an instance property; repeating it adds little for a single profile/region query. |
| `region` | Exclude from each record; defer multi-context metadata | The command already queries one selected region, and the region is available to the caller. A later cross-region command could define its own result model. |
| `account_id` | Exclude from each record; defer | Obtaining it requires an additional STS call and permission. It is not needed for the current single-context query and should not be added for convenience alone. |

If a future command combines multiple profiles or regions, it should define a
deliberate multi-context result contract rather than silently changing this
single-context record.

### 20.5 Implemented `aws-ec2 describe --json`

`describe` should return one normalized JSON object for one resolved instance,
not a one-element array. Its success shape is therefore:

```json
{
  "instance_id": "i-0123456789abcdef0",
  "name": "web-01",
  "state": "running",
  "instance_type": "t3.small",
  "os": "Linux/UNIX",
  "architecture": "x86_64",
  "image_id": "ami-0123456789abcdef0",
  "availability_zone": "us-east-1a",
  "key_name": "prod-web",
  "iam_role": "WebInstanceRole",
  "private_ip": "10.0.12.34",
  "private_dns_name": "ip-10-0-12-34.ec2.internal",
  "public_ip": "203.0.113.42",
  "vpc_id": "vpc-0123456789abcdef0",
  "subnet_id": "subnet-0123456789abcdef0",
  "security_groups": [],
  "launch_time": "2026-09-27T14:32:11Z",
  "tags": {
    "Name": "web-01"
  }
}
```

Resolution and failure rules for the future JSON mode:

| Situation | Result | stdout | stderr | Exit |
|---|---|---|---|---:|
| ID resolves to one instance | Success | One JSON object and newline | No diagnostics | 0 |
| Name substring resolves to one instance | Success | One JSON object and newline | No diagnostics | 0 |
| No name/ID match | Query completed without a target | No JSON value | Diagnostic identifying the target | 1 |
| Multiple name matches | Ambiguous query | No JSON value | Diagnostic plus candidate summary if useful | 1 |
| Stopped instance | Success if returned by EC2 | One object with `state: "stopped"` | No diagnostics | 0 |
| Terminated instance returned by provider | Success if uniquely resolved | One object with its returned state | No diagnostics | 0 |
| Invalid profile or credentials | Query failed | No JSON value | Provider diagnostic | 1 |
| Invalid region or inaccessible region | Query failed | No JSON value | Provider diagnostic | 1 |
| Malformed or unusable provider response | Query failed | No JSON value | Diagnostic | 1 |
| Invalid invocation | Usage/configuration failure | No JSON value | Usage diagnostic | 2 |

The current human behavior remains unchanged: no match and ambiguous name
print human diagnostics and exit 1, and table mode continues to show its
summary. The future machine mode must not print that summary to stdout.

The existing `--format json` and `--format yaml` options should remain
compatible during the first implementation. They currently serialize the
provider-shaped `describe` object and are documented in `docs/aws-ec2.md`.
The proposed `--json` mode should be the canonical normalized contract, not a
silent shape change to existing `--format json` consumers. A later, separately
approved compatibility decision can determine whether the legacy format mode
becomes an alias or remains a legacy representation.

### 20.6 Empty results and exit semantics

`aws-ec2 list --json` with no matching instances returns exactly:

```json
[]
```

followed by a newline and exits 0. This is a successful query with zero
results, not a failed health check. Provider failures, invalid context, and
invalid invocation remain distinct from an empty collection.

The list command should use its existing `--name` and `--state` filters in the
future JSON mode. No additional `--json`-specific filter language is needed.
Consumers can apply downstream filtering:

```bash
aws-ec2 list --json | jq '.[] | select(.state == "running")'
```

```nu
aws-ec2 list --json
| from json
| where state == "running"
| select name instance_id private_ip
```

### 20.7 Filter decisions

| Filter or capability | Decision | Reason |
|---|---|---|
| Name substring | Keep | Existing Python and Nushell workflows use it and EC2 can perform the filter efficiently. |
| State | Keep | Existing list option and EC2 server-side state filter. |
| Instance ID lookup | Keep for `describe`; do not add a new list flag now | Existing describe behavior is clear; a list result can be filtered by consumers. |
| Private/public IP filter | Leave to jq/Nushell initially | Not exposed by the current Python list interface; a stable record makes client-side filtering straightforward. |
| Instance type filter | Leave to jq/Nushell initially | No current workflow demonstrates a need for another provider filter. |
| Arbitrary tag filter | Leave to jq/Nushell initially | The returned tag object is useful for composition; adding a tag expression language would duplicate downstream query behavior. |
| Positional list filter | Do not add | Nushell has one, but it combines name and partial-ID behavior inconsistently with Python. Keep positional resolution on `describe`. |

The future command should not attempt to reproduce Nushell's entire query
language or jq. Provider-side filters are justified when they already exist or
reduce a large response; general record selection belongs downstream.

### 20.8 Nushell migration examples

Current Nushell behavior:

```nu
aws.ec2 --state running
| where os =~ "Linux"
| select name id private_ip
```

The future portable query equivalent is:

```nu
aws-ec2 list --state running --json
| from json
| where os =~ "Linux"
| select name instance_id private_ip
```

Current positional lookup:

```nu
aws.ec2 web-01
```

Future exact-instance selection should be explicit through `describe` when
one object is wanted, or through `list --name web-01 --json` when a collection
is wanted. Nushell can retain convenience wrappers that translate the result
to local conventions such as `id` and `key` if that is important for existing
pipelines.

`aws.env` remains a Nushell environment mutation function. `aws.ec2-key`
remains a candidate for a thin wrapper because its globbing, path handling,
and path-scalar return are genuine Nushell ergonomics. It should not force the
portable query schema to expose local filesystem results.

### 20.9 `find-key` boundary

`find-key` should remain primarily a human/path command. Its useful machine
interface is already `--key-file-only`: successful stdout is one shell-escaped
path, and failure exits nonzero. A JSON object would add little for the common
workflow and could make accidental key-path capture less obvious.

Its responsibilities should remain conceptually separate:

1. provider lookup resolves an instance identifier or Name tag to a key-pair
   name;
2. local policy searches `AWS_EC2_KEY_DIR` for matching `.pem`/`.key` files;
3. the command returns a path or human explanation.

The Python and Nushell lookup semantics should be reviewed during a future
implementation, because Python uses exact case-insensitive Name matching for
this path while Nushell uses a substring-based `aws.ec2` lookup. That is a
compatibility question, not a reason to add JSON now. Nushell may retain its
local path/glob implementation even if the provider lookup later consumes
`aws-ec2` output.

### 20.10 Raw provider data

Do not add a new `--raw` or `--raw-json` mode to the portable command in this
pass. The normalized schema is the public contract. Users who need arbitrary
EC2 provider data can call `aws ec2 describe-instances --output json` directly,
and the current Nushell `--raw` behavior can remain a compatibility aid until
the wrapper is deliberately thinned.

The existing `aws-ec2 describe --format json` is a compatibility concern, not
a recommended raw-mode design. It should be documented as the legacy
provider-shaped representation while the new canonical mode is reviewed.

### 20.11 Implemented `aws-ec2` boundary

The first implementation should remain local to `scripts/aws/aws-ec2.py` and
should not create shared Python infrastructure:

```text
EC2 client and collection
        |
        v
normalized instance record(s)
        |
        +--> existing human table/panel renderer
        +--> existing --format json/yaml compatibility renderer
        +--> new canonical --json renderer
```

Collectors should not print, create Rich tables, or decide stdout/stderr
policy. Renderers should not call boto3. The normalization function should
own null handling, tag mapping, security-group objects, IAM role extraction,
and UTC timestamp conversion. The existing human renderer should preserve its
current columns and messages unless a separate compatibility decision approves
otherwise.

### 20.12 Compatibility and installer surface

The future implementation must account for:

- current human `list`, `describe`, and `find-key` output;
- existing `describe --format json` and `--format yaml` consumers;
- `docs/aws-ec2.md` examples and README command listings;
- the Nushell `aws.ec2`, `aws.ec2-key`, and `aws-ec2-nu` interfaces;
- the `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`, and
  `AWS_EC2_KEY_DIR` environment variables;
- the installer's automatic discovery of `scripts/aws/aws-ec2.py` as the
  `aws-ec2` executable;
- the difference between Python's required profile/region resolution and AWS
  CLI's broader default resolution in Nushell;
- callers that use command substitution or parse the existing path-only
  `find-key --key-file-only` result.

No repository tests currently cover `aws-ec2`. The README, `docs/aws-ec2.md`,
AGENTS inventory, CONTEXT inventory, changelog entry for the Nushell module,
and shell module are the current documented or compatibility surface found in
the repository.

### 20.13 `aws-ec2` contract test matrix

Tests should be added only with the later implementation. The planned matrix
is:

| Area | Required cases |
|---|---|
| Human mode | Existing list columns, describe table fields, no JSON leakage, existing `--format json`/`yaml` behavior preserved |
| JSON framing | Exactly one valid JSON value on stdout, trailing newline, no ANSI, Rich markup, progress, warnings, or banners |
| JSON diagnostics | Provider and diagnostic output only on stderr; stdout remains empty on failure |
| List data | Running and stopped instances; missing optional fields; tags; security groups; IAM role; RFC3339 launch time; empty `[]` |
| Describe data | ID match; unique name match; no match; multiple name matches; terminated record if provider returns it |
| Context failures | Invalid profile, invalid region, authentication failure, provider response failure, and invalid invocation with the planned exit distinctions |
| Filter behavior | Name substring and state filters match current provider-side behavior |
| Consumer compatibility | `jq`, Nushell `from json`, Python `json.loads`, and command substitution on successful JSON output |
| Key lookup | Existing path-only success/failure behavior, local search, missing key name, and no forced JSON interface |

Fixtures should exercise null/absent values rather than relying only on a
fully populated instance. Provider calls should be isolated behind the local
collector boundary so renderer tests do not require AWS credentials.

### 20.14 Implemented public contract

```text
AWS-EC2 STRUCTURED OUTPUT v1

aws-ec2 list --json
    stdout: one JSON array of normalized instance records plus newline
    empty: []
    success: exit 0
    filters: existing --name and --state semantics

aws-ec2 describe TARGET --json
    stdout: one normalized JSON object plus newline
    no match or ambiguous name: no JSON stdout, diagnostic on stderr, exit 1
    provider/runtime failure: no JSON stdout, diagnostic on stderr, exit 1
    invalid invocation: diagnostic on stderr, exit 2

record fields:
    instance_id, name, state, instance_type, os, architecture, image_id,
    availability_zone, key_name, iam_role, private_ip, private_dns_name,
    public_ip, vpc_id, subnet_id, security_groups, launch_time, tags

JSON rules:
    lower_snake_case names
    typed values
    null for absent optional scalar fields
    empty arrays/objects for absent collection fields
    RFC3339 UTC timestamps
    normalized tags and security groups
    no ANSI, Rich markup, progress, or humanized timestamps

context:
    availability_zone is included
    profile, region, and account_id are excluded from each v1 record

find-key:
    remain a path-oriented command; --key-file-only remains plain path output
    with no required JSON mode

compatibility:
    human output unchanged
    existing --format json and --format yaml preserved initially
    --format json remains the legacy provider-shaped representation until a
    separate compatibility decision changes it
```

Open owner decisions for implementation are limited to approving this field
set, deciding whether canonical `--json` should coexist indefinitely with the
legacy `--format json`, and deciding whether `os` should remain the public name
or be renamed to a more provider-specific concept such as `platform`. The
remaining implementation details are renderer and fixture work, not schema
invention.

### 20.15 Standing shell compatibility constraint

Portable toolbox commands must remain usable without Nushell. When a command
is consumed by shell modules, the supported integration surface includes
Bash, zsh, and Nushell unless an intentional limitation is documented.

The preferred boundary is:

```text
portable toolbox command
        |
        +--> Bash adapter
        +--> zsh adapter
        +--> Nushell adapter
```

Nushell may provide richer records, pipelines, `load-env`, and path
operations, but it must consume portable command behavior rather than become
the only implementation of reusable AWS logic. Environment mutation remains
shell-owned because a child process cannot modify its parent shell.

For the future EC2 implementation specifically:

1. Change and validate the portable Python `aws-ec2` command first.
2. Do not change `shell/modules/aws.nu` in that implementation pass.
3. Verify `aws-ec2 --json` directly, without any shell module.
4. Migrate Nushell in a separate change after the record contract is stable.
5. During that migration, inspect Bash and zsh counterparts and determine
   whether equivalent adapters need changes.
6. Do not make Bash, zsh, or Nushell depend on another shell's configuration.

Future shell/module migrations must explicitly validate direct command use,
Bash, zsh, Nushell, and remote or minimal-shell use where relevant. Shell
implementations may remain intentionally different when they provide
shell-native ergonomics, but the underlying portable capability must remain
available outside Nushell.

## Final EC2 planning guardrail

No source code should be changed. No command interface should be modified. No
JSON flag should be added. No Nushell migration should begin. No tests should
be implemented. This EC2 contract and implementation plan must be reviewed
and approved before coding begins.
