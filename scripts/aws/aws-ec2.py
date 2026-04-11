#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3",
#     "rich",
#     "typer",
#     "pyyaml",
# ]
# bin-name = "aws-ec2"
# ///

"""EC2 helpers such as locating the key pair file for an instance."""

from __future__ import annotations

import os
import re
import shlex
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
import typer

console = Console()
app = typer.Typer(help="EC2 utilities.")


class AppState:
    """Hold shared CLI state."""

    def __init__(self, profile: str, region: str) -> None:
        self.profile = profile
        self.region = region

INSTANCE_ID_PATTERN = re.compile(r"^i-[0-9a-fA-F]{8,17}$")


def iter_instances(response: dict) -> Iterable[dict]:
    """Yield instance dictionaries from a describe_instances response."""
    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            yield instance


def create_ec2_client(profile: str | None, region: str | None):
    """Return a boto3 EC2 client for the given profile and region."""
    session_kwargs: dict[str, str] = {}
    if profile:
        session_kwargs["profile_name"] = profile

    session = boto3.Session(**session_kwargs)
    return session.client("ec2", region_name=region)


def resolve_profile(profile: str | None) -> str:
    """Return the AWS profile or exit when missing."""
    resolved = profile or os.environ.get("AWS_PROFILE")
    if not resolved:
        console.print("[red]Set an AWS profile via --profile or AWS_PROFILE.[/red]")
        raise typer.Exit(1)
    return resolved


def resolve_region(region: str | None) -> str:
    """Return the AWS region or exit when missing."""
    resolved = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not resolved:
        console.print("[red]Set an AWS region via --region, AWS_REGION, or AWS_DEFAULT_REGION.[/red]")
        raise typer.Exit(1)
    return resolved


@app.callback()
def main(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        envvar="AWS_PROFILE",
        help="AWS profile name.",
    ),
    region: str | None = typer.Option(
        None,
        "--region",
        "-r",
        envvar=["AWS_REGION", "AWS_DEFAULT_REGION"],
        help="AWS region.",
    ),
) -> None:
    """Global options shared by subcommands."""
    resolved_profile = resolve_profile(profile)
    resolved_region = resolve_region(region)
    ctx.obj = AppState(profile=resolved_profile, region=resolved_region)


def collect_instances(client, filters: list[dict[str, Any]] | None = None) -> list[dict]:
    """Return all instances matching optional filters."""
    paginator = client.get_paginator("describe_instances")
    instances: list[dict] = []
    # IAM actions: ec2:DescribeInstances
    for page in paginator.paginate(**({"Filters": filters} if filters else {})):
        instances.extend(iter_instances(page))
    return instances


def find_key_name(client, identifier: str, status: Status | None = None) -> str | None:
    """Return the key name for an instance id or Name tag."""
    key_names: set[str] = set()

    if INSTANCE_ID_PATTERN.match(identifier):
        if status:
            status.update("Fetching instance by id from EC2")
        try:
            # IAM actions: ec2:DescribeInstances
            response = client.describe_instances(InstanceIds=[identifier])
        except ClientError as exc:
            raise RuntimeError(exc) from exc
        for instance in iter_instances(response):
            key_name = instance.get("KeyName")
            if key_name:
                key_names.add(key_name)
    else:
        if status:
            status.update("Scanning instances by Name tag")
        try:
            paginator = client.get_paginator("describe_instances")
            # IAM actions: ec2:DescribeInstances
            pages = paginator.paginate()
        except ClientError as exc:
            raise RuntimeError(exc) from exc

        for page in pages:
            for instance in iter_instances(page):
                tags = instance.get("Tags", [])
                name_tags = [
                    tag.get("Value", "") for tag in tags if tag.get("Key") == "Name"
                ]
                if any(tag_value.lower() == identifier.lower() for tag_value in name_tags):
                    key_name = instance.get("KeyName")
                    if key_name:
                        key_names.add(key_name)

    if not key_names:
        return None

    return sorted(key_names)[0]


def locate_key_file(key_name: str, search_root: Path) -> Path | None:
    """Return the first matching key file under the search root."""
    if not search_root.exists():
        return None

    wanted_names = {
        key_name.lower(),
        f"{key_name.lower()}.pem",
        f"{key_name.lower()}.key",
    }

    try:
        for path in search_root.rglob("*"):
            if path.is_file() and path.name.lower() in wanted_names:
                return path.resolve()
    except PermissionError:
        return None

    return None


def format_shell_path(path: Path) -> str:
    """Return a shell-escaped path string."""
    return shlex.quote(str(path))


def normalize(value: Any) -> Any:
    """Convert EC2 response objects to JSON/YAML-friendly values."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize(v) for v in value]
    return str(value)


def instance_name(instance: dict) -> str:
    """Return the Name tag value if present."""
    for tag in instance.get("Tags", []):
        if tag.get("Key") == "Name":
            return str(tag.get("Value", ""))
    return ""


def instance_os(instance: dict) -> str:
    """Return a short OS label based on platform details."""
    platform_details = instance.get("PlatformDetails")
    if platform_details:
        return str(platform_details)
    platform = instance.get("Platform")
    if platform:
        return str(platform)
    return "Unknown"


def instance_iam_role(instance: dict) -> str:
    """Return the IAM role name from the instance profile ARN."""
    profile = instance.get("IamInstanceProfile") or {}
    arn = profile.get("Arn") if isinstance(profile, dict) else None
    if not arn:
        return ""
    return arn.rsplit("/", 1)[-1]


def instance_security_groups(instance: dict) -> str:
    """Return a comma-separated list of security groups."""
    groups = instance.get("SecurityGroups", [])
    if not groups:
        return ""
    formatted = []
    for group in groups:
        name = group.get("GroupName", "")
        gid = group.get("GroupId", "")
        if name and gid:
            formatted.append(f"{name} ({gid})")
        else:
            formatted.append(name or gid)
    return ", ".join(formatted)


def build_instance_row(instance: dict) -> list[str]:
    """Return formatted row fields for list output."""
    return [
        instance_name(instance),
        instance.get("InstanceId", ""),
        instance.get("State", {}).get("Name", ""),
        instance.get("InstanceType", ""),
        instance_os(instance),
        instance.get("KeyName", ""),
        instance.get("PublicIpAddress", "") or "",
        instance.get("PrivateIpAddress", "") or "",
    ]


@app.command("list")
def list_instances(
    ctx: typer.Context,
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Substring match on the Name tag (case-insensitive).",
    ),
    state: str | None = typer.Option(
        None,
        "--state",
        help="Filter by instance-state-name (running, stopped, pending, etc.).",
    ),
) -> None:
    """List EC2 instances in a table."""
    state_obj = ctx.ensure_object(AppState)
    filters: list[dict[str, Any]] = []
    if name:
        filters.append({"Name": "tag:Name", "Values": [f"*{name}*"]})
    if state:
        filters.append({"Name": "instance-state-name", "Values": [state]})

    try:
        client = create_ec2_client(profile=state_obj.profile, region=state_obj.region)
    except Exception as exc:  # pragma: no cover - boto initialization errors
        console.print(f"[red]Could not build EC2 client:[/red] {exc}")
        raise typer.Exit(1) from exc

    with console.status("Fetching instances...", spinner="dots"):
        try:
            instances = collect_instances(client, filters=filters)
        except (RuntimeError, BotoCoreError, ClientError) as exc:
            console.print(f"[red]EC2 lookup failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    if not instances:
        console.print("[yellow]No instances found.[/yellow]")
        raise typer.Exit(0)

    table = Table(
        "Name",
        "Id",
        "State",
        "Type",
        "OS",
        "Key",
        "Public IP",
        "Private IP",
        show_lines=False,
    )
    for instance in instances:
        table.add_row(*build_instance_row(instance))

    console.print(table)
    console.print(f"[dim]{len(instances)} instance(s)[/dim]")


@app.command("describe")
def describe_instance(
    ctx: typer.Context,
    identifier: str = typer.Argument(
        ..., help="Instance id (i-xxxx) or Name tag substring."
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        case_sensitive=False,
        help="Output format: table, json, yaml.",
        show_choices=True,
        show_default=True,
    ),
) -> None:
    """Show raw EC2 instance details as JSON."""
    state_obj = ctx.ensure_object(AppState)
    use_id_lookup = INSTANCE_ID_PATTERN.match(identifier) is not None

    try:
        client = create_ec2_client(profile=state_obj.profile, region=state_obj.region)
    except Exception as exc:  # pragma: no cover - boto initialization errors
        console.print(f"[red]Could not build EC2 client:[/red] {exc}")
        raise typer.Exit(1) from exc

    if use_id_lookup:
        describe_kwargs = {"InstanceIds": [identifier]}
    else:
        describe_kwargs = {"Filters": [{"Name": "tag:Name", "Values": [f"*{identifier}*"]}]}

    with console.status("Fetching instance details...", spinner="dots"):
        try:
            # IAM actions: ec2:DescribeInstances
            response = client.describe_instances(**describe_kwargs)
            instances = list(iter_instances(response))
        except (RuntimeError, BotoCoreError, ClientError) as exc:
            console.print(f"[red]EC2 lookup failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    if not instances:
        console.print(f"[yellow]No instances found for '{identifier}'.[/yellow]")
        raise typer.Exit(1)

    if len(instances) > 1 and not use_id_lookup:
        summary = Table("Name", "Id", "State", "Type")
        for instance in instances:
            summary.add_row(
                instance_name(instance),
                instance.get("InstanceId", ""),
                instance.get("State", {}).get("Name", ""),
                instance.get("InstanceType", ""),
            )
        console.print(summary)
        console.print(
            "[yellow]Multiple matches. Refine the name filter or use an instance id.[/yellow]"
        )
        raise typer.Exit(1)

    instance = instances[0]
    fmt = output_format.lower()

    if fmt == "table":
        summary = Table(show_header=False, title="EC2 instance")
        summary.add_row("Name", instance_name(instance))
        summary.add_row("Id", instance.get("InstanceId", ""))
        summary.add_row("State", instance.get("State", {}).get("Name", ""))
        summary.add_row("Type", instance.get("InstanceType", ""))
        summary.add_row("OS", instance_os(instance))
        summary.add_row("AMI", instance.get("ImageId", ""))
        summary.add_row("AZ", instance.get("Placement", {}).get("AvailabilityZone", ""))
        summary.add_row("Key", instance.get("KeyName", ""))
        summary.add_row("IAM role", instance_iam_role(instance))
        summary.add_row("Private IP", instance.get("PrivateIpAddress", "") or "")
        summary.add_row("Private DNS", instance.get("PrivateDnsName", "") or "")
        summary.add_row("Public IP", instance.get("PublicIpAddress", "") or "")
        summary.add_row("VPC", instance.get("VpcId", ""))
        summary.add_row("Subnet", instance.get("SubnetId", ""))
        summary.add_row("Security groups", instance_security_groups(instance))
        summary.add_row("Launch", str(instance.get("LaunchTime", "")))
        console.print(summary)
        return

    normalized = normalize(instance)

    if fmt == "json":
        console.print_json(json.dumps(normalized, indent=2))
    elif fmt == "yaml":
        console.print(yaml.safe_dump(normalized, sort_keys=False))
    else:
        console.print(f"[red]Unknown format '{output_format}'.[/red]")
        raise typer.Exit(1)


@app.command("find-key")
def find_key(
    ctx: typer.Context,
    identifier: str = typer.Argument(
        ..., help="Instance id (i-xxxx) or Name tag to inspect."
    ),
    keys_dir: Path | None = typer.Option(
        None,
        "--keys-dir",
        envvar="AWS_EC2_KEY_DIR",
        file_okay=False,
        dir_okay=True,
        exists=False,
        writable=False,
        resolve_path=True,
        help="Directory to search for key files (or set AWS_EC2_KEY_DIR).",
    ),
    key_file_only: bool = typer.Option(
        False,
        "--key-file-only",
        help="Print only the key file path if found.",
    ),
) -> None:
    """Find the EC2 key pair name and matching local file."""
    state = ctx.ensure_object(AppState)

    if keys_dir is None:
        console.print("[red]AWS_EC2_KEY_DIR is not set. Export it or pass --keys-dir.[/red]")
        raise typer.Exit(1)

    try:
        client = create_ec2_client(profile=state.profile, region=state.region)
    except Exception as exc:  # pragma: no cover - boto initialization errors
        console.print(f"[red]Could not build EC2 client:[/red] {exc}")
        raise typer.Exit(1) from exc

    with console.status("Looking up EC2 key pair...", spinner="dots") as status:
        try:
            key_name = find_key_name(client, identifier, status=status)
        except (RuntimeError, BotoCoreError, ClientError) as exc:
            console.print(f"[red]EC2 lookup failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    if not key_name:
        if key_file_only:
            raise typer.Exit(1)
        console.print(f"[yellow]No key name found for '{identifier}'.[/yellow]")
        raise typer.Exit(1)

    key_path = locate_key_file(key_name, keys_dir)

    if key_path:
        if key_file_only:
            console.print(format_shell_path(key_path))
            raise typer.Exit(0)
        panel = Panel.fit(
            f"[bold green]{key_name}[/bold green]\n{format_shell_path(key_path)}",
            title="Key found",
            style="green",
        )
        console.print(panel)
        console.print(f"[green]Key file:[/green] {format_shell_path(key_path)}")
        return
    elif key_file_only:
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[yellow]{key_name}[/yellow]\nNo key file found under {keys_dir}.",
            title="Key name found",
            style="yellow",
        )
    )
    console.print("Try a different directory with --keys-dir.")
    raise typer.Exit(1)


def run() -> None:
    """Entrypoint for Typer."""
    app()


if __name__ == "__main__":
    run()
