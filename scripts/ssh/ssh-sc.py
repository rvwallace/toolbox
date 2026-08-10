#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "rich",
#     "typer",
# ]
# bin-name = "ssh-sc"
# ///

"""SSH helper script for managing keys and known_hosts."""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="SSH helper script.")
console = Console()
KNOWN_HOSTS_BACKUPS_TO_KEEP = 5


@dataclass(frozen=True)
class PrivateKey:
    """Metadata for one private key file."""

    path: Path
    bits: str
    fingerprint: str
    comment: str
    key_type: str
    loaded: bool


@dataclass(frozen=True)
class AgentIdentity:
    """Metadata for one identity loaded in ssh-agent."""

    bits: str
    fingerprint: str
    comment: str
    key_type: str
    public_key: str
    local_path: Optional[Path]


def check_for_command(command: str):
    """Check if a command exists."""
    if not shutil.which(command):
        console.print(f"[red]Error: '{command}' is not installed or not in your PATH.[/red]")
        raise typer.Exit(1)


def _copy_to_clipboard(text: str) -> Optional[str]:
    """Copy text with the first available clipboard command."""
    clipboard_commands = [
        ("pbcopy", ["pbcopy"]),
        ("wl-copy", ["wl-copy"]),
        ("xclip", ["xclip", "-selection", "clipboard"]),
    ]
    for name, command in clipboard_commands:
        if not shutil.which(name):
            continue
        copy_process = subprocess.run(
            command,
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
        if copy_process.returncode == 0:
            return name
    return None


def _parse_keygen_listing(line: str) -> Optional[tuple[str, str, str, str]]:
    """Parse one ssh-keygen or ssh-add fingerprint line."""
    parts = line.split()
    if len(parts) < 3:
        return None
    key_type = parts[-1].removeprefix("(").removesuffix(")")
    return parts[0], parts[1], " ".join(parts[2:-1]), key_type


def _loaded_fingerprints() -> set[str]:
    """Return agent fingerprints, or an empty set when no agent is available."""
    probe = subprocess.run(
        ["ssh-add", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode not in {0, 1}:
        return set()
    fingerprints = set()
    for line in probe.stdout.splitlines():
        parsed = _parse_keygen_listing(line)
        if parsed:
            fingerprints.add(parsed[1])
    return fingerprints


def _get_private_keys() -> list[PrivateKey]:
    """Return metadata for private key files in the .ssh directory."""
    ssh_path = Path.home() / ".ssh"
    keys: list[PrivateKey] = []
    if not ssh_path.is_dir():
        return []

    loaded_fingerprints = _loaded_fingerprints()
    for path in sorted(ssh_path.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix in {".pub", ".bak"}:
            continue
        if path.name.startswith(("known_hosts", "authorized_keys", "config")):
            continue
        if ".bak" in path.name or ".old" in path.name:
            continue

        probe = subprocess.run(
            ["ssh-keygen", "-l", "-f", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            continue
        parsed = _parse_keygen_listing(probe.stdout.splitlines()[0])
        if not parsed:
            continue
        bits, fingerprint, comment, key_type = parsed
        keys.append(
            PrivateKey(
                path=path,
                bits=bits,
                fingerprint=fingerprint,
                comment=comment,
                key_type=key_type,
                loaded=fingerprint in loaded_fingerprints,
            )
        )
    return keys


def _key_preview(key: PrivateKey) -> str:
    """Return a safe preview that never includes private key material."""
    status = "loaded in ssh-agent" if key.loaded else "not loaded"
    return "\n".join(
        [
            f"File:        {key.path}",
            f"Type:        {key.key_type}",
            f"Bits:        {key.bits}",
            f"Fingerprint: {key.fingerprint}",
            f"Comment:     {key.comment or '(none)'}",
            f"Agent:       {status}",
        ]
    )


def _fzf_select(
    items: list[tuple[str, str, str]],
    *,
    prompt: str,
    header: str,
    query: Optional[str] = None,
    multi: bool = False,
) -> Optional[list[str]]:
    """Select values in a split-pane fzf interface."""
    check_for_command("fzf")
    with tempfile.TemporaryDirectory(prefix="ssh-sc-preview-") as preview_dir_name:
        preview_dir = Path(preview_dir_name)
        values: dict[str, str] = {}
        choice_lines = []
        for index, (value, display, preview) in enumerate(items):
            item_id = str(index)
            values[item_id] = value
            (preview_dir / item_id).write_text(preview)
            choice_lines.append(f"{item_id}\t{display}")

        command = [
            "fzf",
            "--height=80%",
            "--layout=reverse",
            "--border=rounded",
            "--delimiter=\\t",
            "--with-nth=2",
            f"--prompt={prompt}",
            f"--header={header}",
            "--preview-window=right:55%:wrap:border-left",
            f"--preview=cat {shlex.quote(str(preview_dir))}/{{1}}",
        ]
        if query:
            command.append(f"--query={query}")
        if multi:
            command.append("--multi")

        selection_process = subprocess.run(
            command,
            input="\n".join(choice_lines),
            capture_output=True,
            text=True,
            check=False,
        )
    if selection_process.returncode in {1, 130}:
        return None
    if selection_process.returncode != 0:
        console.print("[red]fzf could not open the selector.[/red]")
        if selection_process.stderr.strip():
            console.print(f"[dim]{selection_process.stderr.strip()}[/dim]")
        raise typer.Exit(1)
    return [
        values[line.split("\t", maxsplit=1)[0]]
        for line in selection_process.stdout.splitlines()
        if line
    ]


def _select_private_key(
    keys: list[PrivateKey], query: Optional[str], *, prompt: str
) -> Optional[PrivateKey]:
    """Select one private key with metadata visible in the preview pane."""
    selections = _fzf_select(
        [
            (
                str(key.path),
                f"{key.path.name}  [{key.key_type}]  "
                f"{'loaded' if key.loaded else 'not loaded'}",
                _key_preview(key),
            )
            for key in keys
        ],
        prompt=prompt,
        header="↑/↓: move  Enter: select  ESC: cancel",
        query=query,
    )
    if not selections:
        return None
    selected_path = Path(selections[0])
    return next(key for key in keys if key.path == selected_path)


def _require_agent() -> None:
    """Stop with current-shell setup guidance when ssh-agent is unavailable."""
    agent_probe = subprocess.run(
        ["ssh-add", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    if agent_probe.returncode in {0, 1}:
        return
    start_agent_command = 'eval "$(ssh-agent -s)"'
    console.print(
        Panel(
            f"[bold cyan]{start_agent_command}[/bold cyan]",
            title="[bold yellow]ssh-agent is not available[/bold yellow]",
            subtitle="Run this in your current bash or zsh shell",
            border_style="yellow",
        )
    )
    if typer.confirm("Copy this command to the clipboard?", default=True):
        clipboard_tool = _copy_to_clipboard(start_agent_command)
        if clipboard_tool:
            console.print(f"[green]✓[/green] Copied with [cyan]{clipboard_tool}[/cyan].")
        else:
            console.print(
                "[yellow]Could not copy the command. No supported clipboard "
                "tool was available.[/yellow]"
            )
    console.print("Start the agent, then run the ssh-sc command again.")
    raise typer.Exit(1)


def _get_agent_identities(private_keys: list[PrivateKey]) -> list[AgentIdentity]:
    """Return identities from ssh-agent, including keys absent from disk."""
    _require_agent()
    public_keys_process = subprocess.run(
        ["ssh-add", "-L"],
        capture_output=True,
        text=True,
        check=False,
    )
    if public_keys_process.returncode == 1:
        return []
    if public_keys_process.returncode != 0:
        console.print("[red]Could not read identities from ssh-agent.[/red]")
        raise typer.Exit(1)

    paths_by_fingerprint = {key.fingerprint: key.path for key in private_keys}
    identities = []
    for public_key in public_keys_process.stdout.splitlines():
        fingerprint_process = subprocess.run(
            ["ssh-keygen", "-l", "-f", "-"],
            input=f"{public_key}\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if fingerprint_process.returncode != 0:
            continue
        parsed = _parse_keygen_listing(fingerprint_process.stdout.strip())
        if not parsed:
            continue
        bits, fingerprint, comment, key_type = parsed
        identities.append(
            AgentIdentity(
                bits=bits,
                fingerprint=fingerprint,
                comment=comment,
                key_type=key_type,
                public_key=public_key,
                local_path=paths_by_fingerprint.get(fingerprint),
            )
        )
    return identities


def _identity_preview(identity: AgentIdentity) -> str:
    """Return agent identity details for an fzf preview pane."""
    return "\n".join(
        [
            f"File:        {identity.local_path or '(not found locally)'}",
            f"Type:        {identity.key_type}",
            f"Bits:        {identity.bits}",
            f"Fingerprint: {identity.fingerprint}",
            f"Comment:     {identity.comment or '(none)'}",
            "",
            "Public key:",
            identity.public_key,
        ]
    )


@app.callback()
def main():
    """SSH script commands."""
    pass


@app.command("list-keys")
def list_keys(
    query: Optional[str] = typer.Argument(None, help="Optional initial query filter"),
) -> None:
    """Browse SSH private keys and inspect their metadata."""
    check_for_command("ssh-add")
    check_for_command("ssh-keygen")
    keys = _get_private_keys()
    if not keys:
        console.print("[yellow]No private key files found.[/yellow]")
        raise typer.Exit()

    selected_key = _select_private_key(keys, query, prompt="Inspect key > ")
    if not selected_key:
        console.print("No changes made.")
        raise typer.Exit()

    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_column("Field", style="bold")
    summary.add_column("Value")
    summary.add_row("File", str(selected_key.path))
    summary.add_row("Type", selected_key.key_type)
    summary.add_row("Bits", selected_key.bits)
    summary.add_row("Fingerprint", selected_key.fingerprint)
    summary.add_row("Comment", selected_key.comment or "(none)")
    summary.add_row("Agent", "loaded" if selected_key.loaded else "not loaded")
    console.print(Panel(summary, title="[bold]SSH key[/bold]", border_style="cyan"))

@app.command("add-key")
def add_key(
    query: Optional[str] = typer.Argument(None, help="Optional initial query filter"),
) -> None:
    """Add an SSH key to the ssh-agent."""
    check_for_command("ssh-add")
    check_for_command("ssh-keygen")
    _require_agent()
    keys = _get_private_keys()
    if not keys:
        console.print("[yellow]No private key files found.[/yellow]")
        raise typer.Exit()

    selected_key = _select_private_key(keys, query, prompt="Add key > ")
    if not selected_key:
        console.print("No changes made.")
        raise typer.Exit()
    if selected_key.loaded:
        console.print(
            f"[yellow]{selected_key.path.name} is already loaded in ssh-agent.[/yellow]"
        )
        raise typer.Exit()

    add_process = subprocess.run(
        ["ssh-add", str(selected_key.path)],
        check=False,
    )
    if add_process.returncode != 0:
        console.print(f"[red]Could not add key:[/] {selected_key.path}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Added {selected_key.path}")
    console.print(f"[dim]{selected_key.fingerprint}[/dim]")


@app.command("unload-key")
def unload_key():
    """Remove a specific key from ssh-agent."""
    check_for_command("ssh-add")
    check_for_command("ssh-keygen")

    private_keys = _get_private_keys()
    identities = _get_agent_identities(private_keys)
    if not identities:
        console.print("No keys are loaded in ssh-agent.")
        raise typer.Exit()

    selections = _fzf_select(
        [
            (
                identity.fingerprint,
                f"{identity.comment or '(no comment)'}  [{identity.key_type}]",
                _identity_preview(identity),
            )
            for identity in identities
        ],
        prompt="Unload key > ",
        header="↑/↓: move  Enter: review  ESC: cancel",
    )
    if not selections:
        console.print("No changes made.")
        raise typer.Exit()
    identity = next(item for item in identities if item.fingerprint == selections[0])
    console.print(Panel(_identity_preview(identity), title="[bold]Unload key[/bold]"))
    if not typer.confirm("Remove this key from ssh-agent?", default=False):
        console.print("No changes made.")
        raise typer.Exit()

    with tempfile.NamedTemporaryFile(mode="w", prefix="ssh-sc-public-key-") as key_file:
        key_file.write(f"{identity.public_key}\n")
        key_file.flush()
        remove_process = subprocess.run(
            ["ssh-add", "-d", key_file.name],
            capture_output=True,
            text=True,
            check=False,
        )
    if remove_process.returncode != 0:
        console.print("[red]Could not remove the selected key from ssh-agent.[/red]")
        if remove_process.stderr.strip():
            console.print(f"[dim]{remove_process.stderr.strip()}[/dim]")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Removed {identity.comment or identity.fingerprint}")


@app.command("unload-keys")
def unload_keys():
    """Remove all keys from ssh-agent."""
    check_for_command("ssh-add")
    check_for_command("ssh-keygen")
    identities = _get_agent_identities(_get_private_keys())
    if not identities:
        console.print("No keys are loaded in ssh-agent.")
        raise typer.Exit()

    table = Table("Comment", "Type", "Fingerprint", "Local file")
    for identity in identities:
        table.add_row(
            identity.comment or "(none)",
            identity.key_type,
            identity.fingerprint,
            str(identity.local_path or "(not found)"),
        )
    console.print(Panel(table, title="[bold yellow]Keys to unload[/bold yellow]"))
    if not typer.confirm(
        f"Remove all {len(identities)} keys from ssh-agent?", default=False
    ):
        console.print("No changes made.")
        raise typer.Exit()

    remove_process = subprocess.run(
        ["ssh-add", "-D"],
        capture_output=True,
        text=True,
        check=False,
    )
    if remove_process.returncode != 0:
        console.print("[red]Could not unload all keys.[/red]")
        if remove_process.stderr.strip():
            console.print(f"[dim]{remove_process.stderr.strip()}[/dim]")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Removed {len(identities)} keys from ssh-agent.")


@app.command("generate-key")
def generate_key():
    """Generate a new SSH key."""
    check_for_command("ssh-keygen")

    key_name = typer.prompt("Key filename", default="id_ed25519").strip()
    if (
        not key_name
        or key_name in {".", ".."}
        or Path(key_name).name != key_name
        or Path(key_name).is_absolute()
    ):
        console.print(
            "[red]Key filename must be one filename without directory components.[/red]"
        )
        raise typer.Exit(1)

    ssh_dir = Path.home() / ".ssh"
    key_path = ssh_dir / key_name

    if key_path.exists() or Path(f"{key_path}.pub").exists():
        console.print(f"[red]Key file '{key_path}' already exists.[/red]")
        raise typer.Exit(1)

    key_type_selection = _fzf_select(
        [
            (
                "ed25519",
                "ed25519  [recommended]",
                "Modern default with small keys and fast operations.",
            ),
            (
                "ecdsa",
                "ecdsa",
                "Use ECDSA when a system or policy specifically requires it.",
            ),
            (
                "rsa",
                "rsa",
                "Use RSA for compatibility with systems that do not support Ed25519.",
            ),
        ],
        prompt="Key type > ",
        header="↑/↓: move  Enter: select  ESC: cancel",
    )
    if not key_type_selection:
        console.print("No changes made.")
        raise typer.Exit()
    key_type = key_type_selection[0]
    comment = typer.prompt("Key comment (optional)", default="", show_default=False).strip()
    protect_key = typer.confirm("Protect the private key with a passphrase?", default=True)

    command = ["ssh-keygen", "-t", key_type, "-C", comment, "-f", str(key_path)]
    if not protect_key:
        console.print("[yellow]The private key will not have a passphrase.[/yellow]")
        if not typer.confirm("Generate an unencrypted private key?", default=False):
            console.print("No changes made.")
            raise typer.Exit()
        command.extend(["-N", ""])
    else:
        console.print("[dim]ssh-keygen will securely prompt for the passphrase twice.[/dim]")

    try:
        ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        ssh_dir.chmod(0o700)
        subprocess.run(command, check=True)
        fingerprint_process = subprocess.run(
            ["ssh-keygen", "-l", "-f", str(key_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        summary = Table(show_header=False, box=None, pad_edge=False)
        summary.add_column("Field", style="bold")
        summary.add_column("Value")
        summary.add_row("Private key", str(key_path))
        summary.add_row("Public key", f"{key_path}.pub")
        summary.add_row("Type", key_type)
        summary.add_row("Passphrase", "protected" if protect_key else "none")
        if fingerprint_process.returncode == 0:
            parsed = _parse_keygen_listing(fingerprint_process.stdout.strip())
            if parsed:
                summary.add_row("Fingerprint", parsed[1])
        console.print(
            Panel(summary, title="[bold green]✓ SSH key generated[/bold green]")
        )
        console.print(f"Next: [cyan]ssh-add {shlex.quote(str(key_path))}[/cyan]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to generate key: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        raise typer.Exit(1)


@app.command("remove-known-host")
def remove_known_host():
    """Interactively remove SSH host entries from ~/.ssh/known_hosts."""
    check_for_command("fzf")
    check_for_command("ssh-keygen")

    hosts_file = Path.home() / ".ssh" / "known_hosts"
    if not hosts_file.is_file():
        console.print("[green]No known_hosts file found. Nothing to do.[/green]")
        raise typer.Exit()

    if not os.access(hosts_file, os.W_OK):
        console.print("[red]Cannot write to known_hosts file. Check permissions.[/red]")
        raise typer.Exit(1)

    # Keep each source line so the user can review the exact entries first.
    hosts: dict[str, list[tuple[int, str, str]]] = {}
    order: list[str] = []
    with hosts_file.open("r") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            host, key_type = parts[0], parts[1]
            if host not in hosts:
                hosts[host] = []
                order.append(host)
            hosts[host].append((line_number, key_type, line.rstrip()))

    if not order:
        console.print("[green]No hosts found in known_hosts file.[/green]")
        raise typer.Exit()

    choice_lines = []
    for host in order:
        key_types = ", ".join(dict.fromkeys(entry[1] for entry in hosts[host]))
        entry_label = "entry" if len(hosts[host]) == 1 else "entries"
        choice_lines.append(
            f"{host}\t{host}  [{key_types}]  ({len(hosts[host])} {entry_label})"
        )

    preview_command = (
        "awk -v host={1} "
        "'$1 == host {printf \"Line %d\\n  %s\\n\\n\", NR, $0}' "
        f"{shlex.quote(str(hosts_file))}"
    )
    selection_process = subprocess.run(
        [
            "fzf",
            "--multi",
            "--height=80%",
            "--layout=reverse",
            "--border=rounded",
            "--delimiter=\\t",
            "--with-nth=2",
            "--prompt=Remove host(s) > ",
            "--header=TAB/Shift-TAB: select  Enter: review  ESC: cancel",
            "--preview-window=right:60%:wrap:border-left",
            f"--preview={preview_command}",
        ],
        input="\n".join(choice_lines),
        capture_output=True,
        text=True,
        check=False,
    )
    if selection_process.returncode in {1, 130}:
        console.print("No hosts selected. Aborting.")
        raise typer.Exit()
    if selection_process.returncode != 0:
        console.print("[red]fzf could not open the host selector.[/red]")
        if selection_process.stderr.strip():
            console.print(f"[dim]{selection_process.stderr.strip()}[/dim]")
        raise typer.Exit(1)

    selections = [
        line.split("\t", maxsplit=1)[0]
        for line in selection_process.stdout.splitlines()
        if line
    ]

    if not selections:
        console.print("No hosts selected. Aborting.")
        raise typer.Exit()

    review = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    review.add_column("Host", style="bold cyan", no_wrap=True)
    review.add_column("Line", justify="right", style="dim")
    review.add_column("Key type", style="magenta")
    review.add_column("Key data / comment", overflow="fold")
    for selected_host in selections:
        for line_number, key_type, source_line in hosts[selected_host]:
            parts = source_line.split(maxsplit=2)
            detail = parts[2] if len(parts) == 3 else ""
            review.add_row(selected_host, str(line_number), key_type, detail)

    entry_count = sum(len(hosts[selected_host]) for selected_host in selections)
    console.print()
    console.print(
        Panel(
            review,
            title="[bold]Review entries to remove[/bold]",
            subtitle=(
                f"{len(selections)} {'host' if len(selections) == 1 else 'hosts'}, "
                f"{entry_count} {'entry' if entry_count == 1 else 'entries'}"
            ),
            border_style="yellow",
        )
    )
    if not typer.confirm("Remove these entries?", default=False):
        console.print("No changes made.")
        raise typer.Exit()

    backup_file = hosts_file.with_name(
        f"{hosts_file.name}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    try:
        shutil.copy2(hosts_file, backup_file)
    except OSError as error:
        console.print(f"[bold red]Could not create backup:[/] {error}")
        console.print("No hosts were removed.")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Backup: [cyan]{backup_file}[/cyan]")

    # Cleanup old backups
    backup_dir = hosts_file.parent
    backups = sorted(
        backup_dir.glob(f"{hosts_file.name}.bak.*"),
        key=os.path.getmtime,
        reverse=True,
    )
    expired_backups = backups[KNOWN_HOSTS_BACKUPS_TO_KEEP:]
    cleanup_failures: list[Path] = []
    for old_backup in expired_backups:
        try:
            old_backup.unlink()
        except OSError:
            cleanup_failures.append(old_backup)
    if expired_backups and not cleanup_failures:
        console.print(
            f"[dim]Removed {len(expired_backups)} old "
            f"{'backup' if len(expired_backups) == 1 else 'backups'}; "
            f"kept the newest {KNOWN_HOSTS_BACKUPS_TO_KEEP}.[/dim]"
        )
    elif cleanup_failures:
        console.print(
            f"[yellow]Warning: could not remove {len(cleanup_failures)} old "
            f"{'backup' if len(cleanup_failures) == 1 else 'backups'}.[/yellow]"
        )

    # Remove hosts
    removed_count = 0
    failed_count = 0
    for host_to_remove in selections:
        try:
            # We need to suppress the output of ssh-keygen
            subprocess.run(
                ["ssh-keygen", "-R", host_to_remove, "-f", str(hosts_file)],
                capture_output=True,
                check=True,
                text=True,
            )
            console.print(f"[green]✓[/green] Removed {host_to_remove}")
            removed_count += 1
        except subprocess.CalledProcessError as e:
            console.print(f"[red]✗ Failed:[/] {host_to_remove}")
            if e.stderr.strip():
                console.print(f"  [dim]{e.stderr.strip()}[/dim]")
            failed_count += 1

    console.print()
    summary_style = "bold green" if failed_count == 0 else "bold yellow"
    console.print(
        f"[{summary_style}]Removed {removed_count} of {len(selections)} selected "
        f"{'host' if len(selections) == 1 else 'hosts'}.[/]"
    )
    if failed_count > 0:
        console.print(f"Restore from [cyan]{backup_file}[/cyan] if needed.")
        raise typer.Exit(1)


@app.command("fix-permissions")
def fix_permissions(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show required changes without applying them",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply changes without an interactive confirmation",
    ),
) -> None:
    """Preview and repair permissions for recognized SSH files."""
    check_for_command("ssh-keygen")
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        console.print(f"[yellow]{ssh_dir} does not exist.[/yellow]")
        if dry_run:
            console.print("Would create it with mode 0700.")
            raise typer.Exit()
        if not apply and not typer.confirm(
            f"Create {ssh_dir} with mode 0700?", default=False
        ):
            console.print("No changes made.")
            raise typer.Exit()
        ssh_dir.mkdir(mode=0o700, parents=True)
        console.print(f"[green]✓[/green] Created {ssh_dir} with mode 0700.")
        raise typer.Exit()

    changes: list[tuple[Path, int, int, str]] = []
    skipped: list[Path] = []

    directory_mode = stat.S_IMODE(ssh_dir.stat().st_mode)
    if directory_mode != 0o700:
        changes.append((ssh_dir, directory_mode, 0o700, "SSH directory"))

    for path in sorted(ssh_dir.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_symlink() or not path.is_file():
            continue
        target_mode: Optional[int] = None
        reason = ""
        if path.name in {"config", "authorized_keys"}:
            target_mode = 0o600
            reason = "private SSH configuration"
        elif path.name.startswith("known_hosts"):
            target_mode = 0o644
            reason = "known host public keys"
        elif path.name.endswith(".pub"):
            target_mode = 0o644
            reason = "public key"
        else:
            key_probe = subprocess.run(
                ["ssh-keygen", "-l", "-f", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if key_probe.returncode == 0:
                target_mode = 0o600
                reason = "private key"

        if target_mode is None:
            skipped.append(path)
            continue
        current_mode = stat.S_IMODE(path.stat().st_mode)
        if current_mode != target_mode:
            changes.append((path, current_mode, target_mode, reason))

    if not changes:
        console.print("All SSH files already have correct permissions.")
        if skipped:
            console.print(f"[dim]Skipped {len(skipped)} unrecognized files.[/dim]")
        raise typer.Exit()

    table = Table("Path", "Current", "Target", "Classification")
    for path, current_mode, target_mode, reason in changes:
        table.add_row(str(path), f"{current_mode:04o}", f"{target_mode:04o}", reason)
    console.print(
        Panel(
            table,
            title="[bold yellow]Permission changes[/bold yellow]",
            subtitle=f"{len(changes)} {'item' if len(changes) == 1 else 'items'}",
        )
    )
    if skipped:
        console.print(
            f"[dim]Skipped {len(skipped)} unrecognized files; their modes will not change.[/dim]"
        )
    if dry_run:
        console.print("Dry run: no changes made.")
        raise typer.Exit()
    if not apply and not typer.confirm("Apply these permission changes?", default=False):
        console.print("No changes made.")
        raise typer.Exit()

    failures = []
    for path, _current_mode, target_mode, _reason in changes:
        try:
            path.chmod(target_mode)
            console.print(f"[green]✓[/green] {path} → {target_mode:04o}")
        except OSError as error:
            failures.append((path, error))
            console.print(f"[red]✗[/red] {path}: {error}")
    if failures:
        console.print(f"[red]{len(failures)} permission changes failed.[/red]")
        raise typer.Exit(1)
    console.print(f"[bold green]Updated {len(changes)} items.[/bold green]")


if __name__ == "__main__":
    app()
