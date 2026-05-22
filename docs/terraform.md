# Terraform shell module

Toolbox stem: `terraform` (`shell/modules/terraform.sh`, plus `terraform.zsh` / `terraform.bash` for interactive hooks).

Daily work uses the host `terraform` binary on `PATH` (typically via `tfswitch`). **`tf.amd64`** is a special-case Docker runner for linux/amd64 on Apple Silicon only; plan-save helpers do not use it.

## MR workflow

Attach a human-readable plan when opening a GitLab MR:

```bash
export TICKET=TCM-1060
cd path/to/terraform/stack
tf.plan.save
# → ~/silentcastle/tf-plans/TCM-1060-<timestamp>.txt
# → ~/silentcastle/tf-plans/TCM-1060-<timestamp>-show.txt
# → ~/silentcastle/tf-plans/TCM-1060-<timestamp>.tfplan (local only; do not commit)
```

Post-apply state evidence (optional):

```bash
tf.state.show.save 'dba_mgmt|rds' --managed-only
```

Plan then apply with saved artifacts:

```bash
tf.apply.save          # plan-save, confirm, apply
tf.apply.last --yes    # apply latest plan for $TICKET
```

## Commands

| Command | Purpose |
|---------|---------|
| `tf.plan.save` | `terraform plan` + tee log + `terraform show` sidecar |
| `tf.state.show.save` | Dump `terraform state show` for selected addresses |
| `tf.apply.save` | `tf.plan.save`, confirm, `terraform apply` saved plan |
| `tf.apply.last` | Apply newest `$TICKET-*.tfplan` in `TF_PLANS_DIR` |
| `tf.amd64` | Run HashiCorp terraform image as linux/amd64 (Darwin arm64 + Docker only) |

Aliases: `tf-plan-save`, `tf-state-show-save`, `tf-apply-save`, `tf-apply-last`.

Quick local scratch plans (not MR archive):

| Alias | Command |
|-------|---------|
| `tf` | `terraform` |
| `tf.plan` | `terraform plan -out=tfplan` |
| `tf.apply` | `terraform apply tfplan` |
| `tf.destroy.plan` | `terraform plan -destroy -out=tfplan` |

These match the Terraform aliases previously in [sc-zsh `includes/aliases.zsh`](https://github.com/silentcastle/sc-zsh). If you source toolbox `init.sh`, you can remove that Terraform block from sc-zsh to avoid duplicate aliases.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `TICKET` | (prompt) | Ticket id in filenames |
| `TF_PLANS_DIR` | `~/silentcastle/tf-plans` | Archive directory |
| `TF_ROOT` | `$PWD` | Terraform working directory |
| `TF_PLAN_NO_COLOR` | `1` | Pass `-no-color` to plan/show/apply |
| `TF_PLAN_KEEP_ON_APPLY_ABORT` | `1` | When `0`, delete `.tfplan` if apply declined or failed |
| `TF_PLAN_LAST` | (set by plan-save) | Path to last `.tfplan` |
| `TF_PLAN_LAST_TXT` | (set by plan-save) | Path to last plan tee log |
| `TF_PLAN_LAST_SHOW` | (set by plan-save) | Path to last `terraform show` output |

Override defaults in `~/.zshrc.local.pre` or equivalent.

Credentials (`AWS_PROFILE`, assume_role in `providers.tf`, etc.) are never overridden by this module.

## Flags

**`tf.plan.save`:** `--init`, `--no-sensitive`, `--` then any `terraform plan` arguments.

**`tf.state.show.save`:** optional extended-regex grep pattern; `--managed-only` skips `data.*` addresses.

**`tf.apply.save`:** `--init`, `--yes`, `--` then plan arguments.

**`tf.apply.last`:** `--yes`.

## `tfswitch` hook

On interactive zsh/bash, entering a directory with `.terraform-version`, `.tfswitchrc`, or `versions.tf` runs `tfswitch` (alias: `tfswitch -b ~/.local/bin/terraform`). Implemented in `terraform.zsh` / `terraform.bash`.

`tf.plan.save` also runs a quiet `tfswitch` before plan if the hook did not run.

## Sensitive values

`terraform show` may include sensitive values. Review before posting to a public MR. Use `--no-sensitive` on `tf.plan.save` when your Terraform version supports it.

## Module layout

| File | Role |
|------|------|
| `terraform.sh` | Defaults, helpers, functions, aliases, gated `tf.amd64` |
| `terraform.zsh` | `chpwd` tfswitch + zsh completions |
| `terraform.bash` | `PROMPT_COMMAND` tfswitch |

Disable via `toolboxctl disable terraform` or `disabled_modules` in `~/.config/silentcastle/toolbox/shell.yaml`. The old `tfswitch` stem is retired; use `terraform` instead.

## Exit codes

`tf.plan.save` returns Terraform plan exit codes (0 = no changes, 1 = error, 2 = changes present). Text artifacts are still written on non-zero exits when plan output was captured.
