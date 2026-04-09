#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "boto3",
#   "rich",
#   "typer",
# ]
# ///
"""Locate a private IP across all AWS profiles and US regions."""

import concurrent.futures
import ipaddress
import logging
from configparser import ConfigParser
from functools import lru_cache
from pathlib import Path

import boto3
import typer
from botocore.exceptions import BotoCoreError, ClientError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

REGIONS = ["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

console = Console()
app = typer.Typer(add_completion=False)


def get_profiles() -> list[str]:
    """Read profiles from ~/.aws/config, skipping -do (write/admin) variants."""
    config_path = Path.home() / ".aws" / "config"
    if not config_path.exists():
        console.print("[red]~/.aws/config not found[/red]")
        raise typer.Exit(1)

    cp = ConfigParser()
    cp.read(config_path)

    profiles = []
    for section in cp.sections():
        # Sections are "profile <name>" for named profiles, or "default"
        if section == "default":
            name = "default"
        elif section.startswith("profile "):
            name = section[len("profile "):].strip()
        else:
            continue  # skip unknown section types (e.g. [sso-session ...])
        if not name.endswith("-do"):
            profiles.append(name)
    return profiles


@lru_cache(maxsize=None)
def get_account_id(profile: str) -> str:
    """Resolve AWS account ID for a profile, returning 'unknown' on failure."""
    try:
        session = boto3.Session(profile_name=profile)
        sts = session.client("sts", region_name="us-east-1")
        return sts.get_caller_identity()["Account"]
    except (BotoCoreError, ClientError):
        return "unknown"


def search_profile_region(ip: str, profile: str, region: str) -> dict | None:
    """Return parsed ENI info dict if found, else None."""
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        ec2 = session.client("ec2")
        resp = ec2.describe_network_interfaces(
            Filters=[{"Name": "private-ip-address", "Values": [ip]}]
        )
    except (BotoCoreError, ClientError):
        return None

    interfaces = resp.get("NetworkInterfaces", [])
    if not interfaces:
        return None

    eni = interfaces[0]
    attachment = eni.get("Attachment", {})
    tags = {t["Key"]: t["Value"] for t in eni.get("TagSet", [])}
    sgs = ", ".join(f"{g['GroupName']} ({g['GroupId']})" for g in eni.get("Groups", []))

    result = {
        "ip": ip,
        "profile": profile,
        "account": get_account_id(profile),
        "region": region,
        "az": eni.get("AvailabilityZone", "N/A"),
        "description": eni.get("Description", "N/A"),
        "name_tag": tags.get("Name", ""),
        "type": eni.get("InterfaceType", "N/A"),
        "owner": attachment.get("InstanceOwnerId", "N/A"),
        "eni": eni.get("NetworkInterfaceId", "N/A"),
        "vpc": eni.get("VpcId", "N/A"),
        "subnet": eni.get("SubnetId", "N/A"),
        "sgs": sgs or "N/A",
        "status": eni.get("Status", "N/A"),
        "attached": attachment.get("AttachTime", "N/A"),
    }

    # Normalize datetime to ISO string so the dict is always JSON-safe
    if hasattr(result["attached"], "isoformat"):
        result["attached"] = result["attached"].isoformat()

    return result


def render_result(hit: dict) -> None:
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value", style="white")

    rows = [
        ("IP", hit["ip"]),
        ("What", hit["description"]),
        ("Type", hit["type"]),
        ("ENI Owner", hit["owner"]),
        ("Profile", hit["profile"]),
        ("Account", hit["account"]),
        ("Region / AZ", f"{hit['region']} / {hit['az']}"),
        ("ENI", hit["eni"]),
        ("VPC", hit["vpc"]),
        ("Subnet", hit["subnet"]),
        ("Security Grp", hit["sgs"]),
        ("Status", hit["status"]),
        ("Attached", hit["attached"]),
    ]

    if hit["name_tag"]:
        rows.insert(2, ("Name Tag", hit["name_tag"]))

    for field, value in rows:
        table.add_row(field, value)

    console.print(
        Panel(
            table,
            title=f"[bold green]Found: {hit['ip']}[/bold green]",
            border_style="green",
            expand=False,
        )
    )


@app.command()
def main(
    ip: str = typer.Argument(..., help="Private IP address to search for"),
    workers: int = typer.Option(20, "--workers", "-w", help="Max parallel workers"),
):
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        console.print(f"[red]Invalid IP address: {ip!r}[/red]")
        raise typer.Exit(1)

    profiles = get_profiles()
    tasks = [(ip, profile, region) for profile in profiles for region in REGIONS]
    total = len(tasks)

    console.print(
        f"Searching [bold]{ip}[/bold] across "
        f"[cyan]{len(profiles)}[/cyan] profiles × "
        f"[cyan]{len(REGIONS)}[/cyan] regions "
        f"([dim]{total} checks[/dim])...\n"
    )

    hits: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning...", total=total)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(search_profile_region, *args): args for args in tasks
            }
            for fut in concurrent.futures.as_completed(futures):
                progress.advance(task)
                try:
                    result = fut.result()
                except Exception as exc:
                    args = futures[fut]
                    logging.debug("Unhandled error for %s/%s: %s", args[1], args[2], exc)
                    result = None
                if result:
                    hits.append(result)

    if not hits:
        console.print(f"[red]No ENI found for {ip} in any profile or US region.[/red]")
        raise typer.Exit(1)

    for hit in hits:
        render_result(hit)


if __name__ == "__main__":
    app()
