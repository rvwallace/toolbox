#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3",
#     "rich",
#     "typer",
#     "pyyaml",
# ]
# bin-name = "aws-eks"
# ///

"""EKS helpers for cluster management."""

from __future__ import annotations

import os
import shlex
import json
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import yaml
from rich.console import Console
from rich.table import Table
import typer


console = Console()
app = typer.Typer(help="EKS cluster utilities.")


class AppState:
    """Hold shared CLI state."""

    def __init__(self, profile: str, region: str) -> None:
        self.profile = profile
        self.region = region


def create_eks_client(profile: str | None, region: str | None):
    """Return a boto3 EKS client for the given profile and region."""
    session_kwargs: dict[str, str] = {}
    if profile:
        session_kwargs["profile_name"] = profile

    session = boto3.Session(**session_kwargs)
    return session.client("eks", region_name=region)


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


def normalize(value: Any) -> Any:
    """Convert response objects to JSON/YAML-friendly values."""
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


@app.command("list")
def list_clusters(ctx: typer.Context) -> None:
    """List EKS clusters and their details."""
    state_obj = ctx.ensure_object(AppState)

    try:
        client = create_eks_client(profile=state_obj.profile, region=state_obj.region)
    except Exception as exc:
        console.print(f"[red]Could not build EKS client:[/red] {exc}")
        raise typer.Exit(1) from exc

    with console.status("Fetching EKS clusters...", spinner="dots"):
        try:
            # IAM action: eks:ListClusters
            response = client.list_clusters()
            cluster_names = response.get("clusters", [])
        except (BotoCoreError, ClientError) as exc:
            console.print(f"[red]EKS lookup failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    if not cluster_names:
        console.print("[yellow]No EKS clusters found.[/yellow]")
        raise typer.Exit(0)

    table = Table("Name", "ARN", "Version", "Status", show_lines=False)
    with console.status("Fetching cluster details...", spinner="dots"):
        for name in cluster_names:
            try:
                # IAM action: eks:DescribeCluster
                response = client.describe_cluster(name=name)
                cluster = response.get("cluster", {})
                if cluster:
                    table.add_row(
                        cluster.get("name", ""),
                        cluster.get("arn", ""),
                        cluster.get("version", ""),
                        cluster.get("status", ""),
                    )
            except (BotoCoreError, ClientError) as exc:
                console.print(f"[red]Error describing cluster {name}:[/red] {exc}")

    console.print(table)
    console.print(f"[dim]{len(cluster_names)} cluster(s)[/dim]")


@app.command("describe")
def describe_cluster(
    ctx: typer.Context,
    cluster_name: str = typer.Argument(..., help="Name of the EKS cluster."),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        case_sensitive=False,
        help="Output format: table, yaml, json.",
        show_choices=True,
        show_default=True,
    ),
) -> None:
    """Show raw EKS cluster details."""
    state_obj = ctx.ensure_object(AppState)
    try:
        client = create_eks_client(profile=state_obj.profile, region=state_obj.region)
    except Exception as exc:
        console.print(f"[red]Could not build EKS client:[/red] {exc}")
        raise typer.Exit(1) from exc

    with console.status(f"Fetching details for cluster '{cluster_name}'...", spinner="dots"):
        try:
            # IAM action: eks:DescribeCluster
            response = client.describe_cluster(name=cluster_name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                console.print(f"[red]Cluster '{cluster_name}' not found.[/red]")
                raise typer.Exit(1)
            console.print(f"[red]EKS lookup failed:[/red] {exc}")
            raise typer.Exit(1) from exc
        except BotoCoreError as exc:
            console.print(f"[red]EKS lookup failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    cluster = response.get("cluster", {})
    if not cluster:
        console.print(f"[yellow]No details found for cluster '{cluster_name}'.[/yellow]")
        raise typer.Exit(1)

    fmt = output_format.lower()

    if fmt == "table":
        summary = Table(show_header=False, title="EKS Cluster Details")
        summary.add_row("Name", cluster.get("name", ""))
        summary.add_row("ARN", cluster.get("arn", ""))
        summary.add_row("Status", cluster.get("status", ""))
        summary.add_row("Version", cluster.get("version", ""))
        summary.add_row("Endpoint", cluster.get("endpoint", ""))

        vpc_config = cluster.get("resourcesVpcConfig", {})
        summary.add_row("VPC ID", vpc_config.get("vpcId", ""))
        summary.add_row("Subnet IDs", ", ".join(vpc_config.get("subnetIds", [])))
        summary.add_row("Cluster Security Group ID", vpc_config.get("clusterSecurityGroupId", ""))

        summary.add_row("Created At", str(cluster.get("createdAt", "")))
        console.print(summary)
        return

    normalized = normalize(cluster)

    if fmt == "json":
        console.print_json(json.dumps(normalized, indent=2))
    elif fmt == "yaml":
        console.print(yaml.safe_dump(normalized, sort_keys=False))
    else:
        console.print(f"[red]Unknown format '{output_format}'.[/red]")
        raise typer.Exit(1)


@app.command("kubeconfig")
def update_kubeconfig(
    ctx: typer.Context,
    cluster_name: str = typer.Argument(..., help="Name of the EKS cluster."),
    kubeconfig_name: str | None = typer.Option(
        None,
        "--kubeconfig",
        "-k",
        help="Name of the kubeconfig file (default: cluster_name). Stored in ~/.kube/",
    ),
) -> None:
    """Update kubeconfig with EKS cluster credentials."""
    state_obj = ctx.ensure_object(AppState)
    kube_dir = Path.home() / ".kube"
    kube_dir.mkdir(exist_ok=True)

    config_name = kubeconfig_name or cluster_name
    config_path = kube_dir / config_name

    cmd = [
        "aws",
        "eks",
        "update-kubeconfig",
        "--name",
        cluster_name,
        "--kubeconfig",
        str(config_path),
    ]

    # Pass profile and region to the aws cli if they are set
    env = os.environ.copy()
    if state_obj.profile:
        env["AWS_PROFILE"] = state_obj.profile
    if state_obj.region:
        env["AWS_REGION"] = state_obj.region

    with console.status(f"Updating kubeconfig for '{cluster_name}'...", spinner="dots"):
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                console.print(f"[red]Failed to update kubeconfig:[/red]\n{result.stderr}")
                raise typer.Exit(1)

            console.print(f"Updated context for cluster [green]'{cluster_name}'[/green].")
            console.print("You can now use this cluster with kubectl by specifying the kubeconfig file:")
            console.print(f"kubectl --kubeconfig {shlex.quote(str(config_path))} get nodes")

        except FileNotFoundError:
            console.print("[red]The 'aws' command-line tool is not installed or not in your PATH.[/red]")
            raise typer.Exit(1)
        except Exception as exc:
            console.print(f"[red]An unexpected error occurred:[/red] {exc}")
            raise typer.Exit(1)


def run() -> None:
    """Entrypoint for Typer."""
    app()


if __name__ == "__main__":
    run()
