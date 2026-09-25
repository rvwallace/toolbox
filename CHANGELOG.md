# Changelog

This file documents all notable changes to the `toolbox` project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### 2026-09-25

- Added native Nushell EC2 helpers in `shell/modules/aws.nu` (`aws.ec2`, `aws.ec2-key`, and `aws-ec2-nu` alias) returning typed instance tables with tag records for easy pipeline filtering
- Added Nushell companion modules (`shell/init.nu` and `shell/modules/{aws,kube,chef,git,tmux,yazi,terraform}.nu`) providing native `def --env` implementations for environment switchers (AWS, Kubernetes, Chef), aliases, and shell helpers
- Added the `yazi.sh` shell module with a `y` wrapper that changes to Yazi's selected directory on exit; documented the module in `README.md` and `docs/toolbox.md`

### 2026-09-22

- Added npm global package detection, update-all, interactive updates, and removal to `upkeep`.

### 2026-09-19

- Removed the NvChad/Neovim bootstrap setup and `neovim` package dependencies; editor setup is now managed by scvim

### 2026-09-09

- Added `ssm-parameter` CLI script (`scripts/aws/ssm-parameter.sh`) to select and read AWS Systems Manager Parameter Store parameters with `fzf` interactive search or direct lookup, and added documentation in `docs/ssm-parameter.md`

### 2026-08-28

- Added `ollama.update` CLI script (`scripts/ai/ollama.update.sh`) to update all installed local Ollama models with transient live pull progress output

### 2026-08-25

- Fixed `shell/modules/chef.sh` dependency guard: `toolbox_require_commands knife` had no command to check (the sole argument was consumed as the stem), so `chef.env` always loaded regardless of whether `knife` was installed. This was a regression from commit `d246752` ("fix(chef): correct command dependency check"), which had inverted the fix by removing the `chef` stem argument while `chef.bash`/`chef.zsh` kept the correct two-argument form. Restored to `toolbox_require_commands chef knife`.
- Fixed `shell/modules/ansible.sh` reporting the wrong module name (`uv` instead of `ansible`) in `toolbox shell list` status when `uv` is missing (`toolbox_require_commands uv uv` → `toolbox_require_commands ansible uv`)
- Added a usage comment above `toolbox_require_commands` in `shell/init.sh` documenting its `(stem, cmd...)` signature, since the signature mix-up caused both bugs above
- Removed empty `shell/modules/net.sh` (contained only comments, no functions or aliases)
- Rewrote `shell/modules/ansible.sh`: replaced the `uv run --with` alias wrappers with placeholder functions covering all 10 `ansible-core` entry points (`ansible`, `ansible-playbook`, `ansible-vault`, `ansible-galaxy`, `ansible-doc`, `ansible-config`, `ansible-console`, `ansible-inventory`, `ansible-pull`) plus `ansible-lint`. Each placeholder only fires when the real binary isn't already on `PATH`, and prints `uv tool install` instructions instead of running an ephemeral `uv run` environment on every invocation.
- Removed `tf`, `tf.plan`, `tf.apply`, `tf.destroy.plan` shortcut aliases from `shell/modules/terraform.sh` (use the full `terraform` command instead); kept the `tfswitch` alias since it pins the tfswitch-installed binary path rather than saving keystrokes, and the `chpwd`/`PROMPT_COMMAND` auto-switch hooks depend on it
- Removed duplicate hyphenated aliases `tf-plan-save`, `tf-state-show-save`, `tf-apply-save`, `tf-apply-last` from `shell/modules/terraform.sh` and their `compdef` registrations in `shell/modules/terraform.zsh`
- Renamed `tf.plan.save`, `tf.state.show.save`, `tf.apply.save`, `tf.apply.last` to `terraform.plan.save`, `terraform.state.show.save`, `terraform.apply.save`, `terraform.apply.last` in `shell/modules/terraform.sh` (and their `compdef` targets in `terraform.zsh`), dropping the `tf` abbreviation to match removing the `tf`/`tf.plan`/`tf.apply` shortcut aliases; `tf.amd64` is unrelated and unchanged
- Removed the `k` alias (`=kubectl`) from `shell/modules/kube.sh` and its completion registrations in `kube.bash`/`kube.zsh`; kept `k.ctx-list`, `k.get-all`, and `k.env`
- Updated `README.md`, `docs/terraform.md`, and `docs/toolbox.md` to match the above

### 2026-08-22

- Removed AI utilities, shell dispatcher, roles, and docs (`scripts/ai/ollama-update.sh`, `contrib/aichat-roles/`, `shell/modules/ai.{sh,bash,zsh}`, `docs/ai.md`) — migrated to tmux-conf
- Removed `cmux` shell module and completions (`shell/modules/cmux.{sh,zsh}`)
- Removed `zmx` shell integration, keybindings, completions, and docs (`shell/modules/zmx.{sh,bash,zsh}`, `docs/zmx.md`)
- Migrated `tmux` ZLE keybinding (`^T` for `tp`) from `sc-zsh` to `shell/modules/tmux.zsh`
- Migrated AWS token TTL prompt caching helper (`aws.token.ttl.prompt`) to `shell/modules/aws.zsh` for Starship prompt integration
- Migrated Ansible `uv` wrappers (`ansible`, `ansible-playbook`, `ansible-vault`, `ansible-galaxy`, `ansible-lint`, `ansible-console`, `ansible-inventory`, `ansible-doc`, `ansible-config`, `ansible-pull`) to `shell/modules/ansible.sh`

### 2026-08-20

- Added `upkeep` multi-package manager update CLI (`scripts/sys/upkeep.sh`) supporting Homebrew, uv tools, macOS App Store (`mas`), NvChad, Oh My Zsh, npm globals, Cargo globals, Ruby gems, and Flatpak
- Added `upkeep` documentation in `docs/upkeep.md`

### 2026-08-11

- Prevented redundant `compinit` initialization in `shell/init.sh` when sourced in shells with existing completion initialization

### 2026-08-10

- Enhanced `aws-env` interactive picker navigation with PageUp, PageDown, Home (`Ctrl-A`), End (`Ctrl-E`), and keyboard help overlay (`?`)
- Added minimum terminal size guard (40x10) and comprehensive unit tests in `cmd/aws-env/picker_test.go`

### 2026-08-09

- Enhanced `ssh-sc` (`scripts/ssh/ssh-sc.py`) with rich interactive host selection, fuzzy tag matching, domain filtering, and SSH configuration generation
- Added `docs/ssh-sc.md` guide
- Removed superseded `scripts/ssh/ssh-remove-host.sh` utility

### 2026-08-07

- Enhanced `tssh` (`scripts/ssh/tssh.sh`) with session reuse, tmux split-pane support, window renaming, and target host resolution
- Updated `docs/tssh.md` with multi-session workflows and tmux integration options

### 2026-07-20

- Added `tssh` (`scripts/ssh/tssh.sh`) tmux SSH launcher and documentation in `docs/tssh.md`
- Fixed `chef.env` in `shell/modules/chef.sh` dependency check (`knife`) and argument handling
- Extracted embedded NvChad repository files to lean bootstrap installer

### 2026-07-19

- Replaced LazyVim setup with NvChad configuration in `bootstrap.sh` and `docs/toolbox.md`

### 2026-06-28

- Added `merge-zsh-history` utility (`scripts/sys/merge_zsh_history.py`) for deduplicating and merging timestamped Zsh extended history backups
- Added `go_install` support to dependency manager (`cmd/toolbox/bootstrap.go`, `cmd/toolbox/depsyaml.go`, `deps/toolbox.yaml`) and restored `figurine` dependency

### 2026-05-22

- Added Terraform shell module (`shell/modules/terraform.{sh,zsh,bash}`) providing `tf.plan.save`, `tf.state.show.save`, `tf.apply.save`, `tf.apply.last`, and Terraform aliases
- Added `tf.amd64` Docker runner for Apple Silicon compatibility
- Consolidated `tfswitch` auto-switch hook into `terraform` shell stem
- Added `docs/terraform.md` documentation

### 2026-04-24

- Added `aichat` Alt+e interactive command dispatcher (`toolbox_aichat_widget_run` in `shell/modules/ai.sh`) supporting natural language execution (`# ...`, `#ex`, `#rv`, `#er`, `#ask`)
- Added custom AI role prompts in `contrib/aichat-roles/` (`review`, `explain-review`, `ask`) and `install-roles.sh` installer
- Added `docs/ai.md` guide

### 2026-04-18

- Added reusable completion caching engine (`toolbox_completion_cache_ensure`) in `shell/init.sh` with version-sidecar invalidation
- Added `sesh` shell completion modules (`shell/modules/sesh.{bash,zsh}`)
- Migrated `zmx` and `kube` completions (`shell/modules/{zmx,kube}.{bash,zsh}`) to cached version-sidecar standard
- Documented completion caching pattern in `docs/toolbox.md`

### 2026-04-15

- Improved shell compatibility and error handling in `scripts/sys/brew-search.sh`
- Added generated build binaries to `.gitignore`

### 2026-04-11

- Added `aws-env` Go TUI (`cmd/aws-env/`) using Bubble Tea v2 for AWS profile/region selection and session token status inspection
- Updated `shell/modules/aws.sh` to wrap `aws-env` binary
- Added `AWS_EC2_KEY_DIR` environment variable support in `scripts/aws/aws-ec2.py` and documented in `docs/aws-ec2.md`

### 2026-04-09

- Initial repository release with 28 CLI utilities across Python, Bash, Swift, and Go
- Added `toolbox` Go manager (`cmd/toolbox/`) for tool installation, symlinking, shell module management, and dependency bootstrapping
- Added modular Bash and Zsh shell framework (`shell/init.sh`, `shell/toolboxctl.sh`, `shell/modules/`)
- Made PagerDuty subdomain configurable via `--domain` flag and `PAGERDUTY_DOMAIN` environment variable in `scripts/pagerduty/` tools
