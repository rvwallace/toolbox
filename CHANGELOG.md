# Changelog

This file documents all notable changes to the `toolbox` project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### 2026-08-22

- Migrated `cmux` and `tmux` ZLE keybindings (`^X^C` for `cmux.ssh`, `^T` for `tp`) from `sc-zsh` to `shell/modules/{cmux,tmux}.zsh`
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
