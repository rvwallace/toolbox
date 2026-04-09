#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "python-dotenv",
#     "rich",
#     "pyyaml",
#     "click",
#     "python-dateutil",
# ]
# bin-name = "pd-report"
# ///

"""PagerDuty incident reporting script.

This script generates comprehensive incident reports from PagerDuty services,
with support for multiple output formats and rich console visualization.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import requests
import yaml
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from rich.tree import Tree

# Constants
_DEFAULT_PAGERDUTY_SERVICES = ""
_LAST_RUN_FILENAME = ".pagerduty_last_run"
_PAGERDUTY_BASE_URL = "https://api.pagerduty.com"
_PAGERDUTY_API_VERSION = "application/vnd.pagerduty+json;version=2"
_MAX_INCIDENTS_PER_SERVICE_DISPLAY = 5
_MAX_ASSIGNEES_DISPLAY = 30
_TITLE_TRUNCATE_LENGTH = 60

console = Console()

# Load environment variables
load_dotenv()

PAGERDUTY_API_KEY = os.getenv("PAGERDUTY_API_KEY")
PAGERDUTY_SERVICES = os.getenv("PAGERDUTY_SERVICES", _DEFAULT_PAGERDUTY_SERVICES).split(
    ","
)
LAST_RUN_FILE = Path(_LAST_RUN_FILENAME)


class PagerDutyClient:
    """Client for interacting with the PagerDuty API.

    This class provides methods to fetch incident data from PagerDuty services
    including enriching incidents with alerts and notes.
    """

    def __init__(self, api_key: str) -> None:
        """Initializes the PagerDuty client.

        Args:
            api_key: PagerDuty API key with read access to incidents.
        """
        self.api_key = api_key
        self.base_url = _PAGERDUTY_BASE_URL
        self.headers = {
            "Authorization": f"Token token={api_key}",
            "Accept": _PAGERDUTY_API_VERSION,
            "Content-Type": "application/json",
        }

    def get_incidents(
        self, service_ids: List[str], since: datetime, until: datetime
    ) -> List[Dict[str, Any]]:
        """Fetches incidents for specified services within date range.

        Args:
            service_ids: List of PagerDuty service IDs to query.
            since: Start date for incident search.
            until: End date for incident search.

        Returns:
            List of incident dictionaries from the PagerDuty API.
        """
        incidents = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Fetching incidents from PagerDuty...", total=len(service_ids)
            )

            for service_id in service_ids:
                service_id = service_id.strip()
                if not service_id:
                    continue

                progress.update(
                    task, description=f"Fetching incidents for service {service_id}"
                )

                params = {
                    "service_ids[]": service_id,
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "limit": 100,
                    "offset": 0,
                    "include[]": ["alerts", "notes", "log_entries"],
                }

                while True:
                    response = requests.get(
                        f"{self.base_url}/incidents",
                        headers=self.headers,
                        params=params,
                    )

                    if response.status_code != 200:
                        console.print(
                            f"[red]Error fetching incidents for service "
                            f"{service_id}: {response.status_code}[/red]"
                        )
                        break

                    data = response.json()
                    incidents.extend(data.get("incidents", []))

                    if not data.get("more", False):
                        break

                    params["offset"] += params["limit"]

                progress.advance(task)

        return incidents

    def enrich_incident_data(
        self, incidents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enriches incident data with alerts and notes.

        Args:
            incidents: List of basic incident dictionaries.

        Returns:
            List of enriched incident dictionaries with alerts and notes.
        """
        enriched_incidents = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Enriching incident data...", total=len(incidents))

            for incident in incidents:
                if not incident:
                    continue
                incident_id = incident.get("id")
                if not incident_id:
                    continue

                # Get alerts
                alerts = []
                try:
                    alerts_response = requests.get(
                        f"{self.base_url}/incidents/{incident_id}/alerts",
                        headers=self.headers,
                    )
                    if alerts_response.status_code == 200:
                        alerts_data = alerts_response.json()
                        alerts = alerts_data.get("alerts", []) if alerts_data else []
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not fetch alerts for incident "
                        f"{incident_id}: {e}[/yellow]"
                    )

                # Get notes
                notes = []
                try:
                    notes_response = requests.get(
                        f"{self.base_url}/incidents/{incident_id}/notes",
                        headers=self.headers,
                    )
                    if notes_response.status_code == 200:
                        notes_data = notes_response.json()
                        notes = notes_data.get("notes", []) if notes_data else []
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not fetch notes for incident "
                        f"{incident_id}: {e}[/yellow]"
                    )

                enriched_incident = {
                    "id": incident.get("id", ""),
                    "incident_number": incident.get("incident_number", ""),
                    "title": incident.get("title", ""),
                    "description": incident.get("description", ""),
                    "status": incident.get("status", ""),
                    "created_at": incident.get("created_at", ""),
                    "updated_at": incident.get("updated_at", ""),
                    "service": (
                        incident.get("service", {}).get("summary", "Unknown")
                        if incident.get("service")
                        else "Unknown"
                    ),
                    "service_id": (
                        incident.get("service", {}).get("id", "")
                        if incident.get("service")
                        else ""
                    ),
                    "urgency": incident.get("urgency", ""),
                    "priority": (
                        incident.get("priority", {}).get("summary", "None")
                        if incident.get("priority")
                        else "None"
                    ),
                    "assignees": [
                        user.get("summary", "")
                        for user in incident.get("assignments", [])
                        if user
                    ],
                    "alerts": [
                        {
                            "id": alert.get("id", ""),
                            "summary": alert.get("summary", ""),
                            "created_at": alert.get("created_at", ""),
                            "status": alert.get("status", ""),
                            "severity": alert.get("severity", "Unknown"),
                        }
                        for alert in alerts
                        if alert
                    ],
                    "notes": [
                        {
                            "id": note.get("id", ""),
                            "content": note.get("content", ""),
                            "created_at": note.get("created_at", ""),
                            "user": (
                                note.get("user", {}).get("summary", "Unknown")
                                if note.get("user")
                                else "Unknown"
                            ),
                        }
                        for note in notes
                        if note
                    ],
                }

                enriched_incidents.append(enriched_incident)
                progress.advance(task)

        return enriched_incidents


def parse_time_interval(interval: str) -> timedelta:
    """Parses time interval string into timedelta object.

    Args:
        interval: Time interval string like '1d', '2w', '3m', '12h'.

    Returns:
        timedelta or relativedelta object representing the time interval.

    Raises:
        ValueError: If the interval format is invalid or unsupported.
    """
    if not interval:
        return None

    pattern = r"(\d+)([hdwmy])"
    match = re.match(pattern, interval.lower())

    if not match:
        raise ValueError(f"Invalid time interval format: {interval}")

    amount, unit = match.groups()
    amount = int(amount)

    if unit == "h":
        return timedelta(hours=amount)
    elif unit == "d":
        return timedelta(days=amount)
    elif unit == "w":
        return timedelta(weeks=amount)
    elif unit == "m":
        return relativedelta(months=amount)
    elif unit == "y":
        return relativedelta(years=amount)
    else:
        raise ValueError(f"Unsupported time unit: {unit}")


def get_default_time_range() -> tuple[datetime, datetime]:
    """Gets default time range based on last run or current month.

    Returns:
        Tuple of (start_time, end_time) datetime objects.
    """
    now = datetime.now()

    if LAST_RUN_FILE.exists():
        try:
            last_run = datetime.fromisoformat(LAST_RUN_FILE.read_text().strip())
            return last_run, now
        except (ValueError, FileNotFoundError):
            pass

    # Default to current month
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_of_month, now


def save_last_run() -> None:
    """Saves current timestamp as last run time to file."""
    LAST_RUN_FILE.write_text(datetime.now().isoformat())


def display_rich_report(
    incidents: List[Dict[str, Any]], since: datetime, until: datetime
) -> None:
    """Displays a rich formatted report to stdout.

    Args:
        incidents: List of enriched incident dictionaries.
        since: Start time for the report period.
        until: End time for the report period.
    """
    console.print("\n")
    console.print(
        Panel(
            f"[bold green]PagerDuty Incident Report[/bold green]\n"
            f"[cyan]Period:[/cyan] {since.strftime('%Y-%m-%d %H:%M')} to {until.strftime('%Y-%m-%d %H:%M')}\n"
            f"[cyan]Total Incidents:[/cyan] {len(incidents)}",
            title="📊 Report Summary",
        )
    )

    if not incidents:
        console.print(
            "\n[yellow]No incidents found for the specified time period.[/yellow]"
        )
        return

    # Group by service
    services = {}
    for incident in incidents:
        service = incident["service"]
        if service not in services:
            services[service] = []
        services[service].append(incident)

    # Create tree structure
    tree = Tree("[bold blue]Services & Incidents[/bold blue]")

    for service_name, service_incidents in services.items():
        service_node = tree.add(
            f"[bold cyan]{service_name}[/bold cyan] ({len(service_incidents)} incidents)"
        )

        # Show first few incidents per service
        for incident in service_incidents[:_MAX_INCIDENTS_PER_SERVICE_DISPLAY]:
            status_color = {
                "triggered": "red",
                "acknowledged": "yellow",
                "resolved": "green",
            }.get(incident["status"], "white")

            title_truncated = (
                incident["title"][:_TITLE_TRUNCATE_LENGTH] + "..."
                if len(incident["title"]) > _TITLE_TRUNCATE_LENGTH
                else incident["title"]
            )
            incident_text = (
                f"[{status_color}]#{incident['incident_number']}"
                f"[/{status_color}] {title_truncated}"
            )
            incident_node = service_node.add(incident_text)

            # Add incident details
            if incident["urgency"]:
                incident_node.add(f"🚨 Urgency: {incident['urgency']}")
            if incident["priority"] != "None":
                incident_node.add(f"⭐ Priority: {incident['priority']}")
            if incident["assignees"]:
                assignees_text = ", ".join(
                    incident["assignees"][:_MAX_ASSIGNEES_DISPLAY]
                )
                incident_node.add(f"👤 Assigned to: {assignees_text}")
            if incident["alerts"]:
                incident_node.add(f"🔔 Alerts: {len(incident['alerts'])}")
            if incident["notes"]:
                incident_node.add(f"📝 Notes: {len(incident['notes'])}")

        if len(service_incidents) > _MAX_INCIDENTS_PER_SERVICE_DISPLAY:
            remaining_count = (
                len(service_incidents) - _MAX_INCIDENTS_PER_SERVICE_DISPLAY
            )
            service_node.add(f"[dim]... and {remaining_count} more incidents[/dim]")

    console.print("\n")
    console.print(tree)

    # Summary table
    table = Table(title="📈 Incident Summary by Service")
    table.add_column("Service", style="cyan")
    table.add_column("Total", justify="center")
    table.add_column("Triggered", justify="center", style="red")
    table.add_column("Acknowledged", justify="center", style="yellow")
    table.add_column("Resolved", justify="center", style="green")

    for service_name, service_incidents in services.items():
        total = len(service_incidents)
        triggered = len([i for i in service_incidents if i["status"] == "triggered"])
        acknowledged = len(
            [i for i in service_incidents if i["status"] == "acknowledged"]
        )
        resolved = len([i for i in service_incidents if i["status"] == "resolved"])

        table.add_row(
            service_name, str(total), str(triggered), str(acknowledged), str(resolved)
        )

    console.print("\n")
    console.print(table)


def generate_filename(since: datetime, until: datetime, output_format: str) -> str:
    """Generates filename with date range.

    Args:
        since: Start date for the report.
        until: End date for the report.
        output_format: Output format ('json', 'yaml', 'markdown').

    Returns:
        Filename string with date range and appropriate extension.
    """
    start_str = since.strftime("%Y%m%d")
    end_str = until.strftime("%Y%m%d")

    if start_str == end_str:
        date_part = start_str
    else:
        date_part = f"{start_str}_to_{end_str}"

    extension = {"json": "json", "yaml": "yaml", "markdown": "md"}.get(
        output_format, "md"
    )

    return f"pagerduty_report_{date_part}.{extension}"


def generate_markdown_report(incidents: List[Dict[str, Any]]) -> str:
    """Generates a markdown formatted report.

    Args:
        incidents: List of enriched incident dictionaries.

    Returns:
        Markdown formatted report as a string.
    """
    report = [
        "# PagerDuty Incident Report",
        "",
        f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Incidents:** {len(incidents)}",
        "",
    ]

    if not incidents:
        report.append("No incidents found for the specified time period.")
        return "\n".join(report)

    # Group by service
    services = {}
    for incident in incidents:
        service = incident["service"]
        if service not in services:
            services[service] = []
        services[service].append(incident)

    for service, service_incidents in services.items():
        report.extend(
            [
                f"## {service}",
                "",
                f"**Incidents:** {len(service_incidents)}",
                "",
            ]
        )

        for incident in service_incidents:
            report.extend(
                [
                    f"### Incident #{incident['incident_number']}: {incident['title']}",
                    "",
                    f"- **Status:** {incident['status']}",
                    f"- **Urgency:** {incident['urgency']}",
                    f"- **Priority:** {incident['priority']}",
                    f"- **Created:** {incident['created_at']}",
                    f"- **Assignees:** {', '.join(incident['assignees']) if incident['assignees'] else 'None'}",
                    "",
                ]
            )

            if incident["description"]:
                report.extend(
                    [
                        "**Description:**",
                        f"{incident['description']}",
                        "",
                    ]
                )

            if incident["alerts"]:
                report.extend(
                    [
                        "**Alerts:**",
                        "",
                    ]
                )
                for alert in incident["alerts"]:
                    report.append(
                        f"- {alert['summary']} (Status: {alert['status']}, Severity: {alert['severity']})"
                    )
                report.append("")

            if incident["notes"]:
                report.extend(
                    [
                        "**Notes:**",
                        "",
                    ]
                )
                for note in incident["notes"]:
                    report.append(
                        f"- **{note['user']}** ({note['created_at']}): {note['content']}"
                    )
                report.append("")

            report.append("---")
            report.append("")

    return "\n".join(report)


@click.command()
@click.option("--interval", "-i", help="Time interval (e.g., 1d, 2w, 1m, 12h)")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "yaml", "markdown"]),
    default="markdown",
    help="Output format",
)
@click.option("--file", "-f", help="Output file path")
def main(interval: Optional[str], output: str, file: Optional[str]) -> None:
    """Generates PagerDuty incident report for specified services.

    This script fetches incident data from PagerDuty services, enriches it
    with alerts and notes, and generates reports in multiple formats.

    Args:
        interval: Time interval string (e.g., '7d', '1m', '12h').
        output: Output format ('json', 'yaml', 'markdown').
        file: Optional output file path. If not provided, saves to
              pagerduty_reports/ directory with auto-generated filename.
    """

    if not PAGERDUTY_API_KEY:
        console.print(
            "[red]Error: PAGERDUTY_API_KEY environment variable not set[/red]"
        )
        return

    if not PAGERDUTY_SERVICES or not any(s.strip() for s in PAGERDUTY_SERVICES):
        console.print(
            "[red]Error: PAGERDUTY_SERVICES environment variable not set or empty[/red]"
        )
        return

    # Determine time range
    if interval:
        try:
            time_delta = parse_time_interval(interval)
            until = datetime.now()
            since = until - time_delta
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
    else:
        since, until = get_default_time_range()

    services_list = ", ".join(s.strip() for s in PAGERDUTY_SERVICES if s.strip())
    time_range = (
        f"{since.strftime('%Y-%m-%d %H:%M')} to {until.strftime('%Y-%m-%d %H:%M')}"
    )

    console.print(
        Panel(
            f"Generating PagerDuty report\n"
            f"Services: {services_list}\n"
            f"Time range: {time_range}",
            title="PagerDuty Report Generator",
        )
    )

    # Initialize client and fetch data
    client = PagerDutyClient(PAGERDUTY_API_KEY)

    try:
        incidents = client.get_incidents(PAGERDUTY_SERVICES, since, until)
        enriched_incidents = client.enrich_incident_data(incidents)

        console.print(f"[green]Found {len(enriched_incidents)} incidents[/green]")

        # Display rich output to stdout
        display_rich_report(enriched_incidents, since, until)

        # Generate report content
        if output == "json":
            report_content = json.dumps(enriched_incidents, indent=2, default=str)
        elif output == "yaml":
            report_content = yaml.dump(enriched_incidents, default_flow_style=False)
        else:  # markdown
            report_content = generate_markdown_report(enriched_incidents)

        # Handle file output
        if file:
            # Use provided filename
            output_file = Path(file)
        else:
            # Create default filename in pagerduty_reports directory
            reports_dir = Path("pagerduty_reports")
            reports_dir.mkdir(exist_ok=True)
            filename = generate_filename(since, until, output)
            output_file = reports_dir / filename

        # Write report to file
        output_file.write_text(report_content)
        console.print(f"\n[green]✅ Report saved to {output_file}[/green]")

        # Save last run timestamp
        save_last_run()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return


if __name__ == "__main__":
    main()
