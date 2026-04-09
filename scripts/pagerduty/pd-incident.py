#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests",
#     "python-dotenv",
#     "rich",
#     "pyperclip",
# ]
# bin-name = "pd-incident"
# ///

"""PagerDuty incident details fetcher.

This script fetches detailed information about PagerDuty incidents including
alerts, notes, and event details. Supports multiple output formats.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
import pyperclip
from pathlib import Path

# Constants
_PAGERDUTY_BASE_URL = "https://api.pagerduty.com"
_PAGERDUTY_API_VERSION = "application/vnd.pagerduty+json;version=2"
_DEFAULT_DOMAIN = ""
_OUTPUT_FORMATS = ["text", "markdown", "compact", "json"]
_JSON_INDENT = 2
_PAYLOAD_INDENT = 8

console = Console(
    stderr=True
)  # Send Rich output to stderr so it doesn't interfere with piping


def load_api_key() -> str:
    """Loads PagerDuty API key from environment variables or .env file.

    Returns:
        The PagerDuty API key.

    Raises:
        SystemExit: If no API key is found in environment variables.
    """
    load_dotenv()

    api_key = os.getenv("PAGERDUTY_API_KEY") or os.getenv("PD_API_KEY")
    if not api_key:
        console.print(
            "[red]Error: PagerDuty API key not found. Set PAGERDUTY_API_KEY or "
            "PD_API_KEY environment variable.[/red]"
        )
        sys.exit(1)

    return api_key


def get_incident_details(incident_id: str, api_key: str) -> Dict[str, Any]:
    """Fetches incident details from PagerDuty API.

    Args:
        incident_id: PagerDuty incident ID or number.
        api_key: PagerDuty API key.

    Returns:
        Dictionary containing incident details from the API.

    Raises:
        SystemExit: If API request fails.
    """
    url = f"{_PAGERDUTY_BASE_URL}/incidents/{incident_id}"

    headers = {
        "Authorization": f"Token token={api_key}",
        "Accept": _PAGERDUTY_API_VERSION,
        "Content-Type": "application/json",
    }

    with console.status(f"[bold green]Fetching incident details for {incident_id}..."):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error fetching incident: {e}[/red]")
            sys.exit(1)


def get_incident_notes(incident_id: str, api_key: str) -> List[Dict[str, Any]]:
    """Fetches incident notes from PagerDuty API.

    Args:
        incident_id: PagerDuty incident ID or number.
        api_key: PagerDuty API key.

    Returns:
        List of incident notes dictionaries.
    """
    url = f"{_PAGERDUTY_BASE_URL}/incidents/{incident_id}/notes"

    headers = {
        "Authorization": f"Token token={api_key}",
        "Accept": _PAGERDUTY_API_VERSION,
        "Content-Type": "application/json",
    }

    with console.status(f"[bold blue]Fetching incident notes for {incident_id}..."):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("notes", [])
        except requests.exceptions.RequestException as e:
            console.print(
                f"[yellow]Warning: Could not fetch incident notes: {e}[/yellow]"
            )
            return []


def get_incident_alerts(incident_id: str, api_key: str) -> List[Dict[str, Any]]:
    """Fetches incident alerts/events from PagerDuty API.

    Args:
        incident_id: PagerDuty incident ID or number.
        api_key: PagerDuty API key.

    Returns:
        List of incident alerts dictionaries.
    """
    url = f"{_PAGERDUTY_BASE_URL}/incidents/{incident_id}/alerts"

    headers = {
        "Authorization": f"Token token={api_key}",
        "Accept": _PAGERDUTY_API_VERSION,
        "Content-Type": "application/json",
    }

    with console.status(f"[bold cyan]Fetching incident alerts for {incident_id}..."):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("alerts", [])
        except requests.exceptions.RequestException as e:
            console.print(
                f"[yellow]Warning: Could not fetch incident alerts: {e}[/yellow]"
            )
            return []


def format_datetime(dt_str: Optional[str]) -> str:
    """Formats datetime string to readable format.

    Args:
        dt_str: ISO datetime string or None.

    Returns:
        Formatted datetime string or "N/A" if input is None/invalid.
    """
    if not dt_str:
        return "N/A"

    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        return dt_str


def clean_json_payload(payload: Any) -> Any:
    """Recursively cleans JSON payload by converting \\n to actual newlines.

    Args:
        payload: JSON payload data (dict, list, str, or other).

    Returns:
        Cleaned payload with properly formatted newlines.
    """
    if isinstance(payload, dict):
        cleaned = {}
        for key, value in payload.items():
            cleaned[key] = clean_json_payload(value)
        return cleaned
    elif isinstance(payload, list):
        return [clean_json_payload(item) for item in payload]
    elif isinstance(payload, str):
        # Convert \n to actual newlines for better readability
        return payload.replace("\\n", "\n").replace("\\t", "  ")
    else:
        return payload


def extract_incident_info(
    incident_data: Dict[str, Any],
    notes: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Extracts relevant incident information from API responses.

    Args:
        incident_data: Raw incident data from API.
        notes: List of incident notes.
        alerts: List of incident alerts.

    Returns:
        Dictionary containing extracted and formatted incident information.
    """
    incident = incident_data.get("incident", {})

    service_name = "N/A"
    service_info = incident.get("service")
    if service_info:
        service_name = service_info.get("summary", service_info.get("name", "N/A"))

    # Extract domain from service or incident data - fallback to generic
    incident_url = (
        f"https://{_DEFAULT_DOMAIN}.pagerduty.com/incidents/{incident.get('id', 'N/A')}"
    )
    # Try to extract from HTML URL if available
    html_url = incident.get("html_url", "")
    if html_url:
        incident_url = html_url

    # Extract event details from alerts
    event_details = []
    for alert in alerts:
        body = alert.get("body", {})

        # Clean the raw payload to format newlines properly
        raw_payload = body.get("details", {})
        formatted_payload = clean_json_payload(raw_payload)

        event_detail = {
            "summary": alert.get("summary", "N/A"),
            "severity": alert.get("severity", "N/A"),
            "created_at": format_datetime(alert.get("created_at")),
            "status": alert.get("status", "N/A"),
            "source": body.get("details", {}).get("source", "N/A"),
            "raw_payload": formatted_payload,
            "full_alert": alert,
        }
        event_details.append(event_detail)

    return {
        "incident_number": incident.get("incident_number", "N/A"),
        "incident_url": incident_url,
        "title": incident.get("title", "N/A"),
        "status": incident.get("status", "N/A"),
        "service": service_name,
        "severity": incident.get("severity", "N/A"),
        "urgency": incident.get("urgency", "N/A"),
        "created_at": format_datetime(incident.get("created_at")),
        "updated_at": format_datetime(incident.get("updated_at")),
        "resolved_at": format_datetime(incident.get("resolved_at")),
        "description": incident.get("description", "N/A"),
        "notes": notes,
        "alerts": alerts,
        "event_details": event_details,
        "raw_json": incident_data,
    }


def format_text_output(info: Dict[str, Any]) -> str:
    """Formats incident information as plain text.

    Args:
        info: Extracted incident information dictionary.

    Returns:
        Plain text formatted string of incident details.
    """
    output = []
    output.append(f"Incident Number: {info['incident_number']}")
    output.append(f"Link: {info['incident_url']}")
    output.append(f"Title: {info['title']}")
    output.append(f"Service: {info['service']}")
    output.append(f"Status: {info['status']}")
    # output.append(f"Severity: {info['severity']}")
    # output.append(f"Urgency: {info['urgency']}")
    output.append(f"Created: {info['created_at']}")
    # output.append(f"Updated: {info['updated_at']}")
    # if info['resolved_at'] != "N/A":
    #     output.append(f"Resolved: {info['resolved_at']}")
    output.append(f"Description: {info['description']}")

    # Add event details
    if info["event_details"]:
        output.append("\nEvent Details:")
        for i, event in enumerate(info["event_details"], 1):
            output.append(f"  {i}. [{event['created_at']}] {event['summary']}")
            output.append(
                f"     Source: {event['source']} | Severity: {event['severity']} | Status: {event['status']}"
            )
            if event["raw_payload"]:
                # Format the payload nicely for text output
                formatted_payload = json.dumps(
                    event["raw_payload"], indent=_PAYLOAD_INDENT, ensure_ascii=False
                )
                # Replace escaped newlines with actual newlines
                formatted_payload = formatted_payload.replace("\\n", "\n").replace(
                    "\\t", "  "
                )
                output.append(f"     Raw Payload: {formatted_payload}")
    else:
        output.append("\nEvent Details: None")

    if info["notes"]:
        output.append("\nNotes:")
        for i, note in enumerate(info["notes"], 1):
            created = format_datetime(note.get("created_at"))
            content = note.get("content", "No content")
            user = note.get("user", {}).get("summary", "Unknown user")
            output.append(f"  {i}. [{created}] {user}: {content}")
    else:
        output.append("\nNotes: None")

    return "\n".join(output)


def format_compact_output(info: Dict[str, Any]) -> str:
    """Formats incident information in compact format for incident tracking.

    Args:
        info: Extracted incident information dictionary.

    Returns:
        Compact markdown formatted string suitable for tracking documents.
    """
    output = []

    # Date and incident link
    created_date = info["created_at"]
    output.append(f"**Date:** {created_date}")
    output.append(f"**PagerDuty:** {info['incident_url']}")
    output.append(f"**Alert:** {info['title']}")
    output.append("")

    # Raw payload from first event
    if info["event_details"]:
        event = info["event_details"][0]
        if event["raw_payload"]:
            output.append("```")
            # Extract just the message or most relevant payload
            payload = event["raw_payload"]
            if isinstance(payload, dict) and "message" in payload:
                message = payload["message"].replace("\\n", "\n").replace("\\t", "  ")
                output.append(message)
            else:
                formatted_payload = json.dumps(
                    payload, indent=_JSON_INDENT, ensure_ascii=False
                )
                formatted_payload = formatted_payload.replace("\\n", "\n").replace(
                    "\\t", "  "
                )
                output.append(formatted_payload)
            output.append("```")
            output.append("")

    # Solution section
    output.append("**Solution:**")
    output.append("```")
    if info["notes"]:
        # Use the last note as the solution
        last_note = info["notes"][-1]
        solution = last_note.get("content", "Add solution here")
        output.append(solution)
    else:
        output.append("Add solution here")
    output.append("```")
    output.append("")
    output.append("---")
    output.append("")

    return "\n".join(output)


def format_markdown_output(info: Dict[str, Any]) -> str:
    """Formats incident information as Markdown for Confluence.

    Args:
        info: Extracted incident information dictionary.

    Returns:
        Markdown formatted string suitable for Confluence documentation.
    """
    output = []
    output.append(f"## Incident {info['incident_number']}: {info['title']}")
    output.append(f"**Link:** {info['incident_url']}")
    output.append("")
    output.append("### Incident Details")
    # output.append(f"- **Incident Number:** {info['incident_number']}")
    output.append(f"- **Service:** {info['service']}")
    output.append(f"- **Status:** {info['status']}")
    # output.append(f"- **Severity:** {info['severity']}")
    # output.append(f"- **Urgency:** {info['urgency']}")
    output.append(f"- **Created:** {info['created_at']}")
    # output.append(f"- **Updated:** {info['updated_at']}")
    # if info['resolved_at'] != "N/A":
    #     output.append(f"- **Resolved:** {info['resolved_at']}")
    output.append("")
    output.append("### Description")
    output.append(info["description"])
    output.append("")

    # Add event details section
    if info["event_details"]:
        output.append("### Event Details")
        for i, event in enumerate(info["event_details"], 1):
            output.append(f"#### Event {i}: {event['summary']}")
            output.append(f"- **Created:** {event['created_at']}")
            # output.append(f"- **Source:** {event['source']}")
            output.append(f"- **Severity:** {event['severity']}")
            # output.append(f"- **Status:** {event['status']}")
            if event["raw_payload"]:
                output.append("- **Raw Payload:**")
                output.append("```json")
                # Use clean formatting for markdown - handle newlines properly
                formatted_payload = json.dumps(
                    event["raw_payload"], indent=_JSON_INDENT, ensure_ascii=False
                )
                # Replace escaped newlines with actual newlines in the final output
                formatted_payload = formatted_payload.replace("\\n", "\n").replace(
                    "\\t", "  "
                )
                output.append(formatted_payload)
                output.append("```")
            output.append("")
    else:
        output.append("### Event Details")
        output.append("No event details available.")
        output.append("")

    if info["notes"]:
        output.append("#### Notes & Updates")
        for note in info["notes"]:
            created = format_datetime(note.get("created_at"))
            content = note.get("content", "No content")
            user = note.get("user", {}).get("summary", "Unknown user")
            output.append(f"**{created} - {user}:**")
            output.append(content)
            output.append("")
    else:
        output.append("### Notes")
        output.append("No notes available.")
        output.append("")

    output.append("### Resolution Steps")
    output.append("- [ ] Step 1")
    output.append("- [ ] Step 2")
    output.append("- [ ] Step 3")
    output.append("")
    output.append("---")

    return "\n".join(output)


def format_json_output(info: Dict[str, Any]) -> str:
    """Formats incident information as JSON.

    Args:
        info: Extracted incident information dictionary.

    Returns:
        JSON formatted string of raw incident data.
    """
    return json.dumps(info["raw_json"], indent=_JSON_INDENT)


def main() -> None:
    """Main function to fetch and format PagerDuty incident details."""
    parser = argparse.ArgumentParser(
        description="Fetch PagerDuty incident details",
        epilog="""Examples:
  # Pipe to clipboard while seeing Rich feedback
  uv run pagerduty_incident.py Q3T5ALHBFDNITW --format compact | pbcopy
  
  # Copy directly to clipboard
  uv run pagerduty_incident.py Q3T5ALHBFDNITW --format compact --clipboard
  
  # Save to file
  uv run pagerduty_incident.py Q3T5ALHBFDNITW --format markdown --output incident.md
  
  # Save to file AND copy to clipboard
  uv run pagerduty_incident.py Q3T5ALHBFDNITW --format compact -c -o incident.txt""",
    )
    parser.add_argument("incident_id", help="PagerDuty incident ID or number")
    parser.add_argument(
        "--format",
        "-f",
        choices=_OUTPUT_FORMATS,
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--clipboard",
        "-c",
        action="store_true",
        help="Copy output to clipboard",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save output to file",
    )

    args = parser.parse_args()

    console.print("[bold blue]🔍 PagerDuty Incident Fetcher[/bold blue]")
    console.print(f"[dim]Fetching details for incident: {args.incident_id}[/dim]")
    console.print()

    api_key = load_api_key()

    # Fetch incident details
    incident_data = get_incident_details(args.incident_id, api_key)
    notes = get_incident_notes(args.incident_id, api_key)
    alerts = get_incident_alerts(args.incident_id, api_key)

    # Extract and format information
    with console.status("[bold magenta]Processing incident data..."):
        info = extract_incident_info(incident_data, notes, alerts)

    # Create summary table
    table = Table(title=f"📊 Incident {args.incident_id} Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Incident Number", str(info["incident_number"]))
    table.add_row("Service", str(info["service"]))
    table.add_row("Status", str(info["status"]))
    table.add_row("Created", str(info["created_at"]))
    table.add_row("Alerts Found", str(len(info["alerts"])))
    table.add_row("Notes Found", str(len(info["notes"])))
    table.add_row("Output Format", args.format.upper())

    console.print(table)
    console.print()  # Add blank line before output

    # Generate formatted output
    if args.format == "text":
        formatted_output = format_text_output(info)
    elif args.format == "markdown":
        formatted_output = format_markdown_output(info)
    elif args.format == "compact":
        formatted_output = format_compact_output(info)
    elif args.format == "json":
        formatted_output = format_json_output(info)
    else:
        formatted_output = format_text_output(info)  # fallback

    # Handle output destinations
    if args.output:
        # Save to file
        output_path = Path(args.output)
        output_path.write_text(formatted_output)
        console.print(f"[green]✅ Output saved to {output_path}[/green]")

    if args.clipboard:
        # Copy to clipboard
        try:
            pyperclip.copy(formatted_output)
            console.print("[green]✅ Output copied to clipboard[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not copy to clipboard: {e}[/yellow]")

    # Print to stdout (for piping or normal display)
    # Skip stdout only if we're saving to file AND copying to clipboard (both specified)
    if not (args.output and args.clipboard):
        print(formatted_output)


if __name__ == "__main__":
    main()
