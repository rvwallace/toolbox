#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "textual>=0.50.0",
# ]
# ///
# toolbox-platforms: darwin

"""
A Textual-based TUI for joining Microsoft Teams calls via deeplinks.

This script displays a list of preconfigured Teams meeting deeplinks and
allows you to quickly launch them via macOS's `open` command. The deeplinks
are stored in a TOML configuration file at:

    ~/.config/silentcastle/teams-calls.toml

If the configuration file doesn't exist, it will be created with default
values extracted from existing Raycast scripts.

Usage:
    uv run packages/productivity/join-call.py
    # or standalone:
    uv run --script packages/productivity/join-call.py

TUI Keys:
    Enter - Launch the selected Teams call
    q     - Quit

Author: Robert Wallace <rwallace@silentcastle.net>
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header


###############################################################################
# Data structures
###############################################################################


@dataclass(frozen=True)
class Call:
    """Representation of a Teams call entry."""

    name: str
    description: str
    deeplink: str


###############################################################################
# Configuration paths
###############################################################################


def config_dir() -> Path:
    """Get XDG-compliant config directory for silentcastle."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "silentcastle"


CONFIG_DIR = config_dir()
CONFIG_FILE = CONFIG_DIR / "teams-calls.toml"


###############################################################################
# Default calls (extracted from Raycast scripts)
###############################################################################


DEFAULT_CALLS: list[Call] = [
    Call(
        "Buffalo Room",
        "Open Buffalo Room Call",
        "msteams:/l/meetup-join/19:meeting_MDY4Yzc3MGYtNDI5Ni00Y2QyLWE1MzktOTgyMWNjOGUyODgx@thread.v2/0?context=%7b%22Tid%22%3a%22df5ef74e-dd5b-4d24-84a1-1ed75b831108%22%2c%22Oid%22%3a%22a2fd7a46-a83d-47ce-8805-4a2285840be2%22%7d&anon=true&deeplinkId=8fc0ba47-191c-4519-8d40-df5d24fa6706&launchAgent=join_launcher&type=meetup-join&directDl=true&msLaunch=true&enableMobilePage=true&fqdn=teams.microsoft.com",
    ),
    Call(
        "Flex",
        "Open Flex Call",
        "msteams:/l/meetup-join/19:meeting_NjY4NWFjZGQtNDJhYS00ZjJhLWI2NWEtMzE0NzdhYzJhNjA1@thread.v2/0?context=%7b%22Tid%22%3a%22df5ef74e-dd5b-4d24-84a1-1ed75b831108%22%2c%22Oid%22%3a%22b8b25c9e-a6a0-4a07-a4b2-5dd4fbbad3e9%22%7d&anon=true&deeplinkId=9ad7a4a4-1da8-4144-b043-543b5066b650&launchAgent=join_launcher&type=meetup-join&directDl=true&msLaunch=true&enableMobilePage=true&suppressPrompt=true&fqdn=teams.microsoft.com",
    ),
    Call(
        "Skynet",
        "Open Skynet Call",
        "msteams:/l/meetup-join/19:meeting_YjVmYWY2OTQtNWIzZC00NWQzLWE2NGEtMzRhODE5ODA1Mjcw@thread.v2/0?context=%7b%22Tid%22%3a%22df5ef74e-dd5b-4d24-84a1-1ed75b831108%22%2c%22Oid%22%3a%2202868c43-0e18-4049-bbf6-b2c17a75c9e4%22%7d&anon=true&deeplinkId=ffe583aa-549c-4ec1-a052-147539ad7c54&launchAgent=join_launcher&type=meetup-join&directDl=true&msLaunch=true&enableMobilePage=true&fqdn=teams.microsoft.com",
    ),
    Call(
        "Texas Monkeys",
        "Open Texas Monkeys Call",
        "msteams:/meet/2811838317073?p=BieoFTpdNENc7hZnQ5&anon=true&deeplinkId=ed89c9c3-7141-4e3c-8c38-0b8b738ab8c1&launchAgent=join_launcher&type=meet&directDl=true&msLaunch=true&enableMobilePage=true&suppressPrompt=true&fqdn=teams.microsoft.com",
    ),
    Call(
        "Chaos Monkeys",
        "Open Chaos Monkeys Call",
        "msteams:/l/meetup-join/19:meeting_ODIwZDVhZTctNzg1Ni00MjJjLTkxYmItNGM0ZmE3NjhjZDEw@thread.v2/0?context=%7b%22Tid%22%3a%22df5ef74e-dd5b-4d24-84a1-1ed75b831108%22%2c%22Oid%22%3a%22dacea279-2179-45fa-b860-bbcfb61ad2c5%22%7d&anon=true",
    ),
]


###############################################################################
# Configuration management
###############################################################################


def write_default_config(calls: Sequence[Call]) -> None:
    """Create default configuration file with provided calls."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for c in calls:
        lines.append("[[call]]")
        lines.append(f'name = "{c.name}"')
        lines.append(f'description = "{c.description}"')
        lines.append(f'deeplink = "{c.deeplink}"')
        lines.append("")  # blank line between entries
    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")


def ensure_config() -> None:
    """Ensure configuration file exists, creating it with defaults if needed."""
    if not CONFIG_FILE.exists():
        write_default_config(DEFAULT_CALLS)


def load_calls_from_config() -> list[Call]:
    """Load calls from TOML configuration file with validation.

    Returns:
        List of Call objects. Falls back to DEFAULT_CALLS on error.
    """
    try:
        data = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to parse {CONFIG_FILE}: {e}", file=sys.stderr)
        return DEFAULT_CALLS.copy()

    items = data.get("call", [])
    calls: list[Call] = []
    for i, item in enumerate(items):
        try:
            name = str(item["name"]).strip()
            desc = str(item.get("description", "")).strip()
            link = str(item["deeplink"]).strip()
            if not name or not link or not link.startswith("msteams:"):
                raise ValueError("Invalid call entry")
            calls.append(Call(name, desc, link))
        except Exception as e:
            print(f"Ignoring invalid [[call]] at index {i}: {e}", file=sys.stderr)

    return calls if calls else DEFAULT_CALLS.copy()


###############################################################################
# Helper functions
###############################################################################


def abbreviate(link: str, width: int = 56) -> str:
    """Truncate a deeplink for display in the table."""
    return link if len(link) <= width else link[: width - 1] + "…"


def launch_call(call: Call) -> None:
    """Launch a Teams call using macOS open command."""
    try:
        subprocess.run(["open", call.deeplink], check=False)
    except Exception as e:
        print(f"Failed to launch {call.name}: {e}", file=sys.stderr)


###############################################################################
# Textual TUI
###############################################################################


class JoinCallApp(App):
    """Textual app for selecting and launching Teams calls."""

    CSS = """
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("enter", "launch", "Launch", show=True),
    ]

    def __init__(self, calls: Sequence[Call]) -> None:
        super().__init__()
        self.calls = calls
        self.table: DataTable | None = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        self.table = DataTable(zebra_stripes=True)
        yield self.table
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the table with call data."""
        assert self.table is not None
        self.table.add_columns("Name", "Description", "Deeplink")
        for c in self.calls:
            self.table.add_row(c.name, c.description, abbreviate(c.deeplink))
        self.table.cursor_type = "row"
        self.table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key on a row)."""
        row_idx = event.cursor_row
        if row_idx < len(self.calls):
            call = self.calls[row_idx]
            launch_call(call)
            self.exit()

    def action_launch(self) -> None:
        """Launch the selected Teams call via keybinding."""
        assert self.table is not None
        row_idx = self.table.cursor_row
        if row_idx is not None and row_idx < len(self.calls):
            call = self.calls[row_idx]
            launch_call(call)
            self.exit()


###############################################################################
# Main entry point
###############################################################################


def main() -> None:
    """Main entry point for the script."""
    ensure_config()
    calls = load_calls_from_config()
    if not calls:
        print("No calls configured. Check your configuration file.", file=sys.stderr)
        sys.exit(1)
    JoinCallApp(calls).run()


if __name__ == "__main__":
    main()
