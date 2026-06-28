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

The default output format follows the target history file. Extended history keeps
zsh metadata records like ``: timestamp:duration;command``. Plain history writes
one command per line. When plain entries are written as extended history, they
receive incremental synthetic timestamps immediately before the oldest real
timestamp. When extended entries are written as plain history, timestamp and
duration metadata is intentionally stripped after confirmation.

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
    format_name: str


def parse_history(path: Path) -> ParsedHistory:
    text = path.read_text(errors="replace")
    lines = text.splitlines(keepends=True)

    if not any(HISTORY_RECORD_RE.match(line) for line in lines):
        return ParsedHistory(
            records=[
                HistoryRecord(
                    text=line,
                    command=line,
                    timestamp=0,
                    has_metadata=False,
                )
                for line in lines
                if line
            ],
            format_name="plain",
        )

    records: list[str] = []
    current: list[str] | None = None
    saw_plain_prefix = False

    for line in lines:
        if HISTORY_RECORD_RE.match(line):
            if current is not None:
                records.append("".join(current))
            current = [line]
        else:
            if current is None:
                saw_plain_prefix = True
                current = [line]
            else:
                current.append(line)

    if current is not None:
        records.append("".join(current))

    parsed: list[HistoryRecord] = []
    for record in records:
        match = HISTORY_RECORD_RE.match(record)
        if match:
            timestamp = int(match.group(1))
            command = record[match.end() :]
            has_metadata = True
        else:
            timestamp = 0
            command = record
            has_metadata = False
        parsed.append(
            HistoryRecord(
                text=record,
                command=command,
                timestamp=timestamp,
                has_metadata=has_metadata,
            )
        )

    return ParsedHistory(
        records=parsed,
        format_name="mixed" if saw_plain_prefix else "extended",
    )


def backup_path_for(history_file: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return history_file.with_name(f"{history_file.name}.pre-merge-{stamp}")


def summarize_file(path: Path, parsed: ParsedHistory) -> tuple[str, str, int, int]:
    return (
        str(path),
        parsed.format_name,
        len(parsed.records),
        len({record.command for record in parsed.records}),
    )


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
    timestamps = [record.timestamp for record in records if record.timestamp > 0]
    return min(timestamps) if timestamps else int(datetime.now().timestamp())


def render_plain(records: list[HistoryRecord]) -> str:
    return "".join(command_with_newline(record.command) for record in records)


def render_extended(records: list[HistoryRecord]) -> str:
    synthetic_timestamps = assign_synthetic_timestamps(records)

    rendered: list[str] = []
    for record in records:
        if record.has_metadata:
            rendered.append(record.text)
            continue
        timestamp = synthetic_timestamps[id(record)]
        rendered.append(f": {timestamp}:0;{command_with_newline(record.command)}")
    return "".join(rendered)


def assign_synthetic_timestamps(records: list[HistoryRecord]) -> dict[int, int]:
    plain_records = [record for record in records if not record.has_metadata]
    first_timestamp = oldest_timestamp(records)
    synthetic_start = max(1, first_timestamp - len(plain_records))
    return {
        id(record): synthetic_start + index for index, record in enumerate(plain_records)
    }


def effective_timestamp(
    record: HistoryRecord, synthetic_timestamps: dict[int, int]
) -> int:
    if record.has_metadata:
        return record.timestamp
    return synthetic_timestamps[id(record)]


def resolve_output_format(
    requested_format: str,
    current_format: str | None,
    input_formats: set[str],
) -> str:
    if requested_format not in {"auto", "plain", "extended"}:
        raise typer.BadParameter("--format must be one of: auto, plain, extended")
    if requested_format != "auto":
        return requested_format
    if current_format == "plain":
        return "plain"
    if current_format in {"extended", "mixed"}:
        return "extended"
    if "extended" in input_formats or "mixed" in input_formats:
        return "extended"
    return "plain"


def render_history(records: list[HistoryRecord], output_format: str) -> str:
    if output_format == "plain":
        return render_plain(records)
    return render_extended(records)


def render_summary(
    sources: list[tuple[str, str, int, int]],
    total_records: int,
    current_unique_commands: int,
    final_unique_commands: int,
    new_commands: int,
    refreshed_commands: int,
    output_format: str,
    backup_message: str,
    target: Path,
    dry_run: bool,
    conversion_warnings: list[str],
) -> None:
    table = Table(title="zsh history merge")
    table.add_column("File", overflow="fold")
    table.add_column("Format")
    table.add_column("Records", justify="right")
    table.add_column("Unique commands", justify="right")

    for file_name, format_name, records, unique_commands in sources:
        table.add_row(file_name, format_name, str(records), str(unique_commands))

    result_table = Table.grid(expand=False)
    result_table.add_column("Metric", style="bold", no_wrap=True)
    result_table.add_column("Value", justify="right")
    result_table.add_row("Target", str(target))
    result_table.add_row("Input records", str(total_records))
    result_table.add_row("Current unique commands", str(current_unique_commands))
    result_table.add_row("New commands from backups", str(new_commands))
    result_table.add_row("Existing commands refreshed", str(refreshed_commands))
    result_table.add_row("Final unique commands", str(final_unique_commands))
    result_table.add_row("Deduped records", str(total_records - final_unique_commands))
    result_table.add_row("Output format", output_format)
    result_table.add_row("Backup", backup_message)

    console.print(table)
    console.print(Panel.fit(result_table, title="Result"))

    formats = {format_name for _, format_name, _, _ in sources}
    if len(formats) > 1:
        console.print(
            "[yellow]Warning:[/yellow] input files use mixed history formats. "
            "Output will be normalized to the selected format."
        )
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
        typer.Option(
            "--history-file",
            "-H",
            help="History file to update.",
        ),
    ] = Path.home() / ".zsh_history",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write merged history here instead of replacing the history file.",
        ),
    ] = None,
    no_current: Annotated[
        bool,
        typer.Option(
            "--no-current",
            help="Merge only the backup files, excluding the current history file.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be merged without writing anything.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: auto, plain, or extended.",
        ),
    ] = "auto",
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation prompts for format conversions.",
        ),
    ] = False,
) -> None:
    """Back up the active zsh history file and merge backups into it."""
    target = history_file.expanduser().resolve()
    destination = output.expanduser().resolve() if output else target

    backup_files = [path.expanduser().resolve() for path in backups]
    input_files = list(backup_files)
    current_records: list[HistoryRecord] = []
    parsed_by_path: dict[Path, ParsedHistory] = {}
    if not no_current:
        if not target.exists():
            raise typer.BadParameter(f"history file does not exist: {target}")
        input_files.append(target)
        parsed_by_path[target] = parse_history(target)
        current_records = parsed_by_path[target].records

    all_records: list[HistoryRecord] = []
    sources: list[tuple[str, str, int, int]] = []
    for path in input_files:
        parsed = parsed_by_path.get(path)
        if parsed is None:
            parsed = parse_history(path)
            parsed_by_path[path] = parsed
        all_records.extend(parsed.records)
        sources.append(summarize_file(path, parsed))

    input_formats = {parsed.format_name for parsed in parsed_by_path.values()}
    current_format = parsed_by_path[target].format_name if target in parsed_by_path else None
    resolved_output_format = resolve_output_format(
        output_format,
        current_format=current_format,
        input_formats=input_formats,
    )

    backup_records: list[HistoryRecord] = []
    for path in backup_files:
        backup_records.extend(parsed_by_path[path].records)

    current_by_command = newest_by_command(current_records)
    backup_by_command = newest_by_command(backup_records)

    new_commands = sum(
        1 for command in backup_by_command if command not in current_by_command
    )
    refreshed_commands = sum(
        1
        for command, record in backup_by_command.items()
        if command in current_by_command
        and record.timestamp > current_by_command[command].timestamp
    )

    chosen = newest_by_command(all_records)

    merged_records = list(chosen.values())
    if resolved_output_format == "extended":
        synthetic_timestamps = assign_synthetic_timestamps(merged_records)
        merged = sorted(
            merged_records,
            key=lambda record: (
                effective_timestamp(record, synthetic_timestamps),
                record.command,
            ),
        )
    else:
        merged = sorted(merged_records, key=lambda record: (record.timestamp, record.command))
    merged_text = render_history(merged, resolved_output_format)

    conversion_warnings: list[str] = []
    if resolved_output_format == "plain" and any(
        record.has_metadata for record in merged_records
    ):
        conversion_warnings.append(
            "Extended timestamp/duration metadata will be stripped from output."
        )
    if resolved_output_format == "extended" and any(
        not record.has_metadata for record in merged_records
    ):
        synthetic_timestamps = assign_synthetic_timestamps(merged_records)
        first_synthetic = min(synthetic_timestamps.values())
        last_synthetic = max(synthetic_timestamps.values())
        conversion_warnings.append(
            "Plain entries will receive synthetic incremental timestamps "
            f"from {first_synthetic} to {last_synthetic}."
        )

    should_backup_target = output is None and target.exists()
    backup_path = None if dry_run or not should_backup_target else backup_path_for(target)
    if dry_run:
        backup_message = "skipped for dry run"
    elif backup_path is not None:
        backup_message = str(backup_path)
    elif output is not None:
        backup_message = "not needed; wrote to --output"
    else:
        backup_message = "not needed; target does not exist"

    render_summary(
        sources=sources,
        total_records=len(all_records),
        current_unique_commands=len(current_by_command),
        final_unique_commands=len(merged),
        new_commands=new_commands,
        refreshed_commands=refreshed_commands,
        output_format=resolved_output_format,
        backup_message=backup_message,
        target=destination,
        dry_run=dry_run,
        conversion_warnings=conversion_warnings,
    )

    if dry_run:
        console.print("[yellow]Dry run only. No files were changed.[/yellow]")
        return

    confirm_conversion_if_needed(conversion_warnings, yes=yes)

    if should_backup_target:
        if backup_path is None:
            backup_path = backup_path_for(target)
        shutil.copy2(target, backup_path)
    destination.write_text(merged_text)
    if should_backup_target:
        shutil.copymode(backup_path, destination)

    console.print("[green]Merge complete.[/green]")


if __name__ == "__main__":
    app()
