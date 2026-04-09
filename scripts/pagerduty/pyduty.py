#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
#     "rich",
#     "typer",
# ]
# bin-name = "pyduty"
# ///

"""PagerDuty utility script.

This script provides commands for managing PagerDuty resources. Currently supports
maintenance window operations (list, create, end), with additional features planned.

Authentication is done via a PagerDuty API token stored in the PAGERDUTY_API_TOKEN
environment variable or in ~/.config/silentcastle/pagerduty.json.

Configuration file example (~/.config/silentcastle/pagerduty.json):
    {
        "api_token": "your-pagerduty-api-token-here"
    }

Usage:

    Running the script with uv use: `uv run --script packages/pagerduty/pyduty.py <command> <args>`
    Running the script with the wrapper script use: `pyduty <command> <args>`

    pyduty maint-window list
    pyduty maint-window create <service-id> [<service-id>...] --start <time> --end <time>
    pyduty maint-window end --id <window-id>
    pyduty service list
    pyduty service search <query>
    pyduty service display <service-id>

Examples:
    pyduty maint-window create 1234567890 9876543210 --start "2025-12-10 10:00:00" --end "2025-12-10 11:00:00"
    pyduty maint-window create 1234567890 9876543210 --start "2025-12-10 10:00:00" --end "2025-12-10 11:00:00"

Author: Robert Wallace
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table, Column
import typer

console = Console()
app = typer.Typer(help="PagerDuty utilities.")
maint_app = typer.Typer(help="Maintenance window operations.")
service_app = typer.Typer(help="Service operations.")
app.add_typer(maint_app, name="maint-window")
app.add_typer(service_app, name="service")

# PagerDuty API base URL
PD_API_BASE = "https://api.pagerduty.com"

# Config file format: {"api_token": "your-pagerduty-api-token-here"}
CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "silentcastle"
)
CONFIG_FILE = CONFIG_DIR / "pagerduty.json"


def get_api_token() -> str:
    """Get PagerDuty API token from environment or config file."""
    # Try environment variable first
    token = os.environ.get("PAGERDUTY_API_TOKEN")
    if token:
        return token

    # Try config file
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            token = data.get("api_token") or data.get("PAGERDUTY_API_TOKEN")
            if token:
                return token
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not read config file: {e}[/yellow]"
            )

    console.print(
        "[red]PagerDuty API token not found.[/red]\n"
        "Set PAGERDUTY_API_TOKEN environment variable or create "
        f"{CONFIG_FILE} with:\n"
        '  {{"api_token": "your-token-here"}}'
    )
    raise typer.Exit(1)


def create_client(token: str) -> httpx.Client:
    """Create an HTTP client configured for PagerDuty API."""
    headers = {
        "Authorization": f"Token token={token}",
        "Accept": "application/vnd.pagerduty+json;version=2",
        "Content-Type": "application/json",
    }
    return httpx.Client(base_url=PD_API_BASE, headers=headers, timeout=30.0)


def format_datetime(dt_str: str | None) -> str:
    """Format ISO datetime string for display."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return dt_str


def get_system_timezone() -> ZoneInfo | timezone:
    """Get system timezone or fallback to UTC.
    
    Returns:
        ZoneInfo or UTC timezone object.
    """
    # Try TZ environment variable first
    tz_env = os.environ.get("TZ")
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except Exception:
            pass
    
    # Try macOS/Linux: read /etc/localtime symlink
    try:
        localtime_path = Path("/etc/localtime")
        if localtime_path.exists() and localtime_path.is_symlink():
            target = localtime_path.readlink()
            # Extract timezone from path like /var/db/timezone/zoneinfo/America/Chicago
            parts = target.parts
            if "zoneinfo" in parts:
                idx = parts.index("zoneinfo")
                tz_parts = parts[idx + 1:]
                if tz_parts:
                    tz_name = "/".join(tz_parts)
                    try:
                        return ZoneInfo(tz_name)
                    except Exception:
                        pass
    except Exception:
        pass
    
    # Try to get timezone from datetime's tzinfo
    try:
        local_dt = datetime.now().astimezone()
        tz_info = local_dt.tzinfo
        
        # If it's already a ZoneInfo, return it
        if isinstance(tz_info, ZoneInfo):
            return tz_info
        
        # Try to extract timezone name from tzinfo string representation
        tz_str = str(tz_info)
        # Sometimes tzinfo shows as "CST" or similar, which is ambiguous
        # But if it shows a full path or IANA name, we can use it
        if "/" in tz_str or tz_str.startswith(("America/", "Europe/", "Asia/", "Australia/", "Africa/")):
            try:
                return ZoneInfo(tz_str)
            except Exception:
                pass
    except Exception:
        pass
    
    # Fallback to UTC
    return timezone.utc


def resolve_timezone(tz_str: str | None) -> tuple[ZoneInfo | timezone, bool]:
    """Resolve timezone string to ZoneInfo object.
    
    Args:
        tz_str: Timezone string (e.g., "America/New_York", "UTC", "+05:00", or None).
    
    Returns:
        Tuple of (timezone object, is_fallback) where is_fallback is True if UTC fallback was used.
    """
    if not tz_str:
        tz = get_system_timezone()
        is_fallback = tz == timezone.utc
        return tz, is_fallback
    
    tz_str = tz_str.strip()
    
    # Handle UTC explicitly
    if tz_str.upper() in ("UTC", "Z"):
        return timezone.utc, False
    
    # Handle offset format (+05:00, -05:00)
    if tz_str.startswith(("+", "-")):
        try:
            # Parse offset like +05:00 or -05:00
            if len(tz_str) == 6:  # +05:00 format
                hours = int(tz_str[1:3])
                minutes = int(tz_str[4:6])
                offset_seconds = (hours * 3600 + minutes * 60) * (1 if tz_str[0] == "+" else -1)
                return timezone(timedelta(seconds=offset_seconds)), False
        except Exception:
            pass
    
    # Try as IANA timezone name (e.g., America/New_York)
    try:
        return ZoneInfo(tz_str), False
    except Exception:
        console.print(f"[yellow]Warning: Could not parse timezone '{tz_str}', using UTC.[/yellow]")
        return timezone.utc, True


def parse_datetime(dt_str: str, tz: ZoneInfo | timezone | None = None) -> str:
    """Parse and normalize datetime string to ISO format with timezone.
    
    Args:
        dt_str: Datetime string to parse.
        tz: Timezone to apply if datetime has no timezone info. If None, uses UTC.
    
    Returns:
        ISO format datetime string with timezone.
    """
    if tz is None:
        tz = timezone.utc
    
    # Try ISO format first
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.isoformat()
    except Exception:
        pass

    # Try common formats (naive datetime, will apply timezone)
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            dt = dt.replace(tzinfo=tz)
            return dt.isoformat()
        except Exception:
            continue

    console.print(f"[red]Could not parse datetime: {dt_str}[/red]")
    console.print("Expected formats: ISO 8601, YYYY-MM-DD HH:MM:SS, etc.")
    raise typer.Exit(1)


@maint_app.command("list")
def list_maintenance_windows(
    service_id: str | None = typer.Option(
        None, "--service-id", "-s", help="Filter by service ID."
    ),
    limit: int = typer.Option(
        25, "--limit", "-l", help="Maximum number of windows to return."
    ),
) -> None:
    """List maintenance windows."""
    token = get_api_token()
    client = create_client(token)

    params: dict[str, Any] = {"limit": limit}
    if service_id:
        params["service_ids[]"] = [service_id]

    with console.status("[bold cyan]Fetching maintenance windows...", spinner="dots"):
        try:
            response = client.get("/maintenance_windows", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[red]API error:[/red] {e.response.status_code}")
            if e.response.status_code == 401:
                console.print("[red]Authentication failed. Check your API token.[/red]")
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    console.print(f"[red]{error_data['error']}[/red]")
            except Exception:
                pass
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    windows = data.get("maintenance_windows", [])
    if not windows:
        console.print("[yellow]No maintenance windows found.[/yellow]")
        raise typer.Exit(0)

    table = Table(
        "ID",
        "Description",
        "Service",
        "Start",
        "End",
        Column("Duration", justify="right"),
        "Status",
        show_lines=False,
    )

    # Pre-process windows to calculate status and format times
    status_order = {"active": 0, "pending": 1, "ended": 2}
    now_utc = datetime.now(timezone.utc)

    for window in windows:
        start_time = window.get("start_time")
        end_time = window.get("end_time")
        
        try:
            # Parse start and end times into timezone-aware datetime objects
            start_time_iso = parse_datetime(start_time, tz=timezone.utc)
            end_time_iso = parse_datetime(end_time, tz=timezone.utc)
            
            start_dt = datetime.fromisoformat(start_time_iso)
            end_dt = datetime.fromisoformat(end_time_iso)

            # Calculate duration
            duration = end_dt - start_dt
            total_seconds = int(duration.total_seconds())
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
            if not parts:
                parts.append("0m")
            
            duration_str = " ".join(parts)

            if now_utc < start_dt:
                status = "pending"
            elif start_dt <= now_utc <= end_dt:
                status = "active"
            else:
                status = "ended"
        except Exception:
            status = "unknown"
            start_time_iso = str(start_time)
            end_time_iso = str(end_time)
            duration_str = "N/A"

        # Store calculated values for sorting and display
        window["_status"] = status
        window["_start_iso"] = start_time_iso
        window["_end_iso"] = end_time_iso
        window["_duration_str"] = duration_str
        window["_sort_order"] = status_order.get(status, 99)

    # Sort by status
    windows.sort(key=lambda w: w.get("_sort_order", 99))

    for window in windows:
        window_id = window.get("id", "N/A")
        description = window.get("description")
        services = window.get("services", [])
        service_names = ", ".join(
            [s.get("name", s.get("id", "")) for s in services[:3]]
        )
        if len(services) > 3:
            service_names += f" (+{len(services) - 3} more)"

        # Use pre-calculated values
        status = window.get("_status", "unknown")
        start_time_iso = window.get("_start_iso", "")
        end_time_iso = window.get("_end_iso", "")
        duration_str = window.get("_duration_str", "")

        status_style = (
            "green" if status == "active" else ("yellow" if status == "pending" else "dim")
        )

        table.add_row(
            window_id,
            description or "(no description)",
            service_names or "(no services)",
            start_time_iso,
            end_time_iso,
            duration_str,
            f"[{status_style}]{status}[/{status_style}]",
        )
    
    console.print(table)
    console.print(f"[dim]{len(windows)} window(s)[/dim]")


def list_available_timezones(filter_str: str | None = None) -> list[str]:
    """List all available IANA timezones, optionally filtered.
    
    Args:
        filter_str: Optional filter string to match timezone names (case-insensitive).
    
    Returns:
        List of timezone names.
    """
    try:
        # Try to get timezones from zoneinfo
        import zoneinfo
        all_tz = sorted(zoneinfo.available_timezones())
    except Exception:
        # Fallback: common timezones if zoneinfo.available_timezones() isn't available
        # This is a subset of common timezones
        all_tz = [
            "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos",
            "America/Chicago", "America/Denver", "America/Los_Angeles",
            "America/Mexico_City", "America/New_York", "America/Sao_Paulo",
            "America/Toronto", "Asia/Dubai", "Asia/Hong_Kong",
            "Asia/Jakarta", "Asia/Kolkata", "Asia/Seoul", "Asia/Shanghai",
            "Asia/Singapore", "Asia/Tokyo", "Australia/Melbourne",
            "Australia/Sydney", "Europe/Amsterdam", "Europe/Berlin",
            "Europe/London", "Europe/Madrid", "Europe/Paris", "Europe/Rome",
            "Pacific/Auckland", "Pacific/Honolulu", "UTC",
        ]
    
    if filter_str:
        filter_lower = filter_str.lower()
        return [tz for tz in all_tz if filter_lower in tz.lower()]
    
    return all_tz


@maint_app.command("check-tz")
def check_timezone(
    tz: str | None = typer.Option(
        None, "--tz", help="Timezone to check (e.g., America/New_York, UTC, +05:00). If not provided, shows system timezone."
    ),
    list_tz: bool = typer.Option(
        False, "--list-tz", help="List available timezones and exit."
    ),
    filter_tz: str | None = typer.Option(
        None, "--filter", help="Filter timezones by name (e.g., 'america' to show America/* timezones). Only used with --list-tz."
    ),
) -> None:
    """Display the timezone that would be used for maintenance windows."""
    # Handle list timezones request
    if list_tz:
        filter_str = filter_tz if filter_tz else None
        timezones = list_available_timezones(filter_str)
        
        if not timezones:
            filter_display = f"'{filter_str}'" if filter_str else "the filter"
            console.print(f"[yellow]No timezones found matching {filter_display}.[/yellow]")
            raise typer.Exit(0)
        
        table = Table("Timezone", show_lines=False)
        for tz_name in timezones:
            table.add_row(tz_name)
        
        filter_msg = f" matching '{filter_str}'" if filter_str else ""
        console.print(table)
        console.print(f"[dim]{len(timezones)} timezone(s){filter_msg}[/dim]")
        raise typer.Exit(0)
    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)
    
    # Get system timezone
    system_tz = get_system_timezone()
    system_tz_name = str(system_tz)
    if isinstance(system_tz, ZoneInfo):
        system_tz_name = system_tz.key
    elif isinstance(system_tz, timezone):
        if system_tz == timezone.utc:
            system_tz_name = "UTC"
        else:
            system_tz_name = str(system_tz)
    
    # Get resolved timezone (system or override)
    resolved_tz, is_fallback = resolve_timezone(tz)
    
    tz_name = str(resolved_tz)
    if isinstance(resolved_tz, ZoneInfo):
        tz_name = resolved_tz.key
    elif isinstance(resolved_tz, timezone):
        if resolved_tz == timezone.utc:
            tz_name = "UTC"
        else:
            tz_name = str(resolved_tz)
    
    # Build display table
    table = Table(show_header=False, box=None, padding=(0, 1))
    
    # Current time in UTC
    utc_time = now_utc.strftime("%Y-%m-%d %H:%M:%S %Z")
    table.add_row("[bold]Current time (UTC):[/bold]", utc_time)
    
    # System timezone
    system_time = now_utc.astimezone(system_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    system_fallback = " (fallback to UTC)" if system_tz == timezone.utc and not os.environ.get("TZ") else ""
    table.add_row("[bold]System timezone:[/bold]", f"{system_tz_name}{system_fallback}")
    table.add_row("", f"  {system_time}")
    
    # Override timezone if specified
    if tz:
        override_time = now_utc.astimezone(resolved_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        override_fallback = " (fallback to UTC)" if is_fallback else ""
        table.add_row("[bold]Override timezone:[/bold]", f"{tz_name}{override_fallback}")
        table.add_row("", f"  {override_time}")
    else:
        table.add_row("", "[dim]No override specified.[/dim]")
    
    console.print(table)
    
    if is_fallback and not tz:
        console.print()
        console.print("[yellow]System timezone could not be determined.[/yellow]")
        console.print("[yellow]Please specify a timezone using --tz option when creating maintenance windows.[/yellow]")
        console.print("\nExamples:")
        console.print("  --tz America/New_York")
        console.print("  --tz UTC")
        console.print("  --tz +05:00")


@maint_app.command("create")
def create_maintenance_window(
    service_ids: list[str] = typer.Argument(..., help="Service ID(s) to create window for. Can specify multiple."),
    start: str = typer.Option(..., "--start", "-s", help="Start time (ISO format or YYYY-MM-DD HH:MM:SS)."),
    end: str = typer.Option(..., "--end", "-e", help="End time (ISO format or YYYY-MM-DD HH:MM:SS)."),
    description: str = typer.Option(
        "", "--description", "-d", help="Window description."
    ),
    tz: str | None = typer.Option(
        None, "--tz", help="Timezone (e.g., America/New_York, UTC, +05:00). Defaults to system timezone."
    ),
) -> None:
    """Create a new maintenance window for one or more services."""
    if not service_ids:
        console.print("[red]At least one service ID is required.[/red]")
        raise typer.Exit(1)

    # Resolve timezone
    resolved_tz, is_fallback = resolve_timezone(tz)

    # Exit if we had to use UTC fallback
    if is_fallback and not tz:
        console.print("[red]Error: System timezone could not be determined.[/red]")
        console.print("[yellow]Please specify a timezone using --tz option.[/yellow]")
        console.print("\nExamples:")
        console.print("  --tz America/New_York")
        console.print("  --tz UTC")
        console.print("  --tz +05:00")
        console.print("\nUse 'pyduty maint-window check-tz' to see what timezone would be used.")
        raise typer.Exit(1)

    token = get_api_token()
    client = create_client(token)

    start_iso = parse_datetime(start, resolved_tz)
    end_iso = parse_datetime(end, resolved_tz)

    # Validate end is after start
    try:
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        if end_dt <= start_dt:
            console.print("[red]End time must be after start time.[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Invalid datetime:[/red] {e}")
        raise typer.Exit(1) from e

    # Build services array from all provided service IDs
    services = [{"id": sid, "type": "service_reference"} for sid in service_ids]

    payload = {
        "maintenance_window": {
            "type": "maintenance_window",
            "start_time": start_iso,
            "end_time": end_iso,
            "services": services,
        }
    }

    if description:
        payload["maintenance_window"]["description"] = description

    with console.status("[bold cyan]Creating maintenance window...", spinner="dots"):
        try:
            response = client.post("/maintenance_windows", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[red]API error:[/red] {e.response.status_code}")
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    console.print(f"[red]{error_data['error']}[/red]")
                if "errors" in error_data:
                    for err in error_data["errors"]:
                        console.print(f"[red]{err}[/red]")
            except Exception:
                pass
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    window = data.get("maintenance_window", {})
    window_id = window.get("id", "")
    description = window.get("description", "")
    start_time = format_datetime(window.get("start_time"))
    end_time = format_datetime(window.get("end_time"))

    panel = Panel.fit(
        f"[bold green]Maintenance window created[/bold green]\n\n"
        f"ID: {window_id}\n"
        f"Description: {description or '(no description)'}\n"
        f"Services: {len(service_ids)} service(s)\n"
        f"Start: {start_time}\n"
        f"End: {end_time}",
        title="Success",
        style="green",
    )
    console.print(panel)
    if len(service_ids) > 1:
        console.print(f"[dim]Service IDs: {', '.join(service_ids)}[/dim]")


@maint_app.command("end")
def end_maintenance_window(
    window_id: str = typer.Argument(..., help="Maintenance window ID to end."),
) -> None:
    """End an active maintenance window."""
    token = get_api_token()
    client = create_client(token)

    # Get current window to check status
    with console.status(
        "[bold cyan]Fetching maintenance window...", spinner="dots"
    ) as status:
        try:
            response = client.get(f"/maintenance_windows/{window_id}")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[red]Maintenance window {window_id} not found.[/red]")
            else:
                console.print(f"[red]API error:[/red] {e.response.status_code}")
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    window = data.get("maintenance_window", {})
    current_status = window.get("status", "")

    if current_status not in ("active", "pending"):
        console.print(
            f"[yellow]Window is already {current_status}. Nothing to do.[/yellow]"
        )
        raise typer.Exit(0)

    # End the window by updating end_time to now
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "maintenance_window": {
            "end_time": now_iso,
        }
    }

    status.update("[bold cyan]Ending maintenance window...")
    try:
        response = client.put(f"/maintenance_windows/{window_id}", json=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        console.print(f"[red]API error:[/red] {e.response.status_code}")
        try:
            error_data = e.response.json()
            if "error" in error_data:
                console.print(f"[red]{error_data['error']}[/red]")
            if "errors" in error_data:
                for err in error_data["errors"]:
                    console.print(f"[red]{err}[/red]")
        except Exception:
            pass
        raise typer.Exit(1) from e
    except httpx.RequestError as e:
        console.print(f"[red]Request failed:[/red] {e}")
        raise typer.Exit(1) from e

    window = data.get("maintenance_window", {})
    end_time = format_datetime(window.get("end_time"))

    panel = Panel.fit(
        f"[bold green]Maintenance window ended[/bold green]\n\n"
        f"ID: {window_id}\n"
        f"Ended at: {end_time}",
        title="Success",
        style="green",
    )
    console.print(panel)


@maint_app.command("display")
def display_maintenance_window(
    window_id: str = typer.Argument(..., help="Maintenance window ID to display."),
) -> None:
    """Display detailed information about a maintenance window."""
    token = get_api_token()
    client = create_client(token)

    with console.status(f"[bold cyan]Fetching maintenance window {window_id}...", spinner="dots"):
        try:
            response = client.get(f"/maintenance_windows/{window_id}")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[red]Maintenance window {window_id} not found.[/red]")
            else:
                console.print(f"[red]API error:[/red] {e.response.status_code}")
                if e.response.status_code == 401:
                    console.print("[red]Authentication failed. Check your API token.[/red]")
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    console.print(f"[red]{error_data['error']}[/red]")
            except Exception:
                pass
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    window = data.get("maintenance_window", {})
    if not window:
        console.print(f"[yellow]Maintenance window {window_id} not found.[/yellow]")
        raise typer.Exit(1) 

    # table = Table(show_header=False, title="Maintenance Window Details", box=None)
    table = Table(show_header=False, title="Maintenance Window Details", show_lines=False)

    window_id_val = window.get("id", "")
    summary = window.get("summary", "")
    sequence_number = window.get("sequence_number", "")
    description = window.get("description", "")
    html_url = window.get("html_url", "")
    start_time = window.get("start_time")
    end_time = window.get("end_time")
    # created_at is not standard in maintenance_window object, check if present
    created_at = window.get("created_at")
    created_at_fmt = format_datetime(created_at) if created_at else ""
    
    # Calculate status
    now_utc = datetime.now(timezone.utc)
    start_time_iso = parse_datetime(start_time, tz=timezone.utc)
    end_time_iso = parse_datetime(end_time, tz=timezone.utc)
    start_dt = datetime.fromisoformat(start_time_iso)
    end_dt = datetime.fromisoformat(end_time_iso)

    if now_utc < start_dt:
        status = "pending"
    elif start_dt <= now_utc <= end_dt:
        status = "active"
    else:
        status = "ended"

    status_style = (
        "green" if status == "active" else ("yellow" if status == "pending" else "dim")
    )

    table.add_row("ID", window_id_val)
    if summary:
        table.add_row("Summary", summary)
    if sequence_number:
        table.add_row("Sequence Number", str(sequence_number))
    table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
    if description and description != summary:
         table.add_row("Description", description)
    table.add_row("Start Time", start_time_iso)
    table.add_row("End Time", end_time_iso)
    
    if created_at_fmt:
        table.add_row("Created At", created_at_fmt)
    
    created_by = window.get("created_by", {})
    if created_by:
        cb_name = created_by.get("summary", created_by.get("id", ""))
        table.add_row("Created By", cb_name)

    services = window.get("services", [])
    if services:
        service_lines = []
        for s in services:
            s_id = s.get("id", "")
            s_summary = s.get("summary", "")
            service_lines.append(f"[{s_id}] {s_summary}")
        
        table.add_row("Services", "\n".join(service_lines))

    teams = window.get("teams", [])
    if teams:
        team_names = ", ".join(
            [t.get("summary", t.get("id", "")) for t in teams[:5]]
        )
        if len(teams) > 5:
            team_names += f" (+{len(teams) - 5} more)"
        table.add_row("Teams", team_names)

    if html_url:
        table.add_row("URL", html_url)

    console.print(table)
    console.print(f"[dim]ID: {window_id_val}[/dim]")


@service_app.command("list")
def list_services(
    limit: int = typer.Option(
        25, "--limit", "-l", help="Maximum number of services to return."
    ),
) -> None:
    """List all services."""
    token = get_api_token()
    client = create_client(token)

    params: dict[str, Any] = {"limit": limit}

    with console.status("[bold cyan]Fetching services...", spinner="dots"):
        try:
            response = client.get("/services", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[red]API error:[/red] {e.response.status_code}")
            if e.response.status_code == 401:
                console.print("[red]Authentication failed. Check your API token.[/red]")
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    console.print(f"[red]{error_data['error']}[/red]")
            except Exception:
                pass
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    services = data.get("services", [])
    if not services:
        console.print("[yellow]No services found.[/yellow]")
        raise typer.Exit(0)

    table = Table(
        "ID",
        "Name",
        "Status",
        "Type",
        "Escalation Policy",
        show_lines=False,
    )

    for service in services:
        service_id = service.get("id", "")
        name = service.get("name", "")
        status = service.get("status", "unknown")
        service_type = service.get("type", "")
        escalation_policy = service.get("escalation_policy", {})
        escalation_policy_name = escalation_policy.get("summary", escalation_policy.get("id", "")) if isinstance(escalation_policy, dict) else ""

        status_style = (
            "green" if status == "active" else ("yellow" if status == "warning" else "dim")
        )

        table.add_row(
            service_id,
            name,
            f"[{status_style}]{status}[/{status_style}]",
            service_type,
            escalation_policy_name or "(none)",
        )

    console.print(table)
    console.print(f"[dim]{len(services)} service(s)[/dim]")


@service_app.command("search")
def search_services(
    query: str = typer.Argument(..., help="Search query (matches service name)."),
    limit: int = typer.Option(
        25, "--limit", "-l", help="Maximum number of services to return."
    ),
) -> None:
    """Search for services by name."""
    token = get_api_token()
    client = create_client(token)

    params: dict[str, Any] = {"limit": limit, "query": query}

    with console.status(f"[bold cyan]Searching for '{query}'...", spinner="dots"):
        try:
            response = client.get("/services", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[red]API error:[/red] {e.response.status_code}")
            if e.response.status_code == 401:
                console.print("[red]Authentication failed. Check your API token.[/red]")
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    console.print(f"[red]{error_data['error']}[/red]")
            except Exception:
                pass
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    services = data.get("services", [])
    if not services:
        console.print(f"[yellow]No services found matching '{query}'.[/yellow]")
        raise typer.Exit(0)

    table = Table(
        "ID",
        "Name",
        "Status",
        "Type",
        "Escalation Policy",
        show_lines=False,
    )

    for service in services:
        service_id = service.get("id", "")
        name = service.get("name", "")
        status = service.get("status", "unknown")
        service_type = service.get("type", "")
        escalation_policy = service.get("escalation_policy", {})
        escalation_policy_name = escalation_policy.get("summary", escalation_policy.get("id", "")) if isinstance(escalation_policy, dict) else ""

        status_style = (
            "green" if status == "active" else ("yellow" if status == "warning" else "dim")
        )

        table.add_row(
            service_id,
            name,
            f"[{status_style}]{status}[/{status_style}]",
            service_type,
            escalation_policy_name or "(none)",
        )

    console.print(table)
    console.print(f"[dim]{len(services)} service(s) found[/dim]")


@service_app.command("display")
def display_service(
    service_id: str = typer.Argument(..., help="Service ID to display."),
) -> None:
    """Display detailed information about a service."""
    token = get_api_token()
    client = create_client(token)

    with console.status(f"[bold cyan]Fetching service {service_id}...", spinner="dots"):
        try:
            response = client.get(f"/services/{service_id}")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[red]Service {service_id} not found.[/red]")
            else:
                console.print(f"[red]API error:[/red] {e.response.status_code}")
                if e.response.status_code == 401:
                    console.print("[red]Authentication failed. Check your API token.[/red]")
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    console.print(f"[red]{error_data['error']}[/red]")
            except Exception:
                pass
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[red]Request failed:[/red] {e}")
            raise typer.Exit(1) from e

    service = data.get("service", {})
    if not service:
        console.print(f"[yellow]Service {service_id} not found.[/yellow]")
        raise typer.Exit(1)

    table = Table(show_header=False, title="Service Details", box=None)
    
    service_id_val = service.get("id", "")
    name = service.get("name", "")
    description = service.get("description", "")
    status = service.get("status", "unknown")
    service_type = service.get("type", "")
    created_at = format_datetime(service.get("created_at"))
    updated_at = format_datetime(service.get("updated_at"))
    
    status_style = (
        "green" if status == "active" else ("yellow" if status == "warning" else "dim")
    )

    table.add_row("ID", service_id_val)
    table.add_row("Name", name)
    if description:
        table.add_row("Description", description)
    table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
    table.add_row("Type", service_type)
    
    escalation_policy = service.get("escalation_policy", {})
    if isinstance(escalation_policy, dict):
        ep_id = escalation_policy.get("id", "")
        ep_name = escalation_policy.get("summary", "")
        table.add_row("Escalation Policy", f"{ep_name} ({ep_id})" if ep_name else ep_id)
    
    alert_creation = service.get("alert_creation", "")
    if alert_creation:
        table.add_row("Alert Creation", alert_creation)
    
    if created_at:
        table.add_row("Created", created_at)
    if updated_at:
        table.add_row("Updated", updated_at)

    integrations = service.get("integrations", [])
    if integrations:
        integration_names = ", ".join([
            i.get("name", i.get("id", "")) for i in integrations[:5]
        ])
        if len(integrations) > 5:
            integration_names += f" (+{len(integrations) - 5} more)"
        table.add_row("Integrations", integration_names)

    console.print(table)
    
    console.print()
    console.print(f"[bold cyan]Service ID:[/bold cyan] {service_id_val}")


def run() -> None:
    """Entrypoint for Typer."""
    app()


if __name__ == "__main__":
    run()

