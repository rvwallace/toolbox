# ssh-sc

`ssh-sc` is an interactive SSH key and `known_hosts` helper. It can inspect,
load, unload, and generate SSH keys. It can also repair SSH file permissions
and remove known-host entries.

```bash
ssh-sc --help
ssh-sc list-keys
ssh-sc add-key
ssh-sc unload-key
ssh-sc unload-keys
ssh-sc generate-key
ssh-sc remove-known-host
ssh-sc fix-permissions --dry-run
```

## Requirements

- OpenSSH `ssh-add` and `ssh-keygen`
- `fzf` for the key and known-host selectors
- `pbcopy`, `wl-copy`, or `xclip` for optional clipboard support

The toolbox dependency files install `fzf` on supported systems. The clipboard
tool is optional.

## Selector controls

The key and known-host selectors use a list on the left and a preview on the
right. The preview changes when the highlighted item changes.

- Use the arrow keys to move through the list.
- Type text to filter the list.
- Push `Enter` to select an item.
- Push `Esc` to cancel.
- In the known-host selector, push `Tab` or `Shift-Tab` to select multiple hosts.

The key preview shows the file, key type, size, fingerprint, comment, and agent
status. It does not show private key data.

## Inspect keys

Run this command to inspect a private key:

```bash
ssh-sc list-keys
```

You can supply an initial search query:

```bash
ssh-sc list-keys work
```

After you select a key, `ssh-sc` shows its metadata in a summary panel.

## Add a key to ssh-agent

Run this command:

```bash
ssh-sc add-key
```

The selector shows whether each key is already loaded. `ssh-sc` does not add a
key that is already loaded.

If `ssh-agent` is not available, `ssh-sc` shows this command:

```bash
eval "$(ssh-agent -s)"
```

Run the command in the current bash or zsh shell. A child process cannot update
the agent variables in its parent shell.

`ssh-sc` also offers to copy the command. It uses the first available clipboard
tool from `pbcopy`, `wl-copy`, and `xclip`.

## Unload keys from ssh-agent

Remove one key:

```bash
ssh-sc unload-key
```

The selector lists the keys that are loaded in the agent. It also lists keys
whose local private key file is not available. `ssh-sc` shows the selected key
and asks for confirmation before it removes the key.

Remove all loaded keys:

```bash
ssh-sc unload-keys
```

`ssh-sc` shows all loaded identities first. It removes the identities only after
you confirm the operation.

## Generate a key

Run this command:

```bash
ssh-sc generate-key
```

The command asks for these values:

1. Key filename
2. Key type
3. Optional key comment
4. Passphrase protection

The key filename must not contain a directory component. `ssh-sc` writes the key
to `~/.ssh` and does not overwrite an existing private or public key.

Passphrase protection is the default. If you select it, `ssh-keygen` asks for
the passphrase twice. `ssh-sc` requires a second confirmation before it creates
an unencrypted private key.

After key generation, the summary shows the private key path, public key path,
key type, protection status, and fingerprint. It also shows the applicable
`ssh-add` command.

## Remove known-host entries

Run this command:

```bash
ssh-sc remove-known-host
```

The left pane groups entries by host. The right pane shows the exact matching
lines from `~/.ssh/known_hosts`. Select one or more hosts, review the entries,
and confirm the removal.

Before removal, `ssh-sc` creates a timestamped backup next to `known_hosts`. It
keeps the five newest backups. If removal fails, use the backup path from the
command output to restore the file.

## Repair SSH permissions

Preview the required changes:

```bash
ssh-sc fix-permissions --dry-run
```

Run the command without an option to preview the changes and get a confirmation
prompt:

```bash
ssh-sc fix-permissions
```

Apply the shown changes without a confirmation prompt:

```bash
ssh-sc fix-permissions --apply
```

The command uses these modes:

| Item | Mode |
|------|------|
| `~/.ssh` | `0700` |
| Private keys | `0600` |
| `config` | `0600` |
| `authorized_keys` | `0600` |
| Public keys | `0644` |
| `known_hosts*` | `0644` |

`ssh-sc` examines unrecognized files with `ssh-keygen`. It changes a file only
when `ssh-keygen` identifies it as a private key. It reports and skips all other
unrecognized files. It also skips symbolic links.
