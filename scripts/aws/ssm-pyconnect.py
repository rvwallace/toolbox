#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3",
#     "textual",
# ]
# bin-name = "ssm-pyconnect"
# ///

"""
A Textual-based terminal user interface for connecting to running EC2 instances
via AWS Systems Manager (SSM).

This script is a Python re-implementation of a Bash utility originally called
``ssm-connect.sh``. It lists the running EC2 instances for a given AWS profile
and region, allows you to interactively filter and select an instance, and
finally launches an interactive SSM session against the selected instance.  To
reduce the number of AWS API calls, the script caches the list of running
instances on disk for a configurable amount of time.  It uses the boto3
library to talk to AWS APIs and Textual to build a rich terminal user
interface.

Run the script with ``uv --script ssm_connect.py``.  Example usage:

```
uv --script ssm_connect.py --profile prod --region us-east-2 --query web
```

Required software:

* Python with the ``boto3`` library installed for AWS API access.
* The ``textual`` library for building the TUI.
* The AWS CLI and its SSM plugin installed if you want to use the same
  interactive session mechanism as the original Bash script.  The AWS CLI
  command ``aws ssm start-session`` is an interactive command that opens
  a WebSocket connection to your instance and therefore requires the
  Session Manager plugin【222673483581875†L51-L59】.  You must have this
  plugin installed locally.【222673483581875†L51-L60】

Notes on behaviour:

* The script filters EC2 instances to the ``running`` state.  The AWS
  documentation describes an ``instance-state-name`` filter that can be
  used to restrict DescribeInstances results to a specific state
  (``pending``, ``running``, ``shutting-down``, ``terminated``, ``stopping``
  or ``stopped``)【762628106905620†L830-L833】.
* When you press Enter while a row is highlighted in the table, the TUI
  exits and the script immediately spawns the ``aws ssm start-session
  --target <instance-id>`` command.  This call is interactive and
  connects your terminal to the remote instance via SSM【222673483581875†L81-L90】.

Author: Robert Wallace
Original Bash version: 2.0

"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
import re
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from rich import box
import json
import configparser
from typing import List, Optional, Tuple, Dict, Iterable, Set
import shutil
import logging
from logging.handlers import RotatingFileHandler
import subprocess


# Attempt to import boto3.  If it is missing we defer the import to the
# functions that need it, so that the rest of the script (including the help
# message) can still be displayed.
try:
    import boto3  # type: ignore
    from botocore.exceptions import BotoCoreError, ClientError  # type: ignore
except ImportError:
    boto3 = None  # type: ignore
    BotoCoreError = Exception  # type: ignore
    ClientError = Exception  # type: ignore


# Attempt to import Textual.  We perform the import lazily so that a useful
# error message can be displayed if Textual is not installed.
try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, DataTable, Input, Static
    try:
        from textual.widgets import LoadingIndicator  # type: ignore
    except Exception:  # pragma: no cover - compatibility
        LoadingIndicator = None  # type: ignore
    from textual.containers import Horizontal, Vertical
    try:
        from textual.screen import ModalScreen  # type: ignore
    except Exception:  # pragma: no cover - compatibility
        ModalScreen = None  # type: ignore
    from textual.reactive import reactive
except ImportError:
    App = None  # type: ignore


###############################################################################
# Data structures
###############################################################################

@dataclass
class InstanceInfo:
    """Representation of an EC2 instance entry."""

    name: str
    instance_id: str
    private_ip: str
    public_ip: str
    status: str
    ami: str
    instance_type: str
    platform: str
    key_name: str
    public_dns_name: str
    # Background-fetched SSM metadata
    ssm_available: Optional[bool] = None
    ssm_info: Optional[str] = None


###############################################################################
# Helper functions
###############################################################################

def check_dependencies() -> None:
    """Verify that required Python modules and external commands are available.

    Raises:
        RuntimeError: If a required dependency is missing.
    """
    # Check boto3
    if boto3 is None:
        raise RuntimeError(
            "The 'boto3' library is required but not installed. "
            "Install it with `pip install boto3`.")

    # Check Textual
    if App is None:
        raise RuntimeError(
            "The 'textual' library is required for the TUI. "
            "Install it with `pip install textual`.")

    # Check AWS CLI for SSM connections
    if shutil.which("aws") is None:
        raise RuntimeError(
            "The AWS CLI must be installed to initiate SSM sessions. "
            "See the AWS CLI documentation for installation instructions."
        )


def ensure_directories(cache_dir: Path, config_dir: Path) -> None:
    """Create cache and configuration directories if they do not already exist."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)


def load_config(config_file: Path) -> dict:
    """Load simple key=value pairs from a configuration file.

    Args:
        config_file: Path to the configuration file.

    Returns:
        A dictionary of configuration keys and values.
    """
    config: dict = {}
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()
    return config


AVAILABLE_THEMES: List[str] = [
    "textual-dark",
    "textual-light",
    "nord",
    "gruvbox",
    "catppuccin-mocha",
    "dracula",
    "tokyo-night",
    "monokai",
    "flexoki",
    "catppuccin-latte",
    "solarized-light",
]


def save_config(_config_file: Path, _config: dict) -> None:
    """Legacy writer kept for compatibility (no-op for JSON mode)."""
    try:
        # Preserve legacy behavior in case other tools rely on it, but prefer JSON.
        lines = ["# Deprecated: legacy ssm-connect.config; JSON is now used."]
        for key, value in _config.items():
            lines.append(f"{key}={value}")
        _config_file.write_text("\n".join(lines) + "\n")
    except Exception:
        pass


def default_json_config() -> dict:
    return {
        "THEME": {
            "value": "tokyo-night",
            "description": "Default Textual theme",
            "valid_values": AVAILABLE_THEMES,
        },
        "LOG_LEVEL": {
            "value": "INFO",
            "description": "Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
            "valid_values": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        },
        "LOG_FORMAT": {
            "value": "text",
            "description": "Logging format: 'text' or 'json'",
            "valid_values": ["text", "json"],
        },
        "CACHE_TTL": {
            "value": 86400,
            "description": "Seconds to cache EC2 instance list",
            "valid_range": {"min": 60, "max": 604800},
        },
        "TOKEN_CHECK_SECONDS": {
            "value": 60,
            "description": "Interval (seconds) to refresh AWS token status",
            "valid_range": {"min": 10, "max": 3600},
        },
        "TOKEN_PROFILE": {
            "value": "",
            "description": "Profile in ~/.aws/credentials for x_security_token_expires; blank to auto-detect",
            "valid_values": [],
        },
    }


def load_json_config(path: Path) -> dict:
    default = default_json_config()
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text())
        # Merge missing keys
        changed = False
        for k, v in default.items():
            if k not in data:
                data[k] = v
                changed = True
            else:
                for subk, subv in v.items():
                    if subk not in data[k]:
                        data[k][subk] = subv
                        changed = True
        if changed:
            save_json_config(path, data)
        return data
    except Exception as exc:
        logging.getLogger("ssm_connect").debug(f"Failed to read JSON config: {exc}")
        return default


def save_json_config(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        logging.getLogger("ssm_connect").debug(f"Failed to save JSON config: {exc}")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def validate_json_config(path: Path, cfg: dict) -> bool:
    """Validate JSON config values against valid ranges/lists; fix to defaults when invalid.

    Returns True if any values were corrected.
    """
    logger = logging.getLogger("ssm_connect")
    defaults = default_json_config()
    changed = False
    corrections: List[str] = []
    for key, meta in defaults.items():
        if key not in cfg:
            cfg[key] = meta
            corrections.append(f"added '{key}' with default")
            changed = True
            continue
        cur = cfg[key]
        if "value" not in cur:
            cfg[key]["value"] = meta["value"]
            corrections.append(f"'{key}' missing value → default {meta['value']}")
            changed = True
            continue
        val = cur["value"]
        # Validate numeric ranges
        if "valid_range" in meta:
            vr = meta["valid_range"]
            try:
                ival = int(val)
            except Exception:
                cfg[key]["value"] = meta["value"]
                corrections.append(f"'{key}' invalid type → default {meta['value']}")
                changed = True
                continue
            if ("min" in vr and ival < vr["min"]) or ("max" in vr and ival > vr["max"]):
                cfg[key]["value"] = meta["value"]
                corrections.append(
                    f"'{key}' out of range ({ival}) → default {meta['value']}"
                )
                changed = True
        # Validate enumerated values (supports scalar or list values)
        if "valid_values" in meta and meta["valid_values"] is not None:
            valid = [str(v) for v in meta["valid_values"]]
            # If default is a list or current value is a list, treat as array
            if isinstance(meta.get("value"), list) or isinstance(val, list):
                # Coerce to list if a comma-separated string was provided
                if not isinstance(val, list):
                    if isinstance(val, str):
                        val_list = [s.strip() for s in val.split(",") if s.strip()]
                    else:
                        val_list = []
                else:
                    val_list = [str(x) for x in val]
                filtered = [x for x in val_list if str(x) in valid]
                if filtered != val_list:
                    if filtered:
                        cfg[key]["value"] = filtered
                        removed = set(val_list) - set(filtered)
                        corrections.append(
                            f"'{key}' removed invalid {sorted(removed)}; kept {filtered}"
                        )
                    else:
                        cfg[key]["value"] = meta["value"]
                        corrections.append(
                            f"'{key}' had no valid entries → default {meta['value']}"
                        )
                    changed = True
            else:
                if str(val) not in valid:
                    cfg[key]["value"] = meta["value"]
                    corrections.append(
                        f"'{key}' invalid option '{val}' → default {meta['value']}"
                    )
                    changed = True
    if changed:
        try:
            save_json_config(path, cfg)
        except Exception:
            pass
        logger.info("Config corrections: " + "; ".join(corrections))
    return changed


def is_cache_expired(cache_file: Path, ttl: int) -> bool:
    """Determine whether a cache file is missing or older than ttl seconds."""
    if not cache_file.exists():
        return True
    cache_age = time.time() - cache_file.stat().st_mtime
    return cache_age > ttl


def refresh_instance_cache(
    session: "boto3.session.Session", cache_file: Path, debug: bool = False
) -> List[InstanceInfo]:
    """Query AWS for running EC2 instances and store them in a cache file.

    Args:
        session: A boto3 session configured with profile and region.
        cache_file: Path to the file where results should be cached.
        debug: If True, emit diagnostic messages to stderr.

    Returns:
        A list of InstanceInfo objects representing running instances.

    The function writes a tab‑separated list of fields with a header to the
    provided cache file.  It filters instances to the ``running`` state using
    the ``instance-state-name`` filter described in the EC2 API documentation
    【762628106905620†L830-L833】.
    """
    if debug:
        logging.getLogger("ssm_connect").debug("Refreshing EC2 instance cache…")

    ec2 = session.client("ec2")
    instances: List[InstanceInfo] = []

    try:
        paginator = ec2.get_paginator("describe_instances")
        # Fetch all instance states; filtering to running is handled in the UI
        page_iter = paginator.paginate()
        for page in page_iter:
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    tags = inst.get("Tags", [])
                    name = next((t["Value"] for t in tags if t["Key"] == "Name"), "")
                    instance_id = inst.get("InstanceId", "")
                    private_ip = inst.get("PrivateIpAddress", "") or ""
                    public_ip = inst.get("PublicIpAddress", "") or ""
                    status = inst.get("State", {}).get("Name", "")
                    ami = inst.get("ImageId", "")
                    instance_type = inst.get("InstanceType", "")
                    platform = inst.get("PlatformDetails", "") or inst.get(
                        "Platform", ""
                    )
                    key_name = inst.get("KeyName", "") or ""
                    public_dns = inst.get("PublicDnsName", "") or ""
                    info = InstanceInfo(
                        name=name,
                        instance_id=instance_id,
                        private_ip=private_ip,
                        public_ip=public_ip,
                        status=status,
                        ami=ami,
                        instance_type=instance_type,
                        platform=platform,
                        key_name=key_name,
                        public_dns_name=public_dns,
                    )
                    instances.append(info)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"Failed to describe instances: {exc}")

    # Write the cache file with a header row
    with cache_file.open("w", encoding="utf-8") as f:
        header = [
            "Name",
            "Instance ID",
            "Private IP",
            "Public IP",
            "Status",
            "AMI",
            "Type",
            "Platform",
            "KeyName",
            "Public DNS Name",
        ]
        f.write("\t".join(header) + "\n")
        for inst in instances:
            row = [
                inst.name,
                inst.instance_id,
                inst.private_ip,
                inst.public_ip,
                inst.status,
                inst.ami,
                inst.instance_type,
                inst.platform,
                inst.key_name,
                inst.public_dns_name,
            ]
            f.write("\t".join(row) + "\n")

    return instances


def load_cache(cache_file: Path) -> List[InstanceInfo]:
    """Load a list of InstanceInfo objects from the cache file."""
    instances: List[InstanceInfo] = []
    if not cache_file.exists():
        return instances
    lines = cache_file.read_text().splitlines()
    if not lines:
        return instances
    # Skip header
    for line in lines[1:]:
        parts = line.split("\t")
        # Ensure we have at least 10 fields
        while len(parts) < 10:
            parts.append("")
        name, instance_id, private_ip, public_ip, status, ami, instance_type, platform, key_name, public_dns = parts[:10]
        instances.append(
            InstanceInfo(
                name=name,
                instance_id=instance_id,
                private_ip=private_ip,
                public_ip=public_ip,
                status=status,
                ami=ami,
                instance_type=instance_type,
                platform=platform,
                key_name=key_name,
                public_dns_name=public_dns,
            )
        )
    return instances


def _fetch_ssm_info_bulk(profile: str, region: str, instance_ids: Iterable[str]) -> Dict[str, dict]:
    """Fetch SSM managed instance information for many instances using boto3.

    Returns a mapping of instance_id -> InstanceInformation dict.
    """
    ids = [i for i in instance_ids if i]
    info_map: Dict[str, dict] = {}
    if not ids:
        return info_map
    session = boto3.Session(profile_name=profile, region_name=region)
    ssm = session.client("ssm")
    # Batch in chunks to respect API limits (typically 50 values per filter)
    def chunks(lst: List[str], n: int) -> Iterable[List[str]]:
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    try:
        for chunk in chunks(ids, 50):
            paginator = ssm.get_paginator("describe_instance_information")
            for page in paginator.paginate(Filters=[{"Key": "InstanceIds", "Values": chunk}]):
                for info in page.get("InstanceInformationList", []):
                    iid = info.get("InstanceId")
                    if iid:
                        info_map[iid] = info
    except Exception:
        # If filtering by InstanceIds isn't supported in the account/region,
        # fall back to enumerating all and filtering client-side.
        try:
            paginator = ssm.get_paginator("describe_instance_information")
            for page in paginator.paginate():
                for info in page.get("InstanceInformationList", []):
                    iid = info.get("InstanceId")
                    if iid in ids:
                        info_map[iid] = info
        except Exception:
            # Return whatever we managed to get
            return info_map
    return info_map


def connect_to_instance(instance_id: str, profile: str, region: str) -> None:
    """Launch an interactive SSM session to the specified instance using the AWS CLI.

    This function uses the ``aws ssm start-session`` command.  According to the
    AWS CLI documentation, the ``start-session`` command initiates a session
    manager session and is interactive【222673483581875†L51-L60】.  The ``--target``
    option identifies the instance to connect to【222673483581875†L69-L92】.

    Args:
        instance_id: The ID of the instance to connect to.
        profile: AWS profile to use.
        region: AWS region to use.
    """
    aws_path = shutil.which("aws")
    if not aws_path:
        raise RuntimeError(
            "Cannot start session: the 'aws' CLI is not installed or not in PATH."
        )
    args = [aws_path, "ssm", "start-session", "--target", instance_id]
    if profile:
        args.extend(["--profile", profile])
    if region:
        args.extend(["--region", region])
    # Use subprocess.run so that the user's terminal is handed over to the AWS
    # Session Manager plugin.  This call will block until the session ends.
    subprocess.run(args, check=False)


###############################################################################
# Textual application
###############################################################################

class StatusBar(Static):
    """Simple reactive status bar that updates when `message` changes."""

    message = reactive("Loading credentials…")

    def watch_message(self, new_value) -> None:  # type: ignore[override]
        try:
            self.update(new_value)
        except Exception:
            try:
                self.update(str(new_value))
            except Exception:
                pass


class SSMConnectApp(App):  # type: ignore[misc]
    """A Textual application for browsing and connecting to EC2 instances."""
    TITLE = "SSM Connect"

    CSS = """
    Screen {
        layout: vertical;
    }
    #left-panel {
        width: 50%;
    }
    #right-panel {
        width: 50%;
        border: tall;
        padding: 1 2;
    }
    #search {
        dock: top;
        height: 3;
        border: round;
        padding: 0 1;
    }
    #table {
        overflow: auto;
    }
    #details {
        overflow: auto;
    }
    #right-panel.hidden {
        display: none;
    }
    #left-panel.full {
        width: 100%;
    }
    Header, Footer {
        text-style: bold;
    }
    #refresh-modal {
        border: round;
        padding: 1 2;
        width: 60%;
        height: auto;
        content-align: center middle;
        text-align: center;
    }
    .dim {
        opacity: 0.4;
    }
    #status-bar {
        height: 1;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "connect", "Connect"),
        ("r", "refresh", "Refresh instances"),
        ("shift+r", "refresh_selected", "Refresh instance"),
        ("R", "refresh_selected", "Refresh instance"),
        ("a", "toggle_running_filter", "All/Running"),
        ("d", "toggle_details", "Toggle details"),
        ("f", "toggle_ssm_filter", "Filter SSM only"),
    ]

    def __init__(
        self,
        instances: List[InstanceInfo],
        profile: str,
        region: str,
        initial_query: str,
        cache_file: Path,
        ttl: int,
        debug: bool = False,
        force_refresh: bool = False,
        theme_name: str = "tokyo-night",
        config_file: Optional[Path] = None,
        token_check_seconds: int = 60,
        token_profile: str = "",
    ) -> None:
        super().__init__()
        self.all_instances = instances
        self.profile = profile
        self.region = region
        self.initial_query = initial_query
        self.cache_file = cache_file
        self.ttl = ttl
        self._debug = debug
        self._force_refresh = force_refresh
        self.theme_name = theme_name
        self._config_file = config_file
        self._token_check_seconds = token_check_seconds
        self._token_profile = token_profile.strip()
        self._token_ambiguous_warned = False
        # Instances filtered by the search box
        self.filtered_instances: List[InstanceInfo] = list(instances)
        # Selected instance after user hits Enter
        self.selected_instance: Optional[InstanceInfo] = None
        # (SSM details are fetched in the background; no per-row fetch state)
        # Currently highlighted row index (into filtered_instances)
        self._current_row_index: Optional[int] = None
        # Track last row index used for details to avoid redundant updates
        self._last_details_row: Optional[int] = None
        # SSM info cache: instance_id -> info dict
        self._ssm_info: Dict[str, dict] = {}
        self._ssm_loaded: bool = False
        # Track per-instance SSM loading state for UI indicator
        self._ssm_loading_ids: Set[str] = set()
        # Whether to show only instances with SSM information
        self._filter_ssm_only: bool = False
        # Whether to show only running instances (default True)
        self._filter_running_only: bool = True

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        # Restore default header with clock and palette/menu button
        yield Header(show_clock=True, id="header")
        with Horizontal():
            with Vertical(id="left-panel"):
                yield Input(placeholder="Filter instances…", id="search")
                yield DataTable(id="table")
            with Vertical(id="right-panel"):
                yield Static("Select an instance to see details.", id="details")
        # Status bar just above the footer
        yield StatusBar(id="status-bar")
        yield Footer()

    # Simple modal used during refresh operations
    if 'ModalScreen' in globals() and ModalScreen is not None:  # type: ignore
        class RefreshModal(ModalScreen[None]):  # type: ignore[misc]
            def compose(self) -> ComposeResult:  # type: ignore[override]
                with Vertical(id="refresh-modal"):
                    if LoadingIndicator is not None:
                        yield LoadingIndicator()
                    yield Static("Refreshing EC2 instance list…")

            def set_message(self, text: str) -> None:
                try:
                    static = self.query(Static).last()
                    static.update(text)
                except Exception:
                    pass

    def _toast(self, message: str, severity: str = "info", timeout: float = 2.5) -> None:
        """Show a transient notification without disturbing the details pane.

        Uses Textual's notify if available; otherwise falls back to a bell and
        debug log.
        """
        try:
            notify = getattr(self, "notify", None)
            if callable(notify):
                sev = (severity or "info").lower()
                if sev in ("info", "success", "ok", "okay"):
                    sev = "information"
                # type: ignore[call-arg]
                notify(message, severity=sev, timeout=timeout)  # pragma: no cover - runtime UI
                return
        except Exception:
            pass
        # Fallback: audible bell and stderr message in debug mode
        try:
            self.bell()
        except Exception:
            pass
        logging.getLogger("ssm_connect").debug(f"TOAST[{severity}]: {message}")

    def _apply_theme(self, name: str) -> bool:
        """Try to apply a Textual theme by name. Returns True if applied."""
        try:
            setter = getattr(self, "set_theme", None)
            if callable(setter):
                self.set_theme(name)  # type: ignore[arg-type]
                return True
            if hasattr(self, "theme"):
                setattr(self, "theme", name)
                return True
        except Exception:
            return False
        return False

    # Persist theme changes initiated by Textual's built-in theme switcher
    def set_theme(self, theme: str):  # type: ignore[override]
        try:
            result = super().set_theme(theme)  # type: ignore[misc]
        except Exception:
            # Fallback for versions without super().set_theme
            try:
                setattr(self, "theme", theme)
                result = None
            except Exception:
                raise
        # Update internal state and persist to config
        self.theme_name = theme
        try:
            if self._config_file is not None:
                cfg = load_json_config(self._config_file)
                if cfg.get("THEME", {}).get("value") != theme:
                    cfg["THEME"]["value"] = theme
                    save_json_config(self._config_file, cfg)
                    logging.getLogger("ssm_connect").info(f"Theme changed to '{theme}'")
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Failed to persist THEME '{theme}': {exc}")
        return result

    async def on_mount(self) -> None:
        """Prepare widgets after the app has mounted."""
        # Apply the "tokyo-night" theme with simple fallbacks (no loop)
        try:
            applied = self._apply_theme(self.theme_name or "tokyo-night")
            # Prefer dark mode visuals where applicable
            try:
                self.dark = True  # type: ignore[assignment]
            except Exception:
                pass
            if not applied:
                logging.getLogger("ssm_connect").debug("Could not apply 'tokyo-night' theme via API")
        except Exception:
            pass
        # Show AWS token status in header instead of clock
        try:
            # Initial update shortly after first render
            try:
                self.call_after_refresh(self._update_token_status)  # type: ignore[attr-defined]
            except Exception:
                self.set_timer(0.05, self._update_token_status)  # type: ignore[attr-defined]
            # Also run a resilient async loop that updates periodically
            asyncio.create_task(self._token_status_loop())
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Token status scheduler error: {exc}")
        # Populate table
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        columns = [
            "SSM",
            "Instance ID",
            "Name",
            "Private IP",
            "Public IP",
            "Status",
            "Platform",
            "Platform Name",
            "Key Pair",
        ]
        table.clear(columns=True)
        table.add_columns(*columns)
        # Prefer row-based selection for usability
        try:
            table.cursor_type = "row"  # type: ignore[attr-defined]
            # Enable zebra/striped rows for readability if supported
            try:
                table.zebra_stripes = True  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass
        # Insert rows with a key equal to the index; DataTable uses strings
        self._populate_table(self.all_instances)
        # Set initial query
        search_widget: Input = self.query_one("#search", expect_type=Input)
        if self.initial_query:
            search_widget.value = self.initial_query
            # Trigger a search on mount
            self._apply_filter(self.initial_query)
        # Focus the table so that arrow keys work immediately
        table.focus()
        # Set default highlighted row index and show details
        if self.filtered_instances:
            self._current_row_index = 0
            # Show details for the first row on startup
            await self._show_instance_details(self.filtered_instances[0])
        # If we don't yet have instances, start initial load in the background
        if not self.all_instances:
            asyncio.create_task(self._initial_load_instances())
        else:
            # Kick off background SSM info fetch for all instances
            asyncio.create_task(self._prefetch_ssm_info())
        # Default: hide details panel; expand left panel
        try:
            left_panel: Vertical = self.query_one("#left-panel", expect_type=Vertical)
            right_panel: Vertical = self.query_one("#right-panel", expect_type=Vertical)
            right_panel.add_class("hidden")
            left_panel.add_class("full")
            self._details_visible = False
        except Exception:
            self._details_visible = True

    def _parse_expiry(self, value) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        # Attempt ISO8601 parsing without external deps
        try:
            s = str(value)
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except Exception:
            return None

    def _append_counts_to(self, t: Text) -> Text:
        """Append counts to a Text: total (ignoring running filter), running, SSM ready.

        - Total applies current search text and SSM-only filter, but NOT the running-only toggle.
        - Running applies to the same base set.
        - SSM ready counts PingStatus=Online in the base set.
        """
        try:
            # Build base set: respect search text and SSM-only, ignore running-only
            try:
                search_text = self.query_one("#search", expect_type=Input).value.strip().lower()
            except Exception:
                search_text = ""
            base: List[InstanceInfo] = []
            if self._filter_ssm_only and not self._ssm_loaded:
                base = []
            else:
                for inst in self.all_instances:
                    haystack = "\t".join([
                        inst.name or "",
                        inst.instance_id or "",
                        inst.private_ip or "",
                        inst.public_ip or "",
                        inst.platform or "",
                        (self._ssm_info.get(inst.instance_id, {}).get("PlatformName") if self._ssm_info.get(inst.instance_id) else ""),
                        inst.key_name or "",
                    ]).lower()
                    if search_text and search_text not in haystack:
                        continue
                    if self._filter_ssm_only:
                        if inst.instance_id not in self._ssm_info:
                            continue
                    base.append(inst)

            total = len(base)
            running_count = 0
            online = 0
            for inst in base:
                if (inst.status or '').lower() == 'running':
                    running_count += 1
                info = self._ssm_info.get(inst.instance_id)
                if info:
                    status = (info.get("PingStatus") or info.get("Status") or "").lower()
                    if status == "online":
                        online += 1
            t.append(" | ")
            t.append(str(total), style="cyan")
            t.append(" inst, running: ")
            t.append(str(running_count), style=("green" if running_count > 0 else "red"))
            t.append(", SSM ready: ")
            t.append(str(online), style=("green" if online > 0 else "red"))
        except Exception:
            pass
        return t

    def _read_credentials_expiry(self) -> Tuple[Optional[datetime], Optional[str]]:
        """Read x_security_token_expires from ~/.aws/credentials.

        Returns (expiry_datetime, source_profile) or (None, reason) where reason
        may be 'none', 'ambiguous', or an error string for logging.
        """
        try:
            creds_path = Path.home() / ".aws" / "credentials"
            if not creds_path.exists():
                return (None, "none")
            parser = configparser.RawConfigParser()
            parser.read(creds_path)
            # If a specific profile is set, only check that one
            if self._token_profile:
                if parser.has_section(self._token_profile) and parser.has_option(
                    self._token_profile, "x_security_token_expires"
                ):
                    val = parser.get(self._token_profile, "x_security_token_expires")
                    return (self._parse_expiry(val), self._token_profile)
                return (None, "none")
            # Auto-discover: find all profiles with the key
            matches: List[Tuple[str, str]] = []
            for sect in parser.sections():
                if parser.has_option(sect, "x_security_token_expires"):
                    matches.append((sect, parser.get(sect, "x_security_token_expires")))
            if not matches:
                # Fallback: scan raw file lines for a single occurrence (no section)
                try:
                    text = creds_path.read_text()
                    vals = re.findall(r"^\s*x_security_token_expires\s*=\s*(\S+)\s*$", text, flags=re.MULTILINE)
                    vals = [v.strip() for v in vals if v.strip()]
                    if len(vals) == 1:
                        return (self._parse_expiry(vals[0]), "raw")
                except Exception:
                    pass
                return (None, "none")
            if len(matches) > 1:
                return (None, "ambiguous")
            sect, val = matches[0]
            return (self._parse_expiry(val), sect)
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Credentials parse error: {exc}")
            return (None, "error")

    def _compute_token_status(self) -> Text:
        try:
            # Prefer expiry from ~/.aws/credentials x_security_token_expires
            exp_dt, source = self._read_credentials_expiry()
            prefix = Text(f"{self.profile}/{self.region}: ")
            if source == "ambiguous":
                if not self._token_ambiguous_warned:
                    self._toast("Multiple profiles with x_security_token_expires; set TOKEN_PROFILE in config.")
                    logging.getLogger("ssm_connect").warning(
                        "Multiple profiles contained x_security_token_expires; not displaying token."
                    )
                    self._token_ambiguous_warned = True
                # Omit token details; just append counts
                return self._append_counts_to(prefix)
            if exp_dt is None and source == "none":
                # Fallback to boto3 session awareness only to identify session/long-lived
                try:
                    session = boto3.Session(profile_name=self.profile, region_name=self.region)
                    creds = session.get_credentials()
                    if creds is None:
                        prefix.append("no credentials", style="red")
                        return self._append_counts_to(prefix)
                    frozen = creds.get_frozen_credentials()
                    access_key = getattr(frozen, "access_key", "")
                    has_token = bool(getattr(frozen, "token", None)) or access_key.startswith("ASIA")
                    if not has_token:
                        prefix.append("long-lived credentials", style="cyan")
                        return self._append_counts_to(prefix)
                except Exception:
                    pass
                prefix.append("token (expiry unknown)", style="yellow")
                return self._append_counts_to(prefix)
            # Have an expiry
            now = datetime.now(timezone.utc)
            prefix = Text(f"{self.profile}/{self.region}: ")
            if exp_dt is None:
                prefix.append("token (expiry unknown)", style="yellow")
                return self._append_counts_to(prefix)
            remaining = (exp_dt - now).total_seconds()
            if remaining <= 0:
                prefix.append("token expired", style="red")
                return self._append_counts_to(prefix)
            # Format remaining concisely
            mins = int(remaining // 60)
            hours, mins = divmod(mins, 60)
            days, hours = divmod(hours, 24)
            if days > 0:
                rem = f"{days}d {hours}h"
            elif hours > 0:
                rem = f"{hours}h {mins}m"
            else:
                rem = f"{mins}m"
            color = "green" if remaining >= 3600 else ("yellow" if remaining >= 600 else "red")
            prefix.append("token ")
            prefix.append(rem, style=color)
            prefix.append(" left")
            return self._append_counts_to(prefix)
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Token status error: {exc}")
            return self._append_counts_to(Text(f"{self.profile}/{self.region}: token status n/a", style="yellow"))

    def _credentials_ok(self) -> Tuple[bool, str]:
        """Validate AWS credentials and token.

        Returns (ok, reason). If token expiry is present and expired, returns False.
        If STS GetCallerIdentity fails, returns False.
        """
        # Check token expiry from credentials file
        try:
            exp_dt, source = self._read_credentials_expiry()
            if exp_dt is not None:
                now = datetime.now(timezone.utc)
                if (exp_dt - now).total_seconds() <= 0:
                    return (False, "Token expired")
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Token expiry check failed: {exc}")
        # STS check
        try:
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            sts = session.client("sts")
            sts.get_caller_identity()
        except Exception as exc:
            return (False, f"Credentials invalid: {exc}")
        return (True, "ok")

    def _clear_instance_cache(self) -> None:
        try:
            if self.cache_file and self.cache_file.exists():
                self.cache_file.unlink()
                logging.getLogger("ssm_connect").warning("Cleared instance cache due to invalid credentials or expired token")
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Failed to clear cache: {exc}")

    def _update_token_status(self) -> None:
        try:
            status = self._compute_token_status()
            # Update dedicated status bar line via reactive property
            bar: StatusBar = self.query_one("#status-bar", expect_type=StatusBar)
            bar.message = status
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Status bar error: {exc}")

    async def _token_status_loop(self) -> None:
        """Background loop to refresh token status at configured interval."""
        interval = max(10, int(self._token_check_seconds))
        while True:
            try:
                self._update_token_status()
            except Exception as exc:
                logging.getLogger("ssm_connect").debug(f"Token loop error: {exc}")
            await asyncio.sleep(interval)

    def _populate_table(self, instances: List[InstanceInfo]) -> None:
        """Fill the table with a list of instances."""
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        # Clear existing rows; older/newer Textual versions don't support a 'rows' kwarg
        table.clear()
        for idx, inst in enumerate(instances):
            # First column shows SSM availability indicator
            indicator = self._ssm_indicator(inst.instance_id)
            info = self._ssm_info.get(inst.instance_id)
            if info:
                platform_val = info.get("PlatformType") or (inst.platform or "")
                platform_name = info.get("PlatformName") or ""
            else:
                platform_val = inst.platform or ""
                platform_name = ""
            # Colorize status
            status_style = "green" if (inst.status or "").lower() == "running" else "red"
            status_cell = Text(inst.status or "", style=status_style)
            table.add_row(
                indicator,
                inst.instance_id,
                inst.name or "",
                inst.private_ip or "",
                inst.public_ip or "",
                status_cell,
                platform_val,
                platform_name,
                inst.key_name or "",
                key=str(idx),
            )
        self.filtered_instances = list(instances)
        self._current_row_index = 0 if self.filtered_instances else None
        self._last_details_row = None

    def _ssm_indicator(self, instance_id: str) -> Text:
        info = self._ssm_info.get(instance_id)
        if instance_id in getattr(self, "_ssm_loading_ids", set()):
            return Text("…")
        if info is None:
            # If background fetch hasn't completed, show loading. Otherwise it's unavailable.
            return Text("…") if not self._ssm_loaded else Text("×", style="red")
        status = (info.get("PingStatus") or info.get("Status") or "").lower()
        return Text("✓", style="green") if status == "online" else Text("×", style="red")

    def _apply_filter(self, query: str) -> None:
        """Filter the instance list based on the search query and repopulate the table."""
        query = query.strip().lower()
        if not query:
            filtered = self.all_instances
        else:
            filtered = []
            for inst in self.all_instances:
                info = self._ssm_info.get(inst.instance_id)
                platform_val = (info.get("PlatformType") if info else None) or (inst.platform or "")
                platform_name = (info.get("PlatformName") if info else None) or ("SSM N/A" if info is None else "")
                haystack = "\t".join(
                    [
                        inst.name or "",
                        inst.instance_id or "",
                        inst.private_ip or "",
                        inst.public_ip or "",
                        platform_val or "",
                        platform_name or "",
                        inst.key_name or "",
                    ]
                ).lower()
                if query in haystack:
                    filtered.append(inst)
        # Apply SSM-only filter if enabled
        if self._filter_ssm_only:
            if self._ssm_loaded:
                filtered = [i for i in filtered if i.instance_id in self._ssm_info]
            else:
                filtered = []
        # Apply running-only filter if enabled
        if self._filter_running_only:
            filtered = [i for i in filtered if (i.status or '').lower() == 'running']
        extra = " + SSM only" if self._filter_ssm_only else ""
        extra2 = " + Running only" if self._filter_running_only else " + All states"
        logging.getLogger("ssm_connect").debug(
            f"Filter query '{query}'{extra}{extra2} matched {len(filtered)} instances"
        )
        self._populate_table(filtered)

    def _restore_selection_by_instance(self, instance_id: str) -> None:
        """Restore table selection/highlight to the row with given instance id."""
        try:
            idx = None
            for i, it in enumerate(self.filtered_instances):
                if it.instance_id == instance_id:
                    idx = i
                    break
            if idx is None:
                return
            self._current_row_index = idx
            table: DataTable = self.query_one("#table", expect_type=DataTable)
            # Try several APIs depending on Textual version
            try:
                table.cursor_coordinate = (idx, 0)  # type: ignore[attr-defined]
            except Exception:
                try:
                    table.move_cursor(row=idx, column=0)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        table.scroll_to_row(idx)  # type: ignore[attr-defined]
                    except Exception:
                        pass
        except Exception:
            pass

    async def action_toggle_ssm_filter(self) -> None:
        """Toggle showing only SSM-managed instances."""
        self._filter_ssm_only = not self._filter_ssm_only
        details_widget: Static = self.query_one("#details", expect_type=Static)
        if self._filter_ssm_only and not self._ssm_loaded:
            # Ensure SSM info is being fetched
            asyncio.create_task(self._prefetch_ssm_info())
            details_widget.update("Fetching SSM info to apply filter…")
        # Reapply filter using current search text
        self._apply_filter(self.query_one("#search", expect_type=Input).value)
        # Keep current selection if possible
        if self._current_row_index is not None and 0 <= self._current_row_index < len(self.filtered_instances):
            self._restore_selection_by_instance(self.filtered_instances[self._current_row_index].instance_id)
        # Optional: note the mode in the details panel
        mode = "enabled" if self._filter_ssm_only else "disabled"
        logging.getLogger("ssm_connect").debug(f"SSM-only filter {mode}")

    async def action_toggle_running_filter(self) -> None:
        """Toggle showing only running instances vs all states."""
        self._filter_running_only = not self._filter_running_only
        self._toast("Running only" if self._filter_running_only else "All states", severity="info")
        # Reapply filter using current search text and keep selection if possible
        prev_id = None
        if self._current_row_index is not None and 0 <= self._current_row_index < len(self.filtered_instances):
            prev_id = self.filtered_instances[self._current_row_index].instance_id
        self._apply_filter(self.query_one("#search", expect_type=Input).value)
        if prev_id:
            self._restore_selection_by_instance(prev_id)

    async def action_toggle_details(self) -> None:
        """Show/hide the details panel and resize the table pane."""
        try:
            left_panel: Vertical = self.query_one("#left-panel", expect_type=Vertical)
            right_panel: Vertical = self.query_one("#right-panel", expect_type=Vertical)
            self._details_visible = not getattr(self, "_details_visible", False)
            if self._details_visible:
                right_panel.remove_class("hidden")
                left_panel.remove_class("full")
                self._toast("Details shown", severity="info")
                if self._current_row_index is not None and 0 <= self._current_row_index < len(self.filtered_instances):
                    await self._show_instance_details(self.filtered_instances[self._current_row_index])
            else:
                right_panel.add_class("hidden")
                left_panel.add_class("full")
                self._toast("Details hidden", severity="info")
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Toggle details failed: {exc}")

    async def on_input_changed(self, event: Input.Changed) -> None:
        """React to changes in the search box."""
        self._apply_filter(event.value)

    def _resolve_row_index(self, table: DataTable, obj: object) -> Optional[int]:
        """Best-effort extraction of a row index from a DataTable event or key."""
        # Try direct get_row_index when a row_key is present
        row_key = getattr(obj, "row_key", None)
        if row_key is not None:
            try:
                return table.get_row_index(row_key)  # type: ignore[arg-type]
            except Exception:
                pass
        # Direct row attributes that some events expose
        for attr in ("row", "cursor_row", "row_index"):
            val = getattr(obj, attr, None)
            if isinstance(val, int):
                return val
        # Try coordinate attribute (CellSelected has this)
        coord = getattr(obj, "coordinate", None)
        if coord is not None:
            row = getattr(coord, "row", None)
            if isinstance(row, int):
                return row
            # Coordinate may be a tuple
            try:
                return int(coord[0])  # type: ignore[index]
            except Exception:
                pass
        # Fallback: interpret object itself as a key or int
        key_val = getattr(obj, "value", obj)
        try:
            return int(key_val)  # type: ignore[arg-type]
        except Exception:
            return None

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update details panel when the highlighted row changes."""
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        row_index = self._resolve_row_index(table, event)
        if row_index is None:
            return
        if 0 <= row_index < len(self.filtered_instances):
            if self._last_details_row == row_index:
                return
            inst = self.filtered_instances[row_index]
            self._current_row_index = row_index
            self._last_details_row = row_index
            await self._show_instance_details(inst)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Also update details when a row is selected via mouse/enter."""
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        row_index = self._resolve_row_index(table, event)
        if row_index is None:
            return
        if 0 <= row_index < len(self.filtered_instances):
            if self._last_details_row == row_index:
                return
            inst = self.filtered_instances[row_index]
            self._current_row_index = row_index
            self._last_details_row = row_index
            await self._show_instance_details(inst)

    async def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Update details on cell-level selection changes as well."""
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        row_index = self._resolve_row_index(table, event)
        if row_index is None:
            return
        if 0 <= row_index < len(self.filtered_instances):
            if self._last_details_row == row_index:
                return
            inst = self.filtered_instances[row_index]
            self._current_row_index = row_index
            self._last_details_row = row_index
            await self._show_instance_details(inst)

    async def on_data_table_cursor_moved(self, event: DataTable.CursorMoved) -> None:
        """Update details when the DataTable cursor moves (arrow keys)."""
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        row_index = self._resolve_row_index(table, event)
        if row_index is None:
            return
        if 0 <= row_index < len(self.filtered_instances):
            if self._last_details_row == row_index:
                return
            inst = self.filtered_instances[row_index]
            self._current_row_index = row_index
            self._last_details_row = row_index
            await self._show_instance_details(inst)

    async def _show_instance_details(self, inst: InstanceInfo) -> None:
        """Populate the details panel with instance and SSM information using Rich."""
        details_widget: Static = self.query_one("#details", expect_type=Static)

        # Instance details table
        t_inst = Table(box=box.SIMPLE, expand=True, show_edge=False, padding=(0,1))
        t_inst.add_column("Field", style="bold cyan", no_wrap=True)
        t_inst.add_column("Value", style="white")
        t_inst.add_row("Name", inst.name or "(none)")
        t_inst.add_row("Instance ID", inst.instance_id)
        t_inst.add_row("Private IP", inst.private_ip or "(none)")
        t_inst.add_row("Public IP", inst.public_ip or "(none)")
        status_style = "green" if (inst.status or "").lower() == "running" else "red"
        t_inst.add_row("Status", f"[{status_style}]{inst.status}[/{status_style}]")
        t_inst.add_row("AMI", inst.ami or "")
        t_inst.add_row("Type", inst.instance_type or "")
        t_inst.add_row("Platform", inst.platform or "(unknown)")
        t_inst.add_row("Key Pair", inst.key_name or "(none)")
        t_inst.add_row("Public DNS", inst.public_dns_name or "(none)")

        # SSM details table (if available)
        info = self._ssm_info.get(inst.instance_id)
        if info is None:
            if self._ssm_loaded:
                ssm_panel = Panel(Text("Not managed by SSM.", style="yellow"), title="SSM", box=box.ROUNDED)
            else:
                ssm_panel = Panel(Text("Fetching SSM information…", style="cyan"), title="SSM", box=box.ROUNDED)
        else:
            t_ssm = Table(box=box.SIMPLE, expand=True, show_edge=False, padding=(0,1))
            t_ssm.add_column("Key", style="bold cyan", no_wrap=True)
            t_ssm.add_column("Value", style="white")
            # Show a subset prominently first
            highlight_keys = [
                "InstanceId",
                "PingStatus",
                "ComputerName",
                "PlatformName",
                "PlatformVersion",
                "AgentVersion",
                "IsLatestVersion",
            ]
            for k in highlight_keys:
                if k in info:
                    val = info.get(k)
                    if k == "PingStatus":
                        v = str(val)
                        style = "green" if v.lower() == "online" else "red"
                        t_ssm.add_row(k, f"[{style}]{v}[/{style}]")
                    else:
                        t_ssm.add_row(k, str(val))
            # Then add remaining keys (sorted) skipping duplicates
            for k in sorted(info.keys()):
                if k in highlight_keys:
                    continue
                val = info.get(k)
                if k == "PingStatus":
                    v = str(val)
                    style = "green" if v.lower() == "online" else "red"
                    t_ssm.add_row(k, f"[{style}]{v}[/{style}]")
                else:
                    t_ssm.add_row(k, str(val))
            ssm_panel = Panel(t_ssm, title="SSM", box=box.ROUNDED)

        group = Group(Panel(t_inst, title="Instance", box=box.ROUNDED), ssm_panel)
        details_widget.update(group)

    async def action_refresh(self) -> None:
        """Refresh the instance list from AWS, overwriting the cache."""
        # Show a modal (if supported) and dim the table for feedback
        logging.getLogger("ssm_connect").info("Refreshing EC2 instance list…")
        details_widget: Static = self.query_one("#details", expect_type=Static)
        table: DataTable = self.query_one("#table", expect_type=DataTable)
        left_panel: Vertical = self.query_one("#left-panel", expect_type=Vertical)
        # Dim the table area instead of immediately clearing it
        try:
            left_panel.add_class("dim")
        except Exception:
            pass
        modal_shown = False
        modal_ref = None
        try:
            if 'ModalScreen' in globals() and ModalScreen is not None:  # type: ignore
                modal_ref = self.RefreshModal()  # type: ignore[attr-defined]
                self.push_screen(modal_ref)
                modal_shown = True
            else:
                details_widget.update("Refreshing EC2 instance list…")
        except Exception:
            details_widget.update("Refreshing EC2 instance list…")
        # Validate credentials/token before attempting to load
        ok, reason = self._credentials_ok()
        if not ok:
            details_widget.update(f"Cannot refresh: {reason}")
            try:
                table.clear()
            except Exception:
                pass
            self._clear_instance_cache()
            # Close modal and undim
            try:
                if modal_shown:
                    self.pop_screen()
            except Exception:
                pass
            try:
                left_panel.remove_class("dim")
            except Exception:
                pass
            self._toast("Credentials invalid or token expired. Cache cleared.")
            return
        # Use a separate thread for the blocking call
        try:
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            loop = asyncio.get_running_loop()
            instances: List[InstanceInfo] = await loop.run_in_executor(
                None, refresh_instance_cache, session, self.cache_file, self._debug
            )
            self.all_instances = instances
            count = len(instances)
            logging.getLogger("ssm_connect").info(f"Loaded {count} instances from AWS")
            # Update modal with counts before we rebuild UI
            try:
                if modal_ref is not None:
                    modal_ref.set_message(f"Loaded {count} instances. Updating SSM…")
            except Exception:
                pass
            # Rebuild the table now (clears and replaces rows)
            # Reset SSM cache BEFORE populating so indicators return to default
            self._ssm_info = {}
            self._ssm_loaded = False
            self._apply_filter(self.query_one("#search", expect_type=Input).value)
            details_widget.update(f"Loaded {count} instances. Updating SSM…")
            # Re-fetch SSM details in background for new list
            asyncio.create_task(self._prefetch_ssm_info())
        except Exception as exc:
            details_widget.update(f"Failed to refresh instances: {exc}")
            logging.getLogger("ssm_connect").warning(f"Refresh failed: {exc}")
        finally:
            # Close the modal if it was shown
            try:
                if modal_shown:
                    # Briefly show the loaded counts before closing modal
                    await asyncio.sleep(0.6)
                    self.pop_screen()
            except Exception:
                pass
            # Remove dimming
            try:
                left_panel.remove_class("dim")
            except Exception:
                pass

    async def action_refresh_selected(self) -> None:
        """Refresh SSM details for the currently selected instance."""
        row_index = self._current_row_index
        if row_index is None or not (0 <= row_index < len(self.filtered_instances)):
            self._toast("No instance selected", severity="warning")
            return
        inst = self.filtered_instances[row_index]
        logging.getLogger("ssm_connect").info(f"Refreshing selected instance {inst.instance_id}")
        self._toast(f"Refreshing {inst.instance_id}…", severity="info")
        # Clear detail values except Name and Instance ID
        try:
            grid = Table.grid(padding=(0,1))
            grid.add_column(style="bold cyan")
            grid.add_column(style="white")
            grid.add_row("Name", inst.name or "(none)")
            grid.add_row("Instance ID", inst.instance_id)
            grid.add_row("", "Refreshing…")
            placeholder = Panel(grid, title="Instance", box=box.ROUNDED)
        except Exception:
            placeholder = Text(f"Name: {inst.name or '(none)'}\nInstance ID: {inst.instance_id}\nRefreshing…")
        details_widget: Static = self.query_one("#details", expect_type=Static)
        details_widget.update(placeholder)
        # Reset SSM indicator for this instance to loading
        try:
            self._ssm_loading_ids.add(inst.instance_id)
            if inst.instance_id in self._ssm_info:
                del self._ssm_info[inst.instance_id]
            self._apply_filter(self.query_one("#search", expect_type=Input).value)
            self._restore_selection_by_instance(inst.instance_id)
        except Exception:
            pass
        try:
            loop = asyncio.get_running_loop()
            # Fetch EC2 and SSM info for this instance only
            def _refresh_one() -> Tuple[Optional[InstanceInfo], Dict[str, dict]]:
                session = boto3.Session(profile_name=self.profile, region_name=self.region)
                # EC2
                ec2 = session.client("ec2")
                try:
                    resp = ec2.describe_instances(InstanceIds=[inst.instance_id])
                    for res in resp.get("Reservations", []):
                        for it in res.get("Instances", []):
                            tags = it.get("Tags", [])
                            name = next((t["Value"] for t in tags if t["Key"] == "Name"), "")
                            private_ip = it.get("PrivateIpAddress", "") or ""
                            public_ip = it.get("PublicIpAddress", "") or ""
                            status = it.get("State", {}).get("Name", "")
                            ami = it.get("ImageId", "")
                            instance_type = it.get("InstanceType", "")
                            platform = it.get("PlatformDetails", "") or it.get("Platform", "")
                            key_name = it.get("KeyName", "") or ""
                            public_dns = it.get("PublicDnsName", "") or ""
                            new_info = InstanceInfo(
                                name=name,
                                instance_id=inst.instance_id,
                                private_ip=private_ip,
                                public_ip=public_ip,
                                status=status,
                                ami=ami,
                                instance_type=instance_type,
                                platform=platform,
                                key_name=key_name,
                                public_dns_name=public_dns,
                            )
                            break
                        else:
                            continue
                        break
                    else:
                        new_info = None
                except Exception:
                    new_info = None
                # SSM
                info_map = _fetch_ssm_info_bulk(self.profile, self.region, [inst.instance_id])
                return new_info, info_map

            new_inst, info_map = await loop.run_in_executor(None, _refresh_one)
            # Update EC2 instance details in lists
            if new_inst is not None:
                try:
                    # Update in all_instances
                    for idx2, it in enumerate(self.all_instances):
                        if it.instance_id == inst.instance_id:
                            self.all_instances[idx2] = new_inst
                            break
                    # Update in filtered_instances
                    for idx2, it in enumerate(self.filtered_instances):
                        if it.instance_id == inst.instance_id:
                            self.filtered_instances[idx2] = new_inst
                            break
                    inst = new_inst
                except Exception:
                    pass
            # Update SSM mapping and indicator
            self._ssm_loading_ids.discard(inst.instance_id)
            if info_map:
                self._ssm_info.update(info_map)
                self._ssm_loaded = True
            # Repaint table and details
            self._apply_filter(self.query_one("#search", expect_type=Input).value)
            self._restore_selection_by_instance(inst.instance_id)
            await self._show_instance_details(inst)
            if info_map:
                self._toast(f"Updated: {inst.instance_id}", severity="success")
            else:
                self._toast("No SSM info found for instance", severity="warning")
        except Exception as exc:
            logging.getLogger("ssm_connect").warning(f"Refresh selected failed: {exc}")
            self._toast(f"Failed to refresh: {exc}", severity="error")

    async def _initial_load_instances(self) -> None:
        """Load instances on startup without blocking the UI."""
        logging.getLogger("ssm_connect").info("Initial load: resolving EC2 instances…")
        details_widget: Static = self.query_one("#details", expect_type=Static)
        left_panel: Vertical = self.query_one("#left-panel", expect_type=Vertical)
        # Dim while loading
        try:
            left_panel.add_class("dim")
        except Exception:
            pass
        modal_shown = False
        modal_ref = None
        try:
            if 'ModalScreen' in globals() and ModalScreen is not None:  # type: ignore
                modal_ref = self.RefreshModal()  # type: ignore[attr-defined]
                self.push_screen(modal_ref)
                modal_shown = True
            else:
                details_widget.update("Loading EC2 instances…")
        except Exception:
            details_widget.update("Loading EC2 instances…")

        try:
            # Create session and decide cache vs refresh
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            loop = asyncio.get_running_loop()
            # Verify credentials quietly (optional)
            ok, reason = self._credentials_ok()
            if not ok:
                self._clear_instance_cache()
                msg = f"Credentials/token invalid: {reason}. Not loading instances."
                details_widget.update(msg)
                logging.getLogger("ssm_connect").warning(msg)
                # Close modal and undim
                try:
                    if modal_shown:
                        await asyncio.sleep(0.4)
                        self.pop_screen()
                except Exception:
                    pass
                try:
                    left_panel.remove_class("dim")
                except Exception:
                    pass
                self._toast("Credentials invalid or token expired. Cache cleared.")
                return

            use_refresh = self._force_refresh or is_cache_expired(self.cache_file, self.ttl)
            if modal_ref is not None:
                modal_ref.set_message("Fetching instances from AWS…" if use_refresh else "Loading instances from cache…")
            if use_refresh:
                logging.getLogger("ssm_connect").info("Cache expired/forced; fetching from AWS")
                instances: List[InstanceInfo] = await loop.run_in_executor(
                    None, refresh_instance_cache, session, self.cache_file, self._debug
                )
            else:
                logging.getLogger("ssm_connect").info("Loading instances from cache")
                instances = await loop.run_in_executor(None, load_cache, self.cache_file)

            self.all_instances = instances
            count = len(instances)
            logging.getLogger("ssm_connect").info(f"Initial load: {count} instances")
            # Reset SSM cache before populating
            self._ssm_info = {}
            self._ssm_loaded = False
            # Populate table
            self._apply_filter(self.query_one("#search", expect_type=Input).value)
            details_widget.update(f"Loaded {count} instances. Updating SSM…")
            # Kick off SSM background prefetch
            asyncio.create_task(self._prefetch_ssm_info())
        except Exception as exc:
            details_widget.update(f"Failed to load instances: {exc}")
            logging.getLogger("ssm_connect").error(f"Initial load failed: {exc}")
        finally:
            try:
                if modal_shown:
                    await asyncio.sleep(0.6)
                    self.pop_screen()
            except Exception:
                pass
            try:
                left_panel.remove_class("dim")
            except Exception:
                pass

    async def action_connect(self) -> None:
        """Connect to the selected instance using AWS SSM.

        If possible, suspend the Textual app, run the AWS CLI session, then
        resume the app upon exit. If suspension isn't available, fall back to
        closing the app and starting the session after exit (existing behavior).
        """
        row_index = self._current_row_index
        if row_index is None or not (0 <= row_index < len(self.filtered_instances)):
            return
        inst = self.filtered_instances[row_index]

        # If we have SSM data loaded, ensure the target looks connectable
        info = self._ssm_info.get(inst.instance_id)
        if self._ssm_loaded:
            if info is None:
                self._toast("SSM is not available for this instance.")
                return
            status = (info.get("PingStatus") or info.get("Status") or "").lower()
            if status != "online":
                self._toast(f"SSM not online (status: {status or 'unknown'}).")
                return

        # Try to suspend the app and run the session inline
        try:
            suspender = getattr(self, "suspend", None)
            if callable(suspender):
                try:
                    logging.getLogger("ssm_connect").info(
                        f"Starting SSM session to {inst.instance_id}"
                    )
                    with self.suspend():  # type: ignore[attr-defined]
                        connect_to_instance(inst.instance_id, self.profile, self.region)
                finally:
                    # After returning from the session, refresh details in case state changed
                    await self._show_instance_details(inst)
                    logging.getLogger("ssm_connect").info("SSM session ended")
                return
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Failed to run inline SSM session: {exc}")

        # Fallback: exit the TUI and let main() run the session
        self.selected_instance = inst
        await self.action_quit()

    async def _prefetch_ssm_info(self) -> None:
        """Fetch SSM information for all instances in the background and update UI."""
        try:
            logging.getLogger("ssm_connect").info("Fetching SSM instance information…")
            ids = [inst.instance_id for inst in self.all_instances]
            loop = asyncio.get_running_loop()
            info_map: Dict[str, dict] = await loop.run_in_executor(
                None, _fetch_ssm_info_bulk, self.profile, self.region, ids
            )
            self._ssm_info = info_map
            self._ssm_loaded = True
            logging.getLogger("ssm_connect").debug(
                f"SSM info fetched for {len(info_map)}/{len(ids)} instances"
            )
            logging.getLogger("ssm_connect").info(
                f"SSM info ready: managed={len(info_map)} of total={len(ids)}"
            )
            # Re-populate table to show SSM indicators
            self._apply_filter(self.query_one("#search", expect_type=Input).value)
            # If a row is currently selected, refresh its details
            if self._current_row_index is not None and 0 <= self._current_row_index < len(self.filtered_instances):
                await self._show_instance_details(self.filtered_instances[self._current_row_index])
            # Immediately refresh status bar counts after SSM info arrives
            try:
                self._update_token_status()
            except Exception:
                pass
        except Exception as exc:
            logging.getLogger("ssm_connect").debug(f"Failed to prefetch SSM info: {exc}")


###############################################################################
# Main entry point
###############################################################################

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Connect to EC2 via SSM with a Textual TUI.")
    parser.add_argument(
        "-p",
        "--profile",
        default=os.environ.get("AWS_PROFILE", "cs_prod"),
        help="AWS profile to use (overrides AWS_PROFILE).",
    )
    parser.add_argument(
        "-r",
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-2"),
        help="AWS region to use (overrides AWS_REGION).",
    )
    parser.add_argument(
        "-q",
        "--query",
        default="",
        help="Initial filter query for the TUI search box.",
    )
    parser.add_argument(
        "-f",
        "--force-refresh",
        action="store_true",
        help="Force refresh the EC2 instance cache even if it is still valid.",
    )
    parser.add_argument(
        "-t",
        "--ttl",
        type=int,
        default=86400,
        help="Cache TTL in seconds (default: 86400).",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug output to stderr.",
    )
    parser.add_argument(
        "--no-alt",
        action="store_true",
        help="Ignored for compatibility with the Bash version."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    try:
        check_dependencies()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve cache and config paths
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "silentcastle"
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "silentcastle"
    ensure_directories(cache_dir, config_dir)
    config_file = config_dir / "ssm-connect.config"

    # Load JSON configuration (migrate from legacy key=value if present)
    legacy_config_file = config_dir / "ssm-connect.config"
    json_path = config_dir / "ssm-connect.json"
    cfg = load_json_config(json_path)
    # Configure logging to a rotating file in the cache directory
    log_file = cache_dir / "ssm-connect.log"
    logger = logging.getLogger("ssm_connect")
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logging.captureWarnings(True)
    # If no JSON config existed, save defaults now
    if not json_path.exists():
        save_json_config(json_path, cfg)
    if (not json_path.exists()) and legacy_config_file.exists():
        legacy = load_config(legacy_config_file)
        if legacy:
            # Map legacy values into JSON structure
            if "THEME" in legacy:
                cfg["THEME"]["value"] = legacy["THEME"]
            if "CACHE_TTL" in legacy:
                try:
                    cfg["CACHE_TTL"]["value"] = int(legacy["CACHE_TTL"])
                except Exception:
                    pass
            if "TOKEN_CHECK_SECONDS" in legacy:
                try:
                    cfg["TOKEN_CHECK_SECONDS"]["value"] = int(legacy["TOKEN_CHECK_SECONDS"])
                except Exception:
                    pass
            if "TOKEN_PROFILE" in legacy:
                cfg["TOKEN_PROFILE"]["value"] = legacy.get("TOKEN_PROFILE", "")
        save_json_config(json_path, cfg)

    # Determine effective values
    # TTL precedence: if CLI value differs from parser default, override and persist
    parser_default_ttl = 86400
    if args.ttl != parser_default_ttl:
        cfg["CACHE_TTL"]["value"] = int(args.ttl)
        save_json_config(json_path, cfg)
        effective_ttl = args.ttl
    else:
        try:
            effective_ttl = int(cfg["CACHE_TTL"]["value"])
        except Exception:
            effective_ttl = parser_default_ttl
            cfg["CACHE_TTL"]["value"] = effective_ttl
            save_json_config(json_path, cfg)

    selected_theme = cfg["THEME"]["value"]
    # Switch formatter if JSON logging requested; then apply log level
    try:
        log_format = str(cfg.get("LOG_FORMAT", {}).get("value", "text")).lower()
        if logger.handlers:
            if log_format == "json":
                logger.handlers[0].setFormatter(JsonFormatter())
            else:
                logger.handlers[0].setFormatter(
                    logging.Formatter(
                        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                )
    except Exception:
        pass
    if not args.debug:
        try:
            level_name = str(cfg.get("LOG_LEVEL", {}).get("value", "INFO")).upper()
            level = getattr(logging, level_name, logging.INFO)
            logger.setLevel(level)
        except Exception:
            pass
    # Log initial messages after format/level applied
    logger.info("Logging format set to %s", log_format if 'log_format' in locals() else 'text')
    logger.info("Log level set to %s", level_name if not args.debug else 'DEBUG')
    logger.debug("Logger initialized")
    logger.info(
        f"Starting SSM Connect profile={args.profile} region={args.region} debug={args.debug}"
    )
    # Apply log level from config unless --debug
    if not args.debug:
        try:
            level_name = str(cfg.get("LOG_LEVEL", {}).get("value", "INFO")).upper()
            level = getattr(logging, level_name, logging.INFO)
            logger.setLevel(level)
            logger.info(f"Log level set to {level_name}")
        except Exception:
            pass
    try:
        token_check_seconds = int(cfg["TOKEN_CHECK_SECONDS"]["value"])
    except Exception:
        token_check_seconds = 60
        cfg["TOKEN_CHECK_SECONDS"]["value"] = token_check_seconds
        save_json_config(json_path, cfg)
    token_profile = str(cfg["TOKEN_PROFILE"]["value"]).strip()

    cache_file = cache_dir / f"ssm-connect-{args.profile}-{args.region}.cache"

    # Defer loading of instances and credentials to the UI to avoid startup delay.

    # Create and run the TUI app. Launch immediately; it will load instances in background.
    app = SSMConnectApp(
        instances=[],
        profile=args.profile,
        region=args.region,
        initial_query=args.query,
        cache_file=cache_file,
        ttl=effective_ttl,
        debug=args.debug,
        force_refresh=args.force_refresh,
        theme_name=selected_theme,
        config_file=json_path,
        token_check_seconds=token_check_seconds,
        token_profile=token_profile,
    )
    app.run()

    # When the app exits, check if an instance was selected and connect
    if app.selected_instance:
        inst_id = app.selected_instance.instance_id
        logging.getLogger("ssm_connect").debug(f"Connecting to {inst_id}…")
        try:
            logging.getLogger("ssm_connect").info(f"Starting SSM session to {inst_id} (post-exit)")
            connect_to_instance(inst_id, args.profile, args.region)
        except Exception as exc:
            print(f"Error: failed to start SSM session: {exc}", file=sys.stderr)
            logging.getLogger("ssm_connect").error(f"SSM session failed: {exc}")
    else:
        logging.getLogger("ssm_connect").debug("No instance selected. Exiting.")


if __name__ == "__main__":
    main()
