#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "kubernetes",
#   "rich",
#   "inquirerpy",
#   "typer",
# ]
# bin-name = "k8s-hpa-analyzer"
# ///

from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from contextlib import nullcontext

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text
from rich import box

import typer
from InquirerPy import inquirer

console = Console()


class HPAAnalyzer:
    def __init__(self, namespace: Optional[str] = None):
        """Initialize the HPA analyzer using the Kubernetes Python client."""
        self.namespace = namespace
        try:
            try:
                config.load_kube_config()
            except ConfigException as e:
                console.print(f"[bold red]Kubeconfig error:[/bold red] {e}")
                try:
                    config.load_incluster_config()
                except ConfigException as e2:
                    console.print(f"[bold red]In-cluster config error:[/bold red] {e2}")
                    console.print("[bold red]Could not load Kubernetes configuration. Exiting.[/bold red]")
                    raise SystemExit(1)
                except Exception as e2:
                    console.print(f"[bold red]Unexpected error loading in-cluster config:[/bold red] {e2}")
                    raise SystemExit(1)
            except Exception as e:
                console.print(f"[bold red]Unexpected error loading kubeconfig:[/bold red] {e}")
                raise SystemExit(1)
            self.autoscaling_api = client.AutoscalingV2Api()
            self.core_api = client.CoreV1Api()
        except Exception as e:
            console.print(f"[bold red]Failed to initialize Kubernetes client:[/bold red] {e}")
            raise SystemExit(1)

    def get_all_hpas(self) -> List[client.V2HorizontalPodAutoscaler]:
        """Get list of all HPAs across all or specified namespace."""
        try:
            with console.status("[bold green]Retrieving HPAs..."):
                if self.namespace:
                    resp = self.autoscaling_api.list_namespaced_horizontal_pod_autoscaler(self.namespace)
                else:
                    resp = self.autoscaling_api.list_horizontal_pod_autoscaler_for_all_namespaces()
            return resp.items
        except ApiException as e:
            console.print(f"[bold red]Error fetching HPAs:[/bold red] {e}")
            return []

    def get_hpa_details(self, name: str, namespace: str) -> Optional[client.V2HorizontalPodAutoscaler]:
        """Get detailed information about a specific HPA."""
        try:
            with console.status(f"[bold green]Retrieving details for HPA {name}..."):
                return self.autoscaling_api.read_namespaced_horizontal_pod_autoscaler(name, namespace)
        except ApiException as e:
            console.print(f"[bold red]Error fetching HPA details:[/bold red] {e}")
            return None

    def parse_metrics(self, status_metrics: Optional[List[Any]], spec_metrics: Optional[List[Any]]) -> List[Tuple[str, Any, Any, str]]:
        """Parse metrics from HPA status and spec.

        Args:
            status_metrics: List of metric status objects from HPA status
            spec_metrics: List of metric spec objects from HPA spec

        Returns:
            List of tuples (metric_name, current_value, target_value, unit)
        """
        parsed_metrics: List[Tuple[str, Any, Any, str]] = []
        if not status_metrics:
            return parsed_metrics

        # Build a lookup for spec metrics by type and resource name
        spec_lookup = {}
        for metric in spec_metrics or []:
            if getattr(metric, 'type', None) == 'Resource':
                resource = getattr(metric, 'resource', None)
                if resource and hasattr(resource, 'name'):
                    spec_lookup[(metric.type, resource.name)] = resource

        for metric in status_metrics:
            if getattr(metric, 'type', None) == 'Resource':
                resource = getattr(metric, 'resource', None)
                name = resource.name if resource and hasattr(resource, 'name') else 'unknown'
                current_obj = getattr(resource, 'current', None)

                # Find the matching spec metric for the target
                spec_resource = spec_lookup.get((metric.type, name))
                target_obj = getattr(spec_resource, 'target', None) if spec_resource else None

                if current_obj and hasattr(current_obj, 'average_utilization'):
                    current = f"{current_obj.average_utilization}%"
                    target = f"{target_obj.average_utilization}%" if target_obj and hasattr(target_obj, 'average_utilization') else "N/A"
                    unit = "percentage of request"
                else:
                    current = getattr(current_obj, 'average_value', 'N/A') if current_obj else 'N/A'
                    target = getattr(target_obj, 'average_value', 'N/A') if target_obj else 'N/A'
                    unit = "absolute value"
                parsed_metrics.append((name, current, target, unit))
        return parsed_metrics

    def get_recent_events(self, name: str, namespace: str, show_status: bool = True) -> str:
        """Get recent events for an HPA."""
        try:
            status_context = console.status(f"[bold green]Retrieving events for HPA {name}...") if show_status else nullcontext()
            with status_context:
                field_selector = f"involvedObject.name={name},involvedObject.kind=HorizontalPodAutoscaler"
                events = self.core_api.list_namespaced_event(
                    namespace=namespace,
                    field_selector=field_selector,
                    _preload_content=True
                )
            if not events.items:
                return "No recent scaling events found"
            # Sort by lastTimestamp descending
            sorted_events = sorted(events.items, key=self._event_sort_key, reverse=True)
            lines = []
            for event in sorted_events[:5]:
                ts = event.last_timestamp or event.event_time or ''
                msg = event.message or ''
                reason = event.reason or ''
                lines.append(f"[b]{ts}[/b]: {reason} - {msg}")
            return "\n".join(lines)
        except ApiException as e:
            return f"[bold red]Error fetching events:[/bold red] {e}"

    @staticmethod
    def _event_sort_key(event: Any) -> datetime:
        """Return a comparable timestamp for sorting events."""
        for attribute in ("last_timestamp", "event_time", "first_timestamp"):
            value = getattr(event, attribute, None)
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            if isinstance(value, str) and value:
                try:
                    cleaned_value = value.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(cleaned_value)
                    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        return datetime.min.replace(tzinfo=timezone.utc)

    def analyze_and_print_hpas(
        self,
        hpas: Optional[List[client.V2HorizontalPodAutoscaler]] = None,
        disable_cli_pager: bool = False,
    ) -> None:
        """Analyze and print information about the provided HPAs."""
        hpas = hpas if hpas is not None else self.get_all_hpas()
        if not hpas:
            console.print("[bold yellow]No HPAs found[/bold yellow]" + (f" in namespace [bold]{self.namespace}[/bold]" if self.namespace else " in the cluster"))
            return

        total_hpas = len(hpas)
        render_context = console.pager(styles=True) if total_hpas > 1 and not disable_cli_pager else nullcontext()
        use_spinner = total_hpas == 1

        with render_context:
            console.rule(f"[bold blue]HPA Analysis Report[/bold blue] ({total_hpas})")
            console.print(f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")
            status_indicator = Status("[bold green]Analyzing HPAs...[/bold green]", console=console, spinner="dots") if use_spinner else None
            if status_indicator:
                status_indicator.start()
            try:
                for index, hpa in enumerate(hpas, start=1):
                    if status_indicator:
                        status_indicator.update(f"[bold green]Analyzing HPAs ({index}/{total_hpas})...[/bold green]")
                    else:
                        console.print(f"[dim]Analyzing HPAs ({index}/{total_hpas})...[/dim]")
                    metadata = hpa.metadata
                    spec = hpa.spec
                    status = hpa.status

                    hpa_name = metadata.name
                    hpa_namespace = metadata.namespace

                    # Basic Information Table
                    info_table = Table(show_header=False, box=box.SIMPLE)
                    info_table.add_row("Created", str(metadata.creation_timestamp))
                    info_table.add_row("Target", f"{spec.scale_target_ref.kind}/{spec.scale_target_ref.name}")

                    # Scaling Configuration Table
                    scaling_table = Table(show_header=False, box=box.SIMPLE)
                    scaling_table.add_row("Min Replicas", str(spec.min_replicas))
                    scaling_table.add_row("Max Replicas", str(spec.max_replicas))
                    scaling_table.add_row("Current Replicas", str(getattr(status, 'current_replicas', 'N/A')))
                    scaling_table.add_row("Desired Replicas", str(getattr(status, 'desired_replicas', 'N/A')))

                    # Metrics Table
                    metrics = self.parse_metrics(
                        getattr(status, 'current_metrics', []),
                        getattr(spec, 'metrics', [])
                    )
                    metrics_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
                    metrics_table.add_column("Resource")
                    metrics_table.add_column("Current")
                    metrics_table.add_column("Target")
                    metrics_table.add_column("Unit")
                    if metrics:
                        for name, current, target, unit in metrics:
                            metrics_table.add_row(name, str(current), str(target), unit)
                    else:
                        metrics_table.add_row("No metrics available", "-", "-", "-")

                    # Conditions Table
                    conditions_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
                    conditions_table.add_column("Type")
                    conditions_table.add_column("Status")
                    conditions_table.add_column("Reason")
                    conditions_table.add_column("Message")
                    for condition in getattr(status, 'conditions', []) or []:
                        condition_type = getattr(condition, 'type', 'Unknown')
                        condition_status = getattr(condition, 'status', 'Unknown')
                        condition_reason = getattr(condition, 'reason', 'Unknown')
                        condition_message = getattr(condition, 'message', 'No message')

                        status_style = "bold black on light_green"
                        if condition_status == "False":
                            status_style = "bold black on dark_orange"
                        elif condition_status == "Unknown":
                            status_style = "bold black on khaki1"

                        conditions_table.add_row(
                            condition_type,
                            Text(condition_status, style=status_style),
                            condition_reason,
                            condition_message,
                        )

                    # Scaling Behavior Table
                    behavior_panel = None
                    behavior = getattr(spec, 'behavior', None)
                    if behavior:
                        behavior_table = Table(title="Scaling Behavior", show_header=True, header_style="bold green", box=box.SIMPLE)
                        behavior_table.add_column("Direction")
                        behavior_table.add_column("Stabilization Window (s)")
                        behavior_table.add_column("Policy Type")
                        behavior_table.add_column("Policy Value")
                        behavior_table.add_column("Period (s)")
                        # Scale Down
                        scale_down = getattr(behavior, 'scale_down', None)
                        if scale_down:
                            for policy in getattr(scale_down, 'policies', []) or []:
                                behavior_table.add_row(
                                    "Down",
                                    str(getattr(scale_down, 'stabilization_window_seconds', 'N/A')),
                                    str(policy.type),
                                    str(policy.value),
                                    str(policy.period_seconds)
                                )
                        # Scale Up
                        scale_up = getattr(behavior, 'scale_up', None)
                        if scale_up:
                            for policy in getattr(scale_up, 'policies', []) or []:
                                behavior_table.add_row(
                                    "Up",
                                    str(getattr(scale_up, 'stabilization_window_seconds', 'N/A')),
                                    str(policy.type),
                                    str(policy.value),
                                    str(policy.period_seconds)
                                )
                        behavior_panel = Panel(
                            behavior_table,
                            title="Scaling Behavior",
                            border_style="green",
                            title_align="left",
                        )

                    # Recent Events
                    events = self.get_recent_events(hpa_name, hpa_namespace, show_status=use_spinner)
                    events_panel = Panel(
                        events,
                        title="Recent Events",
                        border_style="yellow",
                        title_align="left",
                    )

                    # Compose the HPA Panel
                    hpa_table = Table(show_header=False, box=box.SIMPLE)
                    hpa_table.add_row("Namespace", hpa_namespace)
                    hpa_table.add_row("Name", hpa_name)
                    hpa_panel = Panel(
                        hpa_table,
                        title=f"{hpa_name}",
                        border_style="blue",
                        title_align="left",
                    )

                    console.rule()
                    console.print(hpa_panel)
                    console.print(
                        Panel(
                            info_table,
                            title="Basic Information",
                            border_style="cyan",
                            title_align="left",
                        )
                    )
                    console.print(
                        Panel(
                            scaling_table,
                            title="Scaling Configuration",
                            border_style="cyan",
                            title_align="left",
                        )
                    )
                    console.print(
                        Panel(
                            metrics_table,
                            title="Scaling Metrics",
                            border_style="cyan",
                            title_align="left",
                        )
                    )
                    console.print(
                        Panel(
                            conditions_table,
                            title="Conditions",
                            border_style="cyan",
                            title_align="left",
                        )
                    )
                    if behavior_panel:
                        console.print(behavior_panel)
                    console.print(events_panel)
                    console.print("\n")
            finally:
                if status_indicator:
                    status_indicator.stop()

def main(
    namespace: Optional[str] = typer.Option(
        None,
        "--namespace",
        "-n",
        help="Limit analysis to a single namespace",
    ),
    all_hpas: bool = typer.Option(
        False,
        "--all-hpas",
        "-a",
        help="Analyze every HPA in scope without prompting",
    ),
    hpa: Optional[str] = typer.Option(
        None,
        "--hpa",
        help="Analyze one HPA (format namespace/name or just the name)",
    ),
    disable_cli_pager: bool = typer.Option(
        False,
        "--no-cli-pager",
        help="Print directly to stdout without opening a pager",
    ),
) -> None:
    if all_hpas and hpa:
        console.print("[bold red]Error:[/bold red] Use either --hpa or --all-hpas, not both.")
        raise typer.Exit(code=1)

    analyzer = HPAAnalyzer(namespace=namespace)

    if hpa:
        selected_namespace: Optional[str] = None
        hpa_name: str
        identifier = hpa.strip()

        if "/" in identifier:
            selected_namespace, hpa_name = identifier.split("/", 1)
        elif namespace:
            selected_namespace = namespace
            hpa_name = identifier
        else:
            hpas_in_scope = analyzer.get_all_hpas()
            if not hpas_in_scope:
                console.print("[bold yellow]No HPAs found in the cluster.[/bold yellow]")
                raise typer.Exit(code=0)
            matches = [
                hpa_obj for hpa_obj in hpas_in_scope if getattr(hpa_obj.metadata, "name", None) == identifier
            ]
            if not matches:
                namespace_matches = [
                    hpa_obj for hpa_obj in hpas_in_scope if getattr(hpa_obj.metadata, "namespace", None) == identifier
                ]
                console.print(f"[bold red]HPA '{identifier}' was not found by name.[/bold red]")
                if namespace_matches:
                    console.print(f"[bold yellow]Tip:[/bold yellow] '{identifier}' looks like a namespace. Use `--namespace {identifier} --hpa <name>` or `--hpa {identifier}/<name>`.")
                else:
                    console.print("[bold yellow]Tip:[/bold yellow] Use `--hpa namespace/name` or run without flags to pick interactively.")
                raise typer.Exit(code=1)
            if len(matches) > 1:
                choice = inquirer.fuzzy(
                    message=f"Multiple HPAs named '{identifier}'. Select one:",
                    choices=[f"{match.metadata.namespace}/{match.metadata.name}" for match in matches],
                    max_height=10,
                ).execute()
                selected_namespace, hpa_name = choice.split("/", 1)
            else:
                matched = matches[0]
                selected_namespace = getattr(matched.metadata, "namespace", None) or "default"
                hpa_name = getattr(matched.metadata, "name", identifier)

        if not selected_namespace:
            console.print("[bold red]Unable to determine namespace for the requested HPA.[/bold red]")
            raise typer.Exit(code=1)

        analyzer.namespace = selected_namespace
        hpa_detail = analyzer.get_hpa_details(hpa_name, selected_namespace)
        if not hpa_detail:
            console.print(f"[bold red]Unable to retrieve HPA '{selected_namespace}/{hpa_name}'.[/bold red]")
            console.print("[bold yellow]Tip:[/bold yellow] Use `--hpa namespace/name` or run without flags to select from the list.")
            raise typer.Exit(code=1)

        analyzer.analyze_and_print_hpas([hpa_detail], disable_cli_pager=disable_cli_pager)
        return

    if all_hpas:
        analyzer.analyze_and_print_hpas(disable_cli_pager=disable_cli_pager)
        return

    hpas = analyzer.get_all_hpas()
    if not hpas:
        if namespace:
            console.print(f"[bold yellow]No HPAs found[/bold yellow] in namespace [bold]{namespace}[/bold].")
        else:
            console.print("[bold yellow]No HPAs found in the cluster.[/bold yellow]")
        raise typer.Exit(code=0)

    choices = [f"{hpa_obj.metadata.namespace}/{hpa_obj.metadata.name}" for hpa_obj in hpas]
    selected_label = inquirer.fuzzy(
        message="Select an HPA:",
        choices=choices,
        max_height=10,
    ).execute()
    selected_namespace, selected_name = selected_label.split("/", 1)

    selected_hpa = next(
        (
            hpa_obj
            for hpa_obj in hpas
            if hpa_obj.metadata.namespace == selected_namespace and hpa_obj.metadata.name == selected_name
        ),
        None,
    )
    if not selected_hpa:
        console.print(f"[bold red]Selected HPA '{selected_label}' was not found.[/bold red]")
        raise typer.Exit(code=1)

    analyzer.analyze_and_print_hpas([selected_hpa], disable_cli_pager=disable_cli_pager)


if __name__ == "__main__":
    typer.run(main)
