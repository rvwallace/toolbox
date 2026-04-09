# ssm-connect

Bubble Tea v2 TUI to pick an EC2 instance and start an **AWS Systems Manager Session Manager** shell (`aws ssm start-session`). The instance list is cached under your XDG cache directory to cut repeat API calls, and the TUI resumes after the interactive session exits.

**Source:** `cmd/ssm-connect/`  
**After install:** `ssm-connect`

## Requirements

- **Profile and region** must be known before the TUI starts: set `AWS_PROFILE` and `AWS_REGION` (or `AWS_DEFAULT_REGION`), or pass `-p` / `-r`. If region is still missing, the tool runs `aws configure get region` for your profile. If either is still missing, it exits immediately with a short message (no EC2 fetch).
- Go build support via `./toolbox install`
- **AWS CLI** on `PATH` (the tool uses it for both instance discovery and `aws ssm start-session`)
- **Session Manager plugin** for the AWS CLI on the machine where you run the TUI (same requirement as a manual SSM session)
- IAM permission to call EC2 describe APIs, SSM `DescribeInstanceInformation` (for the SSM column and filters), and SSM `StartSession` on the target instance; the instance must be **running** and **SSM-managed** (agent, IAM profile, network where applicable) for sessions to work

## Configuration and cache

- Config directory: `~/.config/silentcastle/` (`ssm-connect.json`, currently used for default cache TTL)
- Cache: under `XDG_CACHE_HOME` or `~/.cache/silentcastle/`

## CLI flags

| Flag | Meaning |
|------|---------|
| `-p` / `--profile` | AWS profile (**required** unless `AWS_PROFILE` is set in the environment) |
| `-r` / `--region` | Region (**required** unless `AWS_REGION` / `AWS_DEFAULT_REGION` is set, or `aws configure get region` succeeds for that profile) |
| `-q` / `--query` | Seed string for the in-TUI filter box |
| `-f` / `--force-refresh` | Ignore a still-valid instance cache and refetch |
| `-t` / `--ttl` | Cache TTL in seconds (default 86400) |
| `-d` / `--debug` | Enable debug-sensitive fallback behavior such as surfacing cache write failures |
| `--no-alt` | Run without the alternate screen buffer |

## TUI behavior

- **Search (`/` then type):** substring match over name, instance id, IPs, EC2 state, type, AMI, platform, key name, and (after SSM data loads) SSM ping status, platform type/name, and agent version. While SSM is loading, rows that are not SSM-managed match the literal `ssm n/a` in search (same idea as the Python TUI).
- **First column:** `…` while SSM info is loading, `✓` when SSM reports **Online**, `×` when the instance is not in SSM or ping is not online.
- **`a`:** toggle **running only** (default, like the Python app) vs **all EC2 states**.
- **`f`:** toggle **SSM-managed only** (instances returned by `describe-instance-information`). If SSM data is not loaded yet, a fetch is started when you turn this on.
- **Details panel:** shows SSM ping, platform type, OS name, and agent version when available.

## Typical flow

1. Run `ssm-connect` with the profile and region you use for that account.
2. Optionally use **`a`** / **`f`** and the filter box to narrow the list.
3. Select an instance, press Enter.
4. The tool suspends the TUI, runs `aws ssm start-session --target <instance-id>` in your terminal, then returns to the TUI when the session exits.

## Scenarios

- **Jump to a named server:** start with `-q web` (or any substring you use in the filter) to reduce the list.
- **Stale list after launches or terminates:** use `--force-refresh` once.
- **Different account:** set `--profile` / `--region` or export `AWS_PROFILE` and `AWS_REGION` before running.

If the TUI fails to start, check that `aws` is installed, your AWS profile and region are valid, and the Session Manager plugin is installed.
