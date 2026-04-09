# ghrel

GitHub release browser and asset downloader (Bubble Tea TUI). Run `ghrel` after `./toolbox install`.

## Flow

1. Enter `owner/repo`, press Enter.
2. Pick a release (left panel) and an asset (right panel); Tab / Shift+Tab switches panels.
3. Enter on an asset downloads it.

## Keys (summary)

| Context | Keys |
|---------|------|
| Repo input | Enter search, `s` settings, Ctrl+C quit |
| Browse | j/k or arrows, Tab/l and Shift+Tab/h switch panels, Enter (releases → assets or download), `s` settings, Esc/q back |
| Settings | Esc back to repo input |

## Config

Path: `~/.config/silentcastle/ghrel.json` (or `$XDG_CONFIG_HOME/silentcastle/ghrel.json`).

If you used the standalone `ghrel` repo before, `~/.config/ghrel/config.json` is still read until you save settings once (then the new path is written).

Fields match the in-app settings screen: install path, download path, releases per page, mark executable on bare binaries.

## GitHub API auth

Optional. Unauthenticated works for public repos (lower rate limit). Set one of `DRA_GITHUB_TOKEN`, `GITHUB_TOKEN`, or `GH_TOKEN` for higher limits or private repos.

## Implementation

Built from `cmd/ghrel/` (Go, `charm.land/bubbletea/v2`).
