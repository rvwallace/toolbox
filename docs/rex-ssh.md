# rex-ssh

Open ordinary SSH connections in local Rex tabs or splits. No remote Rex
binary, service or Tailscale installation is needed. OpenSSH handles
authentication, host-key checks, aliases, keys and jump hosts. Use an existing,
approved remote `screen` installation manually for long-running work.

```sh
rex-ssh                              # fzf: recent connections and SSH aliases
rex-ssh server-alias                  # open directly; offer existing managed tab
rex-ssh --label "Production DB" server-alias
rex-ssh --new server-alias            # explicitly open another connection
rex-ssh --split right server-alias    # another SSH login beside the current pane
rex-ssh --split down server-alias
rex-ssh --session main server-alias   # explicit local Rex session

# Put SSH options and their destination after the separator.
rex-ssh --label "Jump host" -- -i "$JUMPCLOUD_KEY" "${JUMPCLOUD_USER}@10.181.32.69"
rex-ssh -- -p 2222 -J bastion user@private-host
rex-ssh --no-store root@192.168.68.9
```

Requirements: local Rex CLI/server, uv with Python 3.11 or later, and OpenSSH.
The Python script has no third-party dependencies. fzf is needed only for
pickers, including the duplicate-tab choice. Install through `./toolbox install`
or invoke `scripts/ssh/rex-ssh.py` directly. The helper targets a local Rex
Unix socket; it refuses a remote `REX_SERVER` endpoint. It does not start a
missing Rex server. If the inherited session is stale, use `--session` rather
than silently launching in another session. A split requires a current live
`REX_BLOCK` in the selected session.

## Connection behavior

The new tab takes focus within its Rex session. If you are viewing a different
session in the app, the helper does not invoke app Remote Control to switch
sessions. Use native Rex navigation to view it. No custom keybinding or reload
is required.

When SSH exits, its status remains visible and the terminal offers **r** to
reconnect or **Enter** to close. Reconnect starts the same SSH argument vector
in that pane. It never retries automatically. Normal SSH prompts remain in
the pane; passwords and key passphrases are not requested by rex-ssh itself.

For stored destination-only connections, a small local registry tracks tabs
the helper created. Before offering to switch, it checks that the recorded
block/window still exists in the same session. A managed tab can be sitting at
the reconnect prompt; switching to it is not proof of an authenticated login.
`--new` bypasses this choice. `--split` always opens another login. Advanced
connections and `--no-store` launches are not added to that registry, so they
do not participate in duplicate detection.

Remote commands and noninteractive/control modes such as `-N`, `-f`, `-G`,
`-O` and `-W` are intentionally unsupported. Run `ssh` directly for those
operations. Interactive options such as `-i`, `-p`, `-J` and `-o` are passed as
separate arguments, with no shell evaluation. Some command/mode overrides
through `-o` are also rejected. OpenSSH still owns the effective behavior of
your SSH configuration.

Configure keepalives per host in SSH config if needed; rex-ssh does not
silently change connection timeouts or keepalive defaults.

## Picker and SSH config aliases

The picker combines recent entries with explicit `Host` aliases from
`~/.ssh/config`, following `Include` globs. Wildcard and negated Host patterns
are not destinations. It does not run `ssh -G` or execute `Match exec` to
discover aliases. Include traversal is bounded, and conditional Match values
are not presented as effective connection settings.

Rows show labels, destinations, tags and last-attempt timestamps. Alias rows
can include literal HostName, Port and ProxyJump values that pass field-specific
validation. These are a limited preview, not a full OpenSSH config evaluator;
global defaults, substitutions and conditional settings may differ. Raw SSH
options, ProxyCommand, IdentityFile and arbitrary config values are not shown.

Menu actions include **New connection…**, **Edit history…** and **Forget a
recent connection…**. Use native Rex navigation for general tab/pane management.

## Private recent history

History lives at:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/silentcastle/rex-ssh/
  recent-hosts.json
  active.json
  state.lock
```

The directory is mode `0700`; files and editor backups are mode `0600`.
Writes are locked and replaced atomically. History records destination, label,
last attempted launch, pin status and tags. It keeps at most 50 recent entries,
prioritizing pins, and deduplicates destinations. The active registry contains
only destinations and Rex IDs and is capped at 100 records; stale entries are
checked before use.

Only destination-only connections are saved. Any extra SSH option disables
history and active-registry storage for that launch. Define an SSH alias for
reusable advanced connections instead. A tab opening is recorded as an
**attempt**, not a successful remote login.

```sh
rex-ssh --no-store server-alias         # no history/registry writes
rex-ssh --edit                         # $EDITOR, falling back to vi
rex-ssh --forget server-alias
rex-ssh --clear --yes                  # clear history, not live SSH sessions
rex-ssh --pin server-alias
rex-ssh --unpin server-alias
rex-ssh --tags server-alias prod,database
rex-ssh --expire-days 90                # hide older unpinned entries in picker
```

Expiry is optional per invocation. It preserves pins and is applied to stored
history on the next recorded launch. Clearing or forgetting recent history
does not close tabs or clear the separate active-tab registry. `--no-store`
prevents helper state writes on that launch; it does not erase prior history.

The editable JSON format is:

```json
{
  "version": 1,
  "connections": [
    {
      "destination": "server-alias",
      "label": "Production DB",
      "last_attempt": "2026-11-10T20:00:00+00:00",
      "pinned": true,
      "tags": ["prod", "database"]
    }
  ]
}
```

`--edit` saves a private backup before invoking `$EDITOR`. Editor arguments are
split without shell evaluation; ordinary forms such as `code --wait` work.
The result is validated. Invalid edits remain available for correction and
block stored launches; the helper does not silently discard or execute them.
The editor action can repair an already malformed history file. Editor swap
or backup files can contain host data too. Backups are retained for manual
recovery; `--clear` clears the history records, not backups or SSH config.

## Credentials and notifications

Never pass passwords or tokens on a command line. Password authentication
belongs in SSH's prompt, and keys/passphrases belong in the existing SSH/agent
workflow. The helper rejects credential-bearing destinations, suspicious
password/token assignments and control characters without echoing the rejected
values. It never saves raw SSH argument vectors. This does not make arbitrary
command-line secrets safe: supplied arguments still go through the local Rex
process-launch API and can be visible to process inspection or Rex's own state.
`--no-store` controls this helper's files only, not shell history, OS auditing,
remote logging or Rex's internal persistence. Host labels and destinations
are also potentially sensitive; file permissions are not encryption.

`--notify` requests a Rex OSC 777 desktop notification when SSH exits with a
nonzero status. Text is fixed and contains no arguments, host identity or SSH
error output. Routine launches/history updates do not send notifications.
Terminal output remains the primary diagnostic. Rex's **Terminal notifications**
setting and macOS permission determine delivery; the helper changes neither.
Notification display has not been interactively verified. No general floating
in-app notification API is assumed.

## Verification

Automated checks use disposable fake Rex, SSH, fzf and editor commands. A real
pseudo-terminal test verifies reconnect and close. On 2026-11-10, user-authorized
live tests opened a new Rex tab and split: JumpCloud key authentication reached
a shell and returned a harmless printf marker; the root connection to the
sample LAN host reached its password prompt. No password was supplied by the
agent. Both samples used `--no-store`; nothing was installed remotely.
