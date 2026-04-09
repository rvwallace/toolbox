# join-call

Textual TUI that lists **Microsoft Teams** meeting deeplinks from a TOML file and opens the selected link with **`open`** on macOS.

**Source:** `scripts/productivity/join-call.py`  
**After install:** `join-call`

## Configuration

- Path: `~/.config/silentcastle/teams-calls.toml` (or under `XDG_CONFIG_HOME` when set)
- If the file is missing on first run, the app creates it from **built-in defaults** baked into the script (you should edit names and deeplinks for your org).

### TOML shape

Each meeting is one `[[call]]` table:

```toml
[[call]]
name = "Team standup"
description = "Daily sync"
deeplink = "msteams:/l/meetup-join/19:meeting_...@thread.v2/0?context=..."
```

Rules enforced when loading:

- `name` and `deeplink` are required; `deeplink` must start with `msteams:`
- Invalid entries are skipped with a message to stderr; if nothing loads, defaults apply

## TUI keys

- **Enter:** open the selected deeplink (`open` on macOS)
- **q:** quit

## Requirements

- macOS (uses `/usr/bin/open` for Teams)
- Python dependency: **textual** (see PEP 723 block in the script)

## Scenarios

- **Edit once:** copy your Teams links from Outlook or Teams (deeplink format) into `teams-calls.toml` with readable `name` values.
- **Run:** `join-call`, move with arrow keys, Enter to join.

This tool does not run on Linux or Windows unless you change the script to use a different launcher than `open`.
