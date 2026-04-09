#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "rich",
# ]
# bin-name = "saml2aws-op"
# ///

"""
Sign in to AWS through JumpCloud with saml2aws and secrets from 1Password.

You can run:
  uv run --script packages/aws/saml2aws_op.py

The script:
  - Pulls JumpCloud username, password, and one-time password (OTP) from the
    1Password CLI (op) when available outside of SSH.
  - Falls back to interactive prompts when you run from SSH or the CLI is missing.
  - Defaults to the `techops` alias but lets you pass a different one.
  - Forwards the alias and extra flags to `saml2aws login`.

You must unlock 1Password in advance so the CLI can read the JumpCloud item.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

DEFAULT_OP_ITEM = "JumpCloud"
DEFAULT_ALIAS = "techops"

console = Console()


def running_over_ssh() -> bool:
    """Return True when the current shell rides over SSH."""
    return any(
        os.environ.get(var) for var in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")
    )


def command_available(command: str) -> bool:
    """Return whether an executable is present in PATH."""
    return shutil.which(command) is not None


def run_op_command(arguments: Sequence[str]) -> str:
    """Execute the 1Password CLI and return stripped stdout."""
    try:
        result = subprocess.run(arguments, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        stdout = (error.stdout or "").strip()
        details = stderr or stdout or "Unknown 1Password CLI error"
        raise RuntimeError(details) from error
    return result.stdout.strip()


def fetch_jumpcloud_credentials(item_name: str) -> tuple[str, str]:
    """Return the JumpCloud username and password from 1Password."""
    username = run_op_command(
        ["op", "item", "get", item_name, "--fields", "label=username"]
    )
    password = run_op_command(
        ["op", "item", "get", item_name, "--fields", "label=password", "--reveal"]
    )
    return username, password


def fetch_jumpcloud_otp(item_name: str) -> str:
    """Return a fresh JumpCloud OTP from 1Password."""
    return run_op_command(["op", "item", "get", item_name, "--otp"])


def prompt_for_credentials() -> tuple[str, str, str]:
    """Prompt for JumpCloud username, password, and OTP."""
    console.print("[yellow]Enter JumpCloud credentials.[/yellow]")
    username = Prompt.ask("Username")
    password = Prompt.ask("Password", password=True)
    otp = Prompt.ask("OTP")
    return username, password, otp


def gather_credentials(item_name: str, allow_op: bool) -> tuple[str, str, str, bool]:
    """Load credentials either from 1Password or interactive prompts.

    Returns:
        username, password, otp, used_1password
    """
    if allow_op and command_available("op"):
        with console.status(
            "Pulling JumpCloud credentials from 1Password...", spinner="dots"
        ):
            try:
                username, password = fetch_jumpcloud_credentials(item_name)
                otp = fetch_jumpcloud_otp(item_name)
                return username, password, otp, True
            except RuntimeError as error:
                console.log(f"[red]1Password lookup failed:[/red] {error}")
                console.print("[yellow]Falling back to interactive prompts.[/yellow]")
    elif allow_op:
        console.print(
            "[yellow]1Password CLI not found. Prompting for credentials.[/yellow]"
        )

    username, password, otp = prompt_for_credentials()
    return username, password, otp, False


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for the wrapper."""
    parser = argparse.ArgumentParser(
        description="Call saml2aws with secrets pulled from 1Password when possible."
    )
    parser.add_argument(
        "alias",
        nargs="?",
        default=DEFAULT_ALIAS,
        help=f"saml2aws profile alias passed to `saml2aws login -a` (default: {DEFAULT_ALIAS}).",
    )
    parser.add_argument(
        "--op-item",
        default=DEFAULT_OP_ITEM,
        help=f"1Password item to read (default: {DEFAULT_OP_ITEM}).",
    )
    return parser


def build_saml2aws_command(
    username: str, password: str, otp: str, alias: str, extra_args: Sequence[str]
) -> list[str]:
    """Construct the saml2aws command."""
    return [
        "saml2aws",
        "--skip-prompt",
        f"--username={username}",
        f"--password={password}",
        f"--mfa-token={otp}",
        "login",
        "--force",
        "-a",
        alias,
        "--mfa=TOTP",
        *extra_args,
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint for the CLI wrapper."""
    parser = build_argument_parser()
    args, saml2aws_args = parser.parse_known_args(argv)

    # console.rule("[bold cyan]saml2aws[/bold cyan]")
    console.log("Logging into AWS via JumpCloud using saml2aws")
    # console.print()

    if not command_available("saml2aws"):
        parser.exit(
            status=1, message="saml2aws not found in PATH. Install it and retry.\n"
        )

    ssh_session = running_over_ssh()
    allow_op = not ssh_session
    if ssh_session:
        console.log(
            "[yellow]SSH session detected. Prompting for JumpCloud credentials.[/yellow]"
        )

    username, password, otp, used_op = gather_credentials(args.op_item, allow_op=allow_op)

    attempt_results: list[tuple[int, subprocess.CompletedProcess[str]]] = []
    max_attempts = 2 if used_op and allow_op else 1

    for attempt in range(1, max_attempts + 1):
        command = build_saml2aws_command(username, password, otp, args.alias, saml2aws_args)

        # IAM actions: wraps saml2aws login which triggers STS AssumeRoleWithSAML.
        console.log(f"[cyan]Running saml2aws login (attempt {attempt})...[/cyan]")
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        attempt_results.append((attempt, result))

        if result.returncode == 0 or attempt == max_attempts:
            break

        console.log("[yellow]Login failed. Fetching a fresh OTP and retrying...[/yellow]")
        try:
            otp = fetch_jumpcloud_otp(args.op_item)
        except RuntimeError as error:
            console.log(f"[red]Could not fetch a new OTP:[/red] {error}")
            break

    panel_sections: list[str] = []
    for attempt, result in attempt_results:
        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        body_parts = [part for part in (stdout_text, stderr_text) if part]
        body = "\n".join(body_parts).strip()
        if not body:
            body = "<no output>"
        panel_sections.append(f"[bold]Attempt {attempt}[/bold]\n{body}")

    console.print(
        Panel.fit(
            "\n\n".join(panel_sections),
            title="saml2aws",
            border_style="cyan",
        )
    )

    final_result = (
        attempt_results[-1][1]
        if attempt_results
        else subprocess.CompletedProcess(args=[], returncode=1)
    )

    # console.print()
    if final_result.returncode == 0:
        console.log(
            "[green]Successfully logged into AWS via JumpCloud using saml2aws.[/green]"
        )
    else:
        console.log("[red]Failed to log into AWS via JumpCloud using saml2aws.[/red]")
    return final_result.returncode


if __name__ == "__main__":
    sys.exit(main())
