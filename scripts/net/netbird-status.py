#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer>=0.9",
#     "rich>=13.0",
# ]
# bin-name = "netbird-status"
# ///

"""CLI helper that summarizes NetBird connection status.

We call `netbird status --json` so the parsing stays stable across releases and
avoid guessing at the human-readable format. Rich handles rendering.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence
import platform

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)

STATUS_COMMAND = ["netbird", "status", "--json"]


def ensure_binary_available() -> None:
    """Raise an error if the NetBird CLI is missing."""
    if shutil.which(STATUS_COMMAND[0]) is None:
        console.print(
            "[red]The `netbird` CLI is not on PATH. Install NetBird or update PATH."
        )
        raise typer.Exit(code=1)


def run_status_command() -> Dict[str, Any]:
    """Invoke `netbird status --json` and return parsed JSON."""
    try:
        result = subprocess.run(
            STATUS_COMMAND,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        console.print(f"[red]Failed to locate `{STATUS_COMMAND[0]}`: {error}")
        raise typer.Exit(code=1) from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        console.print("[red]`netbird status --json` failed to execute.")
        if stderr:
            console.print(f"[red]{stderr}")
        raise typer.Exit(code=error.returncode) from error

    payload = result.stdout.strip()
    if not payload:
        console.print("[red]NetBird returned an empty JSON payload.")
        raise typer.Exit(code=1)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        fallback = parse_text_status_output(payload)
        if fallback is not None:
            return fallback
        console.print(
            f"[red]Unable to decode JSON from NetBird (offset {error.pos}): {error.msg}"
        )
        raise typer.Exit(code=1) from error
    if not isinstance(data, dict):
        console.print("[red]NetBird returned JSON that is not an object.")
        raise typer.Exit(code=1)
    return data


def parse_text_status_output(payload: str) -> Dict[str, Any] | None:
    """Interpret plain-text status output returned when NetBird is not connected."""
    text = (payload or "").strip()
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    status: str | None = None
    for line in lines:
        lowered = line.lower()
        if lowered.startswith("daemon status"):
            _, _, value = line.partition(":")
            status_candidate = value.strip()
            if status_candidate:
                status = status_candidate
            break
        if lowered.startswith("status"):
            _, _, value = line.partition(":")
            status_candidate = value.strip()
            if status_candidate:
                status = status_candidate
            break

    text_lower = text.lower()
    if status is None:
        if "needslogin" in text_lower or "needs login" in text_lower:
            status = "NeedsLogin"
        elif "loggedout" in text_lower or "logged out" in text_lower:
            status = "LoggedOut"
        elif "needsregister" in text_lower or "needs register" in text_lower:
            status = "NeedsRegister"
        elif "disconnected" in text_lower:
            status = "Disconnected"

    suggestions: List[str] = []
    if "netbird up" in text_lower:
        suggestions.append("Run `netbird up` to log in.")

    fallback: Dict[str, Any] = {
        "status": status or "unknown",
        "statusHeadline": lines[0],
        "rawStatusOutput": text,
        "_fallback": "non_json",
    }
    if suggestions:
        fallback["suggestions"] = suggestions
    return fallback


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def format_relative(value: Any) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return str(value) if value else "-"
    now = datetime.now(parsed.tzinfo or timezone.utc)
    delta = now - parsed
    seconds = int(delta.total_seconds())
    if seconds < 1:
        return "now"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: List[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and len(parts) < 2:
        parts.append(f"{minutes}m")
    if len(parts) < 2 and sec:
        parts.append(f"{sec}s")
    return " ".join(parts) + " ago"


def format_bytes(value: Any) -> str:
    """Render byte counters using decimal units."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while number >= 1000 and index < len(units) - 1:
        number /= 1000
        index += 1
    return f"{number:.1f} {units[index]}"


def summarize_interface(data: Dict[str, Any]) -> Table:
    table = Table(title="Interface", show_edge=False, show_header=False)
    for key in ("name", "address", "addresses", "mtu"):
        if key in data:
            table.add_row(key.replace("_", " ").title(), Text(str(data[key])))
    return table


def extract_items(container: Any) -> List[Dict[str, Any]]:
    if isinstance(container, list):
        return [item for item in container if isinstance(item, dict)]
    if isinstance(container, dict):
        for key in ("details", "items", "entries", "list"):
            value = container.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def summarize_routes(routes: Sequence[Dict[str, Any]]) -> Table:
    table = Table(title="Routes")
    table.add_column("Network", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Via", style="green")
    table.add_column("Metric", justify="right")

    for route in routes:
        network = str(
            route.get("network") or route.get("cidr") or route.get("range") or "unknown"
        )
        route_type = str(route.get("type") or route.get("description") or "-")
        via = str(route.get("via") or route.get("gateway") or "-")
        metric = route.get("metric")
        table.add_row(network, route_type, via, "" if metric is None else str(metric))
    if not table.row_count:
        table.add_row("No routes", "-", "-")
    return table


def summarize_endpoint(title: str, payload: Dict[str, Any]) -> Table:
    table = Table(title=title, show_header=False, show_edge=False)
    for key in ("url", "connected", "error"):
        if key in payload:
            value = payload[key]
            table.add_row(key.replace("_", " ").title(), Text(str(value)))
    return table


def summarize_relays(relays: Dict[str, Any]) -> List[Table]:
    tables: List[Table] = []
    summary = Table(title="Relays", show_header=False, show_edge=False)
    for key in ("total", "available", "error"):
        if key in relays:
            summary.add_row(key.title(), Text(str(relays[key])))
    if summary.row_count:
        tables.append(summary)

    details = extract_items(relays)
    if details:
        detail_table = Table(title="Relay Endpoints")
        detail_table.add_column("URI", style="cyan")
        detail_table.add_column("Available", style="green")
        detail_table.add_column("Error", style="red")
        for entry in details:
            detail_table.add_row(
                str(entry.get("uri", "-")),
                str(entry.get("available", "-")),
                str(entry.get("error", "")),
            )
        tables.append(detail_table)
    return tables


def summarize_nameservers(entries: Sequence[Dict[str, Any]]) -> Table:
    table = Table(title="Nameservers")
    table.add_column("Domains", style="cyan", overflow="fold")
    table.add_column("Servers", style="green", overflow="fold")
    table.add_column("Status", style="magenta")
    table.add_column("Error", style="red", overflow="fold")

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        domains = ", ".join(entry.get("domains", [])) or "-"
        servers = ", ".join(entry.get("servers", [])) or "-"
        enabled = entry.get("enabled")
        status = "Available" if enabled and not entry.get("error") else "Unavailable"
        table.add_row(domains, servers, status, entry.get("error", ""))
    if not table.row_count:
        table.add_row("-", "-", "-", "-")
    return table


def summarize_events(events: Sequence[Dict[str, Any]], limit: int = 20) -> Table:
    table = Table(title="Events (latest)")
    table.add_column("Severity", style="magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Message", overflow="fold")
    table.add_column("When", justify="right")

    for event in events[:limit]:
        if not isinstance(event, dict):
            continue
        severity = event.get("severity", "-")
        category = event.get("category", "-")
        message = event.get("message") or event.get("userMessage") or "-"
        when = format_relative(event.get("timestamp"))
        table.add_row(str(severity), str(category), str(message), when)
    if not table.row_count:
        table.add_row("-", "-", "No events", "-")
    return table


def summarize_peers(peers: Sequence[Dict[str, Any]]) -> Table:
    table = Table(title="Peers")
    table.add_column("Name", style="cyan", overflow="fold")
    table.add_column("Status", style="green")
    table.add_column("Conn Type", style="magenta")
    table.add_column("Relay", style="yellow", overflow="fold")
    table.add_column("Latency", justify="right")
    table.add_column("Rx", justify="right")
    table.add_column("Tx", justify="right")
    table.add_column("Last Update", justify="right")
    table.add_column("Handshake", justify="right")

    for peer in peers:
        name = (
            peer.get("name")
            or peer.get("hostname")
            or peer.get("fqdn")
            or peer.get("id")
            or "-"
        )
        status = peer.get("status") or peer.get("state") or "-"
        connection_type = (
            peer.get("connectionType") or peer.get("connection_type") or "-"
        )
        relay = peer.get("relayAddress") or peer.get("relay") or "-"
        latency = peer.get("latency") or peer.get("latency_ms")
        if isinstance(latency, (int, float)):
            latency_display = f"{latency} ms"
        else:
            latency_display = str(latency or "-")
        rx_source = (
            peer.get("transferReceived")
            or peer.get("receive_bytes")
            or peer.get("rx_bytes")
            or 0
        )
        tx_source = (
            peer.get("transferSent")
            or peer.get("transmit_bytes")
            or peer.get("tx_bytes")
            or 0
        )
        rx = format_bytes(rx_source)
        tx = format_bytes(tx_source)
        status_update = format_relative(peer.get("lastStatusUpdate"))
        handshake = format_relative(
            peer.get("lastWireguardHandshake") or peer.get("last_handshake")
        )
        table.add_row(
            str(name),
            str(status),
            str(connection_type or "-"),
            str(relay or "-"),
            latency_display,
            rx,
            tx,
            status_update,
            handshake,
        )
    if not table.row_count:
        table.add_row("No peers", "-", "-", "-", "-", "-", "-", "-", "-")
    return table


def render_summary(data: Dict[str, Any]) -> None:
    status_value = data.get("status")
    if status_value is None:
        management = data.get("management")
        status_value = (
            "connected"
            if isinstance(management, dict) and management.get("connected")
            else "unknown"
        )
    status_text = Text(str(status_value), style="bold cyan")

    version_value = (
        data.get("version") or data.get("daemonVersion") or data.get("cliVersion")
    )
    version = Text(str(version_value or "unknown"), style="dim")

    peers_container = data.get("peers")
    peers_list = extract_items(peers_container)
    peer_total = (
        peers_container.get("total")
        if isinstance(peers_container, dict)
        and isinstance(peers_container.get("total"), int)
        else len(peers_list)
    )
    peer_connected = (
        peers_container.get("connected")
        if isinstance(peers_container, dict)
        and isinstance(peers_container.get("connected"), int)
        else sum(
            1
            for peer in peers_list
            if str(peer.get("status", "")).lower() in {"connected", "healthy", "online"}
        )
    )

    routes_container = data.get("routes")
    routes_list = extract_items(routes_container)
    route_total = (
        routes_container.get("total")
        if isinstance(routes_container, dict)
        and isinstance(routes_container.get("total"), int)
        else len(routes_list)
    )

    def endpoint_text(payload: Any) -> Text:
        if not isinstance(payload, dict):
            return Text("-")
        connected = payload.get("connected")
        state = "Connected" if connected else "Disconnected"
        text = Text(state, style="green" if connected else "red")
        url = payload.get("url")
        if url:
            text.append(" ")
            text.append(str(url), style="link " + str(url))
        error = payload.get("error")
        if error:
            text.append(f" ({error})", style="red")
        return text

    relays_info = data.get("relays")
    if isinstance(relays_info, dict):
        relays_total = relays_info.get("total")
        relays_available = relays_info.get("available")
    else:
        relays_total = relays_available = None

    dns_field = data.get("dnsServers")
    dns_entries = dns_field if isinstance(dns_field, list) else []
    dns_total = len(dns_entries)
    dns_available = sum(
        1
        for entry in dns_entries
        if isinstance(entry, dict) and entry.get("enabled") and not entry.get("error")
    )

    info_table = Table(show_header=False, show_edge=False)
    info_table.add_row("Status", status_text)
    headline = data.get("statusHeadline")
    if isinstance(headline, str) and headline:
        info_table.add_row("Daemon report", Text(headline))
    suggestions = data.get("suggestions")
    if isinstance(suggestions, list):
        for suggestion in suggestions:
            if isinstance(suggestion, str) and suggestion:
                info_table.add_row("Next step", Text(suggestion, style="yellow"))
    info_table.add_row("OS", Text(f"{platform.system().lower()}/{platform.machine()}"))
    info_table.add_row("Daemon", Text(str(data.get("daemonVersion") or "-")))
    info_table.add_row("CLI", Text(str(data.get("cliVersion") or "-")))
    info_table.add_row("Version", version)
    info_table.add_row("Management", endpoint_text(data.get("management")))
    info_table.add_row("Signal", endpoint_text(data.get("signal")))
    if relays_total is not None and relays_available is not None:
        info_table.add_row(
            "Relays", Text(f"{relays_available}/{relays_total} available")
        )
    if dns_total:
        info_table.add_row(
            "Nameservers", Text(f"{dns_available}/{dns_total} available")
        )
    info_table.add_row("Peers", Text(f"{peer_connected}/{peer_total} connected"))
    info_table.add_row("Routes", Text(str(route_total)))
    if isinstance(data.get("organizationName"), str):
        info_table.add_row("Org", Text(str(data["organizationName"])))
    if isinstance(data.get("fqdn"), str):
        info_table.add_row("FQDN", Text(str(data["fqdn"])))
    if isinstance(data.get("netbirdIp"), str):
        info_table.add_row("NetBird IP", Text(str(data["netbirdIp"])))
    uses_kernel = data.get("usesKernelInterface")
    interface_type = "Kernel" if uses_kernel else "Userspace"
    info_table.add_row("Interface", Text(interface_type))
    info_table.add_row("Quantum resistance", Text(str(data.get("quantumResistance"))))
    networks_field = data.get("networks")
    if isinstance(networks_field, list) and networks_field:
        joined = ", ".join(networks_field[:4])
        if len(networks_field) > 4:
            joined += f", +{len(networks_field) - 4} more"
        networks_text = Text(joined)
    else:
        networks_text = Text("-")
    info_table.add_row("Networks", networks_text)
    forwarding = data.get("forwardingRules")
    if isinstance(forwarding, int):
        info_table.add_row("Forwarding rules", Text(str(forwarding)))

    interface_data = data.get("interface")
    panels = [Panel.fit(info_table, title="NetBird")]
    if isinstance(interface_data, dict):
        panels.append(Panel(summarize_interface(interface_data)))
    console.print(*panels, sep="\n\n")


def render_details(data: Dict[str, Any]) -> None:
    raw_status_output = data.get("rawStatusOutput")
    if isinstance(raw_status_output, str) and raw_status_output:
        console.print(Panel(Text(raw_status_output), title="NetBird daemon output", expand=False))

    peers_container = data.get("peers")
    peers_list = extract_items(peers_container)
    if peers_list:
        if raw_status_output:
            console.print()
        console.print(summarize_peers(peers_list))
    routes_container = data.get("routes")
    routes_list = extract_items(routes_container)
    if routes_list:
        console.print()
        console.print(summarize_routes(routes_list))
    management_info = data.get("management")
    if isinstance(management_info, dict):
        console.print()
        console.print(summarize_endpoint("Management", management_info))
    signal_info = data.get("signal")
    if isinstance(signal_info, dict):
        console.print()
        console.print(summarize_endpoint("Signal", signal_info))
    relays_info = data.get("relays")
    if isinstance(relays_info, dict):
        for table in summarize_relays(relays_info):
            console.print()
            console.print(table)
    dns_field = data.get("dnsServers")
    if isinstance(dns_field, list) and dns_field:
        console.print()
        console.print(summarize_nameservers(dns_field))
    events_field = data.get("events")
    if isinstance(events_field, list) and events_field:
        console.print()
        console.print(summarize_events(events_field))
    meta = {
        key: value
        for key, value in data.items()
        if key
        not in {
            "peers",
            "routes",
            "interface",
            "status",
            "version",
            "management_url",
            "dashboard_url",
            "management",
            "signal",
            "relays",
            "daemonVersion",
            "cliVersion",
            "organizationName",
            "fqdn",
            "dnsServers",
            "events",
            "netbirdIp",
            "quantumResistance",
            "quantumResistancePermissive",
            "networks",
            "forwardingRules",
            "usesKernelInterface",
            "rawStatusOutput",
            "statusHeadline",
            "suggestions",
            "_fallback",
        }
    }
    if meta:
        meta_table = Table(title="Additional", show_edge=False, show_header=False)
        for key, value in sorted(meta.items()):
            meta_table.add_row(key.replace("_", " ").title(), Text(str(value)))
        console.print()
        console.print(meta_table)


@app.command()
def main(
    detail: bool = typer.Option(
        False,
        "--detail",
        "-d",
        help="Display detailed status information in human-readable format.",
    ),
    no_cli_pager: bool = typer.Option(
        False,
        "--no-cli-pager",
        help="Print detail output directly instead of using the Rich pager.",
    ),
) -> None:
    """Summarize the local NetBird agent status."""
    ensure_binary_available()

    with console.status("[bold cyan]Collecting NetBird status..."):
        data = run_status_command()

    render_summary(data)
    if detail:
        console.print()  # spacer
        if no_cli_pager:
            render_details(data)
        else:
            with console.pager(styles=True):
                render_details(data)


if __name__ == "__main__":
    app()
