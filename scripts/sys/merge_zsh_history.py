#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "rich>=13.7",
#   "typer>=0.12",
# ]
# ///

"""Merge zsh history backups into an active history file.

Usage:
    ./merge_zsh_history.py --dry-run backup.zsh_history
    ./merge_zsh_history.py backup.zsh_history
    ./merge_zsh_history.py --output /tmp/merged.zsh_history backup.zsh_history

Extended history keeps zsh metadata records like ``: timestamp:duration;command``.
Plain history writes one command per line. When plain entries are written as
extended history, they receive incremental synthetic timestamps immediately before
the oldest real timestamp. When extended entries are written as plain history,
timestamp and duration metadata is stripped after confirmation.

Verification:
    python3 -m py_compile merge_zsh_history.py
    UV_CACHE_DIR=.uv-cache ./merge_zsh_history.py --dry-run backup.zsh_history
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


app = typer.Typer(
    add_completion=False,
    help="Merge zsh history backups into your active .zsh_history safely.",
)
console = Console()
HISTORY_RECORD_RE = re.compile(r"^: (\d+):(\d+);")


@dataclass(frozen=True)
class HistoryRecord:
    text: str
    command: str
    timestamp: int
    has_metadata: bool


@dataclass(frozen=True)
class ParsedHistory:
    records: list[HistoryRecord]
    format_name: str  # "plain" or "extended"


def parse_history(path: Path) -> ParsedHistory:
    text = path.read_text(errors="replace")
    lines = text.splitlines(keepends=True)

    if not any(HISTORY_RECORD_RE.match(line) for line in lines):
        return ParsedHistory(
            records=[
                HistoryRecord(text=line, command=line, timestamp=0, has_metadata=False)
                for line in lines
                if line
            ],
            format_name="plain",
        )

    chunks: list[str] = []
    current: list[str] | None = None

    for line in lines:
        if HISTORY_RECORD_RE.match(line):
            if current is not None:
                chunks.append("".join(current))
            current = [line]
        else:
            if current is None:
                current = [line]
            else:
                current.append(line)

    if current is not None:
        chunks.append("".join(current))

    records: list[HistoryRecord] = []
    for chunk in chunks:
        match = HISTORY_RECORD_RE.match(chunk)
        if match:
            records.append(HistoryRecord(
                text=chunk,
                command=chunk[match.end():],
                timestamp=int(match.group(1)),
                has_metadata=True,
            ))
        else:
            records.append(HistoryRecord(text=chunk, command=chunk, timestamp=0, has_metadata=False))

    return ParsedHistory(records=records, format_name="extended")


def backup_path_for(history_file: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return history_file.with_name(f"{history_file.name}.pre-merge-{stamp}")


def newest_by_command(records: list[HistoryRecord]) -> dict[str, HistoryRecord]:
    newest: dict[str, HistoryRecord] = {}
    for record in records:
        old = newest.get(record.command)
        if old is None or record.timestamp >= old.timestamp:
            newest[record.command] = record
    return newest


def command_with_newline(command: str) -> str:
    return command if command.endswith("\n") else f"{command}\n"


def oldest_timestamp(records: list[HistoryRecord]) -> int:
    timestamps = [r.timestamp for r in records if r.timestamp > 0]
    return min(timestamps) if timestamps else int(datetime.now().timestamp())


def assign_synthetic_timestamps(records: list[HistoryRecord]) -> dict[int, int]:
    plain_records = [r for r in records if not r.has_metadata]
    synthetic_start = max(1, oldest_timestamp(records) - len(plain_records))
    return {id(r): synthetic_start + i for i, r in enumerate(plain_records)}


def render_plain(records: list[HistoryRecord]) -> str:
    return "".join(command_with_newline(r.command) for r in records)


def render_extended(records: list[HistoryRecord]) -> str:
    synthetic = assign_synthetic_timestamps(records)
    rendered: list[str] = []
    for r in records:
        if r.has_metadata:
            rendered.append(r.text)
        else:
            rendered.append(f": {synthetic[id(r)]}:0;{command_with_newline(r.command)}")
    return "".join(rendered)


def render_history(records: list[HistoryRecord], output_format: str) -> str:
    return render_plain(records) if output_format == "plain" else render_extended(records)


def resolve_output_format(requested: str, current_format: str) -> str:
    if requested not in {"auto", "plain", "extended"}:
        raise typer.BadParameter("--format must be one of: auto, plain, extended")
    return current_format if requested == "auto" else requested


def render_summary(
    sources: list[tuple[str, str, int, int]],
    total_records: int,
    final_unique_commands: int,
    output_format: str,
    backup_message: str,
    target: Path,
    conversion_warnings: list[str],
) -> None:
    table = Table(title="zsh history merge")
    table.add_column("File", overflow="fold")
    table.add_column("Format")
    table.add_column("Records", justify="right")
    table.add_column("Unique commands", justify="right")
    for file_name, fmt, records, unique in sources:
        table.add_row(file_name, fmt, str(records), str(unique))

    result_table = Table.grid(expand=False)
    result_table.add_column("Metric", style="bold", no_wrap=True)
    result_table.add_column("Value", justify="right")
    result_table.add_row("Target", str(target))
    result_table.add_row("Input records", str(total_records))
    result_table.add_row("Final unique commands", str(final_unique_commands))
    result_table.add_row("Deduped records", str(total_records - final_unique_commands))
    result_table.add_row("Output format", output_format)
    result_table.add_row("Backup", backup_message)

    console.print(table)
    console.print(Panel.fit(result_table, title="Result"))
    for warning in conversion_warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")


def confirm_conversion_if_needed(conversion_warnings: list[str], yes: bool) -> None:
    if not conversion_warnings or yes:
        return
    console.print()
    if not typer.confirm("Continue with this history format conversion?"):
        raise typer.Abort()


@app.command()
def merge(
    backups: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="One or more .zsh_history backup files to merge.",
        ),
    ],
    history_file: Annotated[
        Path,
        typer.Option("--history-file", "-H", help="History file to update."),
    ] = Path.home() / ".zsh_history",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write merged history here instead of replacing the history file."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be merged without writing anything."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: auto, plain, or extended."),
    ] = "auto",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts for format conversions."),
    ] = False,
) -> None:
    """Back up the active zsh history file and merge backups into it."""
    target = history_file.expanduser().resolve()
    destination = output.expanduser().resolve() if output else target

    if not target.exists():
        raise typer.BadParameter(f"history file does not exist: {target}")

    parsed_target = parse_history(target)
    resolved_format = resolve_output_format(output_format, parsed_target.format_name)

    all_records: list[HistoryRecord] = list(parsed_target.records)
    sources: list[tuple[str, str, int, int]] = [
        (str(target), parsed_target.format_name, len(parsed_target.records),
         len({r.command for r in parsed_target.records}))
    ]

    for path in backups:
        parsed = parse_history(path.expanduser().resolve())
        all_records.extend(parsed.records)
        sources.append((str(path), parsed.format_name, len(parsed.records),
                        len({r.command for r in parsed.records})))

    merged_records = list(newest_by_command(all_records).values())

    if resolved_format == "extended":
        synthetic = assign_synthetic_timestamps(merged_records)
        merged = sorted(
            merged_records,
            key=lambda r: (r.timestamp if r.has_metadata else synthetic[id(r)], r.command),
        )
    else:
        merged = sorted(merged_records, key=lambda r: (r.timestamp, r.command))

    conversion_warnings: list[str] = []
    if resolved_format == "plain" and any(r.has_metadata for r in merged_records):
        conversion_warnings.append(
            "Extended timestamp/duration metadata will be stripped from output."
        )
    if resolved_format == "extended" and any(not r.has_metadata for r in merged_records):
        synthetic = assign_synthetic_timestamps(merged_records)
        conversion_warnings.append(
            "Plain entries will receive synthetic incremental timestamps "
            f"from {min(synthetic.values())} to {max(synthetic.values())}."
        )

    backup_path: Path | None = None
    if dry_run:
        backup_message = "skipped for dry run"
    elif output is not None:
        backup_message = "not needed; wrote to --output"
    else:
        backup_path = backup_path_for(target)
        backup_message = str(backup_path)

    render_summary(
        sources=sources,
        total_records=len(all_records),
        final_unique_commands=len(merged),
        output_format=resolved_format,
        backup_message=backup_message,
        target=destination,
        conversion_warnings=conversion_warnings,
    )

    if dry_run:
        console.print("[yellow]Dry run only. No files were changed.[/yellow]")
        return

    confirm_conversion_if_needed(conversion_warnings, yes=yes)

    if backup_path is not None:
        shutil.copy2(target, backup_path)
    destination.write_text(render_history(merged, resolved_format))
    if backup_path is not None:
        shutil.copymode(backup_path, destination)

    console.print("[green]Merge complete.[/green]")


if __name__ == "__main__":
    app()
