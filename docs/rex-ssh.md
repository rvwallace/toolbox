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
rex-ssh --recent "Production DB"     # replay saved SSH parameters by label
rex-ssh --split right                # reuse the current managed SSH connection

# Put SSH options and their destination after the separator.
rex-ssh --label "Jump host" -- -i "$JUMPCLOUD_KEY" "${JUMPCLOUD_USER}@10.181.32.69"
rex-ssh -- -p 2222 -J bastion user@private-host
rex-ssh --no-store root@192.168.68.9

# Save a JumpCloud profile, including the identity path and tags.
rex-ssh --label phi-p-pls-nodejs01 --notify --tags pls,phi -- \
  -i "$JUMPCLOUD_KEY" "${JUMPCLOUD_USER}@10.181.32.69"
# Later, without repeating the SSH arguments:
rex-ssh --recent phi-p-pls-nodejs01
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

The helper creates the terminal with server focus, then asks the Rex app to
select the exact session/window through `session.select`. This requires app
Remote Control, which the user enabled in Settings → Server / Rex Server.
With one connected app it is selected automatically; with several use
`--client APP_ID_OR_LABEL` or `REX_CLIENT`. A refusal or ambiguity produces a
warning without discarding the opened terminal. CLI acceptance confirms the
focus request, not a separate readback of the app's visible interface.

### Standard split shortcuts

The companion `rex-config/rex/rex_ssh.lua` adds conditional **Cmd+d** and
**Shift+Cmd+d** handlers. In a managed rex-ssh pane they reuse its exact SSH
arguments, label and notification/storage settings to open another login.
In an unmanaged/local pane they return control to Rex's default binding.
The palette also offers **Split SSH Pane Right** and **Split SSH Pane Down**.
The built-in split menu actions are not replaced; use these shortcuts or the
SSH-aware palette actions. The user-authorized reload activated this integration
at generation 5 on 2026-11-10. On another installation the Lua module must be
installed/configured and explicitly reloaded separately.

A live runner serves connection metadata only through a mode-0600 Unix socket
inside an owned mode-0700 `/tmp/rex-ssh-runtime-UID` directory. Both ends verify
the peer's user ID. The socket file contains no argument data; its response
comes from the live process's memory, and it is removed on normal exit. Before
splitting, the helper verifies the selected pane's exact script and PID. The
runner also supplies the CLI path because Rex config actions may have a smaller
PATH than terminals. This works with `--no-store` without writing its arguments
into history. Old panes started before this update must be reopened once.

When SSH exits, its status remains visible and the terminal offers **r** to
reconnect or **Enter** to close. Reconnect starts the same SSH argument vector
in that pane. It never retries automatically. Normal SSH prompts remain in
the pane; passwords and key passphrases are not requested by rex-ssh itself.

For stored profiles, a small local registry tracks tabs
the helper created. Before offering to switch, it checks that the recorded
block/window still exists in the same session. A managed tab can be sitting at
the reconnect prompt; switching to it is not proof of an authenticated login.
`--new` bypasses this choice. `--split` always opens another login. Parameters
and labels distinguish profiles on the same host. Unsafe-option and `--no-store`
launches skip the disk registry; they still have live metadata for splitting.

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
last attempted launch, pin status, tags and a validated `ssh_args` array. It
keeps at most 50 entries, prioritizing pins. A profile is identified by its
label plus exact argument vector, so different keys/ports on the same host do
not overwrite each other. The active registry contains the same validated
profile and Rex IDs, capped at 100 records; stale entries are checked before use.

Safe parameters are saved exactly, including `-i` identity paths, `-p` ports,
`-l` users, `-J` jump hosts, `-F` SSH-config paths and ordinary login flags.
`-o` persistence uses an allowlist for fields such as IdentityFile, User,
Port, ProxyJump, IdentitiesOnly, Compression and keepalive settings. Arbitrary
command, log and tunnel options can run when supported but are not saved.
Credential-shaped values are rejected. A tab opening is recorded as an
**attempt**, not a successful remote login. Existing destination-only records
remain valid. Saved paths/usernames are expanded values from the launch, not
shell-variable expressions to evaluate later.

```sh
rex-ssh --no-store server-alias         # no history/registry writes
rex-ssh --edit                         # $EDITOR, falling back to vi
rex-ssh --forget server-alias
rex-ssh --clear --yes                  # clear history, not live SSH sessions
rex-ssh --pin server-alias
rex-ssh --unpin server-alias
rex-ssh --tags server-alias prod,database
rex-ssh server-alias --tags prod,database # tag while launching
rex-ssh --tag prod --tag database server-alias
rex-ssh --expire-days 90                # hide older unpinned entries in picker
```

Expiry is optional per invocation. It preserves pins and is applied to stored
history on the next recorded launch. Clearing or forgetting recent history
does not close tabs or clear the separate active-tab registry. `--no-store`
prevents history/active-registry writes on that launch; it does not erase prior
history or disable the private live IPC socket. An explicitly requested no-store
split also remains no-store when its source was saved. History-management targets
resolve by exact label first, then unambiguous destination; ambiguous targets
produce an error. If several profiles share a label, `--recent LABEL` refuses to
choose arbitrarily; assign unique labels with `--edit`.

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
      "tags": ["prod", "database"],
      "ssh_args": ["-p", "2222", "server-alias"]
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
values. It saves only validated SSH argument arrays and never evaluates them
as shell code. This does not make arbitrary
command-line secrets safe: supplied arguments still go through the local Rex
process-launch API and can be visible to process inspection or Rex's own state.
`--no-store` controls this helper's persistent history/registry only, not shell history, OS auditing,
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
agent. Both initial samples used `--no-store`; nothing was installed remotely.
The follow-up tested saving/replaying JumpCloud parameters/tags, accepted app
selection requests, a loaded SSH split action, and Cmd+d through Rex's key API
(`handled=true`). A harmless printf marker was verified in the new remote split.
The current suite has 58 Python checks, including real local IPC/peer checks,
PATH bootstrap, no-store inheritance and a PTY reconnect test; the companion
Lua module has nine mocked checks. Physical keystrokes and notification display
have not been independently observed by the agent.
