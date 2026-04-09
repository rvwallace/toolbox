#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "rich",
#     "typer",
#     "InquirerPy",
# ]
# bin-name = "ssh-sc"
# ///

"""SSH helper script for managing keys and known_hosts."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
except ImportError:
    print("InquirerPy is not installed. Please run 'uv pip sync' in your project root.")
    # Exit with a non-zero code to indicate an error
    exit(1)

app = typer.Typer(help="SSH helper script.")
console = Console()
FUZZY_KEYBINDINGS = {"interrupt": [{"key": "c-c"}, {"key": "escape"}]}


def check_for_command(command: str):
    """Check if a command exists."""
    if not shutil.which(command):
        console.print(f"[red]Error: '{command}' is not installed or not in your PATH.[/red]")
        raise typer.Exit(1)


def _get_private_key_files() -> list[str]:
    """Return a list of private key files in the .ssh directory."""
    ssh_path = Path.home() / ".ssh"
    key_files: list[str] = []
    if not ssh_path.is_dir():
        return []

    for path in ssh_path.iterdir():
        if not path.is_file():
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
        if probe.returncode == 0:
            key_files.append(str(path))
    return key_files


def _select_key(query: Optional[str]) -> Optional[str]:
    """Uses a fuzzy prompt to select an SSH key, returns the path."""
    check_for_command("ssh-keygen")
    key_files = _get_private_key_files()
    if query:
        lowered_query = query.lower()
        key_files = [k for k in key_files if lowered_query in k.lower()]
    if not key_files:
        console.print("[yellow]No private key files found.[/yellow]")
        return None

    choices = [
        Choice(value=path, name=Path(path).name)
        for path in key_files
    ]

    try:
        selected_key = inquirer.fuzzy(
            message="Select an SSH key:",
            choices=choices,
            default=query or "",
            long_instruction="CTRL-C or ESC to quit",
            border=True,
            height="40%",
            keybindings=FUZZY_KEYBINDINGS,
        ).execute()
        return selected_key

    except KeyboardInterrupt:
        return None
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        raise typer.Exit(1)


def _extract_fingerprint(line: str) -> Optional[str]:
    """Return the fingerprint field from ssh-add or ssh-keygen output."""
    parts = line.split()
    if len(parts) < 2:
        return None
    return parts[1]


@app.callback()
def main():
    """SSH script commands."""
    pass


@app.command("list-keys")
def list_keys(
    query: Optional[str] = typer.Argument(None, help="Optional initial query filter"),
) -> None:
    """List and select SSH private keys."""
    selected_key = _select_key(query)

    if selected_key:
        console.print(f"Selected key: {selected_key}")
        fingerprint_process = subprocess.run(
            ["ssh-keygen", "-l", "-f", selected_key],
            capture_output=True,
            text=True,
            check=False,
        )
        if fingerprint_process.returncode == 0:
            console.print(f"Fingerprint: {fingerprint_process.stdout.strip()}")
        else:
            console.print("[yellow]Could not get key fingerprint.[/yellow]")
    else:
        console.print("No key selected.")


@app.command("add-key")
def add_key(
    query: Optional[str] = typer.Argument(None, help="Optional initial query filter"),
) -> None:
    """Add an SSH key to the ssh-agent."""
    check_for_command("ssh-add")

    if "SSH_AUTH_SOCK" not in os.environ:
        console.print("[yellow]SSH_AUTH_SOCK is not set. Starting ssh-agent...[/yellow]")
        try:
            agent_output = subprocess.check_output(["ssh-agent", "-s"], text=True)
            for line in agent_output.splitlines():
                if "SSH_AUTH_SOCK" in line or "SSH_AGENT_PID" in line:
                    key, value = line.rstrip(";").split(";")[0].split("=")
                    os.environ[key] = value
            console.print("[green]Started ssh-agent.[/green]")
        except Exception:
            console.print("[red]Failed to start ssh-agent automatically. Please start it manually.[/red]")
            raise typer.Exit(1)

    selected_key = _select_key(query)

    if selected_key:
        try:
            subprocess.run(["ssh-add", selected_key], check=True)
            console.print(f"Key added: {selected_key}")
        except subprocess.CalledProcessError:
            console.print(f"[red]Failed to add key: {selected_key}[/red]")
            raise typer.Exit(1)
    else:
        console.print("No key selected.")


@app.command("unload-key")
def unload_key():
    """Remove a specific key from ssh-agent."""
    check_for_command("ssh-add")
    check_for_command("ssh-keygen")

    try:
        # Get loaded keys
        loaded_keys_process = subprocess.run(
            ["ssh-add", "-l"], capture_output=True, text=True, check=True
        )
        loaded_keys_output = loaded_keys_process.stdout.strip()
        if not loaded_keys_output:
            console.print("No keys loaded in ssh-agent.")
            raise typer.Exit()
        
        loaded_keys = loaded_keys_output.split("\n")

        # Map fingerprints to local key file paths for display
        private_keys = _get_private_key_files()
        fingerprint_to_file: dict[str, str] = {}
        for key_file in private_keys:
            if not key_file:
                continue
            fingerprint_process = subprocess.run(
                ["ssh-keygen", "-l", "-f", key_file],
                capture_output=True, text=True, check=False,
            )
            if fingerprint_process.returncode == 0:
                keygen_output = fingerprint_process.stdout.strip().splitlines()[0]
                keygen_fingerprint = _extract_fingerprint(keygen_output)
                if keygen_fingerprint:
                    fingerprint_to_file[keygen_fingerprint] = key_file

        key_choices = []
        for line in loaded_keys:
            fp = _extract_fingerprint(line)
            key_file = fingerprint_to_file.get(fp, "unknown file")
            display = f"{line} [{key_file}]"
            key_choices.append(Choice(value=line, name=display))

        # Use fuzzy prompt to select a key
        selected_key_line = inquirer.fuzzy(
            message="Select a key to remove:",
            choices=key_choices,
            long_instruction="CTRL-C or ESC to quit",
            border=True,
            height="40%",
            keybindings=FUZZY_KEYBINDINGS,
        ).execute()

        if not selected_key_line:
            console.print("No key selected.")
            raise typer.Exit()

        selected_fingerprint = _extract_fingerprint(selected_key_line)
        if not selected_fingerprint:
            console.print("[red]Could not parse fingerprint from selected key.[/red]")
            raise typer.Exit(1)

        # Find the key file
        private_keys = _get_private_key_files()
        key_file_to_remove = None
        for key_file in private_keys:
            if not key_file:
                continue
            fingerprint_process = subprocess.run(
                ["ssh-keygen", "-l", "-f", key_file],
                capture_output=True, text=True, check=False,
            )
            if fingerprint_process.returncode == 0:
                keygen_output = fingerprint_process.stdout.strip().splitlines()[0]
                keygen_fingerprint = _extract_fingerprint(keygen_output)
                if keygen_fingerprint and keygen_fingerprint == selected_fingerprint:
                    key_file_to_remove = key_file
                    break
        
        if key_file_to_remove:
            subprocess.run(["ssh-add", "-d", key_file_to_remove], check=True)
            console.print(f"Key removed: {key_file_to_remove}")
        else:
            console.print("[red]Could not find matching key file to remove.[/red]")

    except KeyboardInterrupt:
        console.print("No key selected.")
        raise typer.Exit()
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error interacting with ssh-agent: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        raise typer.Exit(1)


@app.command("unload-keys")
def unload_keys():
    """Remove all keys from ssh-agent."""
    check_for_command("ssh-add")
    try:
        subprocess.run(["ssh-add", "-D"], check=True)
        console.print("All keys removed from ssh-agent.")
    except subprocess.CalledProcessError:
        console.print("[red]Failed to unload keys.[/red]")
        raise typer.Exit(1)


@app.command("generate-key")
def generate_key():
    """Generate a new SSH key."""
    check_for_command("ssh-keygen")

    key_name = typer.prompt("Enter a name for the key file")
    email = typer.prompt("Enter your email")
    key_type_input = typer.prompt("Enter key type (rsa/ed25519/ecdsa)", default="ed25519")
    key_type = key_type_input.strip().lower()
    allowed_key_types = {"rsa", "ed25519", "ecdsa"}
    if key_type not in allowed_key_types:
        console.print(f"[red]Key type must be one of: {', '.join(sorted(allowed_key_types))}[/red]")
        raise typer.Exit(1)

    key_path = Path.home() / ".ssh" / key_name

    if key_path.exists():
        console.print(f"[red]Key file '{key_path}' already exists.[/red]")
        raise typer.Exit(1)
    
    if not key_name or not email:
        console.print("[red]Key name and email cannot be empty.[/red]")
        raise typer.Exit(1)

    try:
        subprocess.run(
            ["ssh-keygen", "-t", key_type, "-C", email, "-f", str(key_path), "-N", ""],
            check=True,
        )
        console.print(f"Key generated: {key_path}")
        console.print("Public key:")
        with open(f"{key_path}.pub", "r") as f:
            console.print(f.read())
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to generate key: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        raise typer.Exit(1)


@app.command("remove-known-host")
def remove_known_host():
    """Interactively remove SSH host entries from ~/.ssh/known_hosts."""
    check_for_command("ssh-keygen")

    hosts_file = Path.home() / ".ssh" / "known_hosts"
    if not hosts_file.is_file():
        console.print("[green]No known_hosts file found. Nothing to do.[/green]")
        raise typer.Exit()

    if not os.access(hosts_file, os.W_OK):
        console.print("[red]Cannot write to known_hosts file. Check permissions.[/red]")
        raise typer.Exit(1)

    # Generate host list
    hosts: dict[str, list[str]] = {}
    order: list[str] = []
    with hosts_file.open("r") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            host, key_type = parts[0], parts[1]
            if host not in hosts:
                hosts[host] = []
                order.append(host)
            hosts[host].append(key_type)

    host_choices = [
        Choice(value=h, name=f"{h} [{', '.join(hosts[h])}]")
        for h in order
    ]

    if not host_choices:
        console.print("[green]No hosts found in known_hosts file.[/green]")
        raise typer.Exit()

    try:
        selections = inquirer.fuzzy(
            message="Select host(s) to remove:",
            choices=host_choices,
            multiselect=True,
            long_instruction="TAB to mark hosts. Enter to confirm. ESC/CTRL-C to cancel.",
            border=True,
            height="60%",
            keybindings=FUZZY_KEYBINDINGS,
        ).execute()
    except KeyboardInterrupt:
        console.print("No hosts selected. Aborting.")
        raise typer.Exit()

    if not selections:
        console.print("No hosts selected. Aborting.")
        raise typer.Exit()

    # Backup
    backup_file = hosts_file.with_name(f"{hosts_file.name}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy(hosts_file, backup_file)
    console.print(f"Backed up known_hosts to [cyan]{backup_file.name}[/cyan]")
    
    # Cleanup old backups
    backup_dir = hosts_file.parent
    backups = sorted(
        backup_dir.glob(f"{hosts_file.name}.bak.*"),
        key=os.path.getmtime,
        reverse=True,
    )
    for old_backup in backups[5:]:
        old_backup.unlink()

    # Remove hosts
    removed_count = 0
    failed_count = 0
    for host_to_remove in selections:
        try:
            # We need to suppress the output of ssh-keygen
            subprocess.run(
                ["ssh-keygen", "-R", host_to_remove, "-f", str(hosts_file)],
                capture_output=True, check=True, text=True
            )
            console.print(f"[green]Successfully removed:[/] {host_to_remove}")
            removed_count += 1
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to remove host:[/] {host_to_remove}")
            console.print(f"  [dim]{e.stderr}[/dim]")
            failed_count += 1

    console.print(f"Successfully removed {removed_count} host(s)")
    if failed_count > 0:
        console.print(f"{failed_count} host(s) failed to remove", style="bold red")
        raise typer.Exit(1)
    console.print("[bold green]Done[/bold green]")


@app.command("fix-permissions")
def fix_permissions():
    """Fix permissions for ~/.ssh directory and files."""
    ssh_dir = Path.home() / ".ssh"
    fixed_count = 0

    if not ssh_dir.exists():
        ssh_dir.mkdir(0o700)
        console.print(f"Created directory {ssh_dir} with 700 permissions.")
        fixed_count += 1
    
    # Fix .ssh directory permissions
    if ssh_dir.stat().st_mode & 0o777 != 0o700:
        ssh_dir.chmod(0o700)
        console.print(f"Fixed permissions on {ssh_dir}")
        fixed_count += 1

    # Fix file permissions
    for path in ssh_dir.iterdir():
        if path.is_file():
            if path.name.endswith(".pub") or path.name in [
                "known_hosts",
                "authorized_keys",
                "config",
            ]:
                if path.stat().st_mode & 0o777 != 0o644:
                    path.chmod(0o644)
                    console.print(f"Fixed permissions on {path}")
                    fixed_count += 1
            else:  # Assume private key
                if path.stat().st_mode & 0o777 != 0o600:
                    path.chmod(0o600)
                    console.print(f"Fixed permissions on {path}")
                    fixed_count += 1
    
    if fixed_count == 0:
        console.print("All SSH files already have correct permissions.")
    else:
        console.print(f"Fixed permissions on {fixed_count} item(s).")


if __name__ == "__main__":
    app()
