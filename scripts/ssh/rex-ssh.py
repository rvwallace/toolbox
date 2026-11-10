#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# toolbox-platforms: linux,darwin
"""Open ordinary SSH connections in local Rex tabs, with private recent history."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import glob
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


class Error(Exception):
    """An error safe to display without SSH arguments or history contents."""


_REX_BINARY: str | None = None


def clean(value: object, limit: int = 200) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and all(ch.isprintable() and ch not in "\t\r\n" for ch in value)
    )


def destination_ok(value: object) -> bool:
    # Restrict saved destinations to OpenSSH's user@host/alias form. URI passwords,
    # leading options and control sequences never reach a label, picker or file.
    return bool(
        clean(value)
        and re.fullmatch(
            r"(?:[\w.+-]+@)?(?:[\w.-]+|\[[0-9a-fA-F:]+\]|[0-9a-fA-F:]+)", value
        )
        and not value.startswith("-")
        and value.count("@") <= 1
    )


def label_ok(value: object) -> bool:
    return clean(value) and not value.startswith("-")


def require(name: str) -> str:
    if name == "rex" and _REX_BINARY:
        return _REX_BINARY
    path = shutil.which(name)
    if not path:
        raise Error(f"required command not found: {name}")
    return path


def state_dir() -> Path:
    return (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "silentcastle/rex-ssh"
    )


def private_dir() -> Path:
    path = state_dir()
    if path.is_symlink():
        raise Error("history directory must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise Error("history directory is not owned by this account")
    path.chmod(0o700)
    return path


def check_file(path: Path) -> None:
    if path.is_symlink():
        raise Error("state files must not be symlinks")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise Error("state file must be a regular file owned by this account")
        path.chmod(0o600)


@contextlib.contextmanager
def state_lock():
    path = private_dir() / "state.lock"
    check_file(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read_state(name: str) -> dict:
    path = state_dir() / name
    check_file(path)
    if not path.exists():
        return {"version": 1, "connections": []}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or set(data) != {"version", "connections"}:
            raise ValueError
        if data["version"] != 1 or not isinstance(data["connections"], list):
            raise ValueError
        if len(data["connections"]) > 1000:
            raise ValueError
        seen = set()
        for row in data["connections"]:
            if not isinstance(row, dict) or not destination_ok(row.get("destination")):
                raise ValueError
            if name == "recent-hosts.json":
                if set(row) - {
                    "destination",
                    "label",
                    "last_attempt",
                    "pinned",
                    "tags",
                    "ssh_args",
                }:
                    raise ValueError
                if not label_ok(row.get("label")) or not isinstance(
                    row.get("last_attempt"), str
                ):
                    raise ValueError
                stamp = dt.datetime.fromisoformat(row["last_attempt"])
                if stamp.tzinfo is None or type(row.get("pinned", False)) is not bool:
                    raise ValueError
                tags = row.get("tags", [])
                if (
                    not isinstance(tags, list)
                    or len(tags) > 20
                    or not all(clean(t, 40) for t in tags)
                ):
                    raise ValueError
                saved_argv = profile_args(row)
                saved_destination, unsafe = parse_ssh(saved_argv)
                if unsafe or saved_destination != row["destination"]:
                    raise ValueError
                key = (row["label"], tuple(saved_argv))
            else:
                required = {"destination", "session_id", "window_id", "block_id"}
                if not required <= set(row) or set(row) - required - {
                    "ssh_args",
                    "label",
                }:
                    raise ValueError
                saved_destination, unsafe = parse_ssh(profile_args(row))
                if unsafe or saved_destination != row["destination"]:
                    raise ValueError
                if "label" in row and not label_ok(row["label"]):
                    raise ValueError
                if not all(
                    resource_id(row.get(f), prefix)
                    for f, prefix in (
                        ("session_id", "session"),
                        ("window_id", "window"),
                        ("block_id", "block"),
                    )
                ):
                    raise ValueError
                key = row["block_id"]
            if key in seen:
                raise ValueError
            seen.add(key)
        return data
    except (ValueError, TypeError, KeyError, OverflowError, Error):
        raise Error(
            f"invalid {name}; use --edit to correct history before connecting"
        ) from None


def write_state(name: str, data: dict) -> None:
    directory = private_dir()
    target = directory / name
    check_file(target)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def resource_id(value: object, prefix: str) -> bool:
    return bool(
        isinstance(value, str) and re.fullmatch(prefix + r":[A-Za-z0-9-]+", value)
    )


def rex_json(*args: str, expect_json: bool = True):
    # Do not expose Rex's stderr: a failed creation could echo the child argv.
    result = subprocess.run(
        [require("rex"), "--autostart=false", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise Error("Rex request failed; verify the local server and selected session")
    if not expect_json:
        return None
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise TypeError
        return data
    except (ValueError, TypeError):
        raise Error("Rex returned an invalid response") from None


def response_rows(data: dict, key: str) -> list[dict]:
    rows = data.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise Error("Rex returned an invalid response")
    return rows


def select_session(requested: str | None) -> str:
    endpoint = os.environ.get("REX_SERVER", "")
    if endpoint and not endpoint.startswith(("unix://", "/")):
        raise Error("rex-ssh must run against a local Rex Unix socket")
    sessions = response_rows(rex_json("ls", "--json"), "sessions")
    wanted = requested or os.environ.get("REX_SESSION")
    if wanted:
        matches = [
            s for s in sessions if wanted in (s.get("session_id"), s.get("label"))
        ]
        if len(matches) != 1:
            raise Error(
                "Rex session is missing or ambiguous; select a live session with --session"
            )
    else:
        if len(sessions) != 1:
            raise Error("select a Rex session with --session when more than one exists")
        matches = sessions
    sid = matches[0].get("session_id")
    if not resource_id(sid, "session"):
        raise Error("Rex returned an invalid session ID")
    return sid


def focus_created(session: str, created: dict, requested: str | None = None) -> bool:
    """Server focus alone need not select the app's displayed tab/session."""
    window = created.get("window_id")
    if not resource_id(window, "window"):
        print(
            "rex-ssh: terminal opened, but its app window could not be selected",
            file=sys.stderr,
        )
        return False
    try:
        clients = response_rows(rex_json("client", "ls", "--json"), "clients")
        apps = [
            c
            for c in clients
            if isinstance(c.get("info"), dict) and c["info"].get("kind") == "app"
        ]
        wanted = requested or os.environ.get("REX_CLIENT")
        if wanted:
            apps = [
                c
                for c in apps
                if wanted in (c.get("client_id"), c["info"].get("label"))
            ]
        if len(apps) != 1 or not resource_id(apps[0].get("client_id"), "client"):
            print(
                "rex-ssh: terminal opened; use --client to select one connected app for focus",
                file=sys.stderr,
            )
            return False
        rex_json(
            "-C",
            apps[0]["client_id"],
            "do",
            "session.select",
            "session_id=" + session,
            "window_id=" + window,
            expect_json=False,
        )
        return True
    except Error:
        print(
            "rex-ssh: terminal opened, but app focus was refused. Check Remote Control in Rex Server settings.",
            file=sys.stderr,
        )
        return False


def runtime_module():
    # Keep the support module outside scripts/: toolbox installs every .py there.
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "lib/rex_ssh_runtime.py"
    spec = importlib.util.spec_from_file_location("rex_ssh_runtime", path)
    if not spec or not spec.loader:
        raise Error("cannot load the local SSH runtime helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_split(
    session: str,
    block: str,
    direction: str,
    client: str | None = None,
    *,
    no_store: bool = False,
    label_override: str | None = None,
    notify: bool = False,
    tags: list[str] | None = None,
    expire_days: int | None = None,
    runtime_pid: int | None = None,
) -> int:
    global _REX_BINARY
    if (
        not resource_id(session, "session")
        or not resource_id(block, "block")
        or direction not in {"right", "down"}
    ):
        raise Error("invalid SSH split target")
    # Rex config actions do not inherit terminal PATH. Bootstrap the matching
    # CLI through same-user IPC, then verify the live block's script and PID.
    if runtime_pid is not None:
        try:
            bootstrap = runtime_module().read(runtime_pid)
            binary = bootstrap["rex_path"]
            if (
                not isinstance(binary, str)
                or not Path(binary).is_absolute()
                or Path(binary).name != "rex"
                or not os.access(binary, os.X_OK)
            ):
                raise ValueError
            _REX_BINARY = binary
        except (OSError, ValueError, KeyError):
            raise Error(
                "reopen this connection with the updated rex-ssh to enable native splitting"
            ) from None
    process = rex_json("block", "call", "-s", session, "-b", block, "process")
    child = process.get("child")
    if not isinstance(child, dict) or child.get("script") != str(
        Path(__file__).resolve()
    ):
        return 20  # An unmanaged pane: the Lua key handler keeps the native binding.
    if runtime_pid is not None and child.get("pid") != runtime_pid:
        raise Error("SSH pane process changed; try splitting it again")
    try:
        payload = runtime_module().read(child.get("pid"))
        ssh_args = payload["ssh_args"]
        label = payload["label"]
        if (
            not isinstance(ssh_args, list)
            or not all(isinstance(a, str) for a in ssh_args)
            or not label_ok(label)
        ):
            raise ValueError
        if type(payload["notify"]) is not bool or type(payload["no_store"]) is not bool:
            raise ValueError
        parse_ssh(ssh_args)
    except (OSError, ValueError, KeyError, TypeError):
        raise Error(
            "this SSH pane has no live split metadata; open it with the updated rex-ssh and retry"
        ) from None
    forwarded = [
        "--session",
        session,
        "--split",
        direction,
        "--label",
        label_override or label,
    ]
    if client:
        forwarded.extend(["--client", client])
    if no_store or payload["no_store"]:
        forwarded.append("--no-store")
    if notify or payload["notify"]:
        forwarded.append("--notify")
    if tags is not None:
        forwarded.extend(["--tag", ",".join(tags)])
    if expire_days is not None:
        forwarded.extend(["--expire-days", str(expire_days)])
    # Supply the anchor explicitly to the normal launch path. Don't mutate the
    # environment: split requests can run concurrently with an active SSH login.
    return main([*forwarded, "--", *ssh_args], split_anchor=block)


def profile_args(row: dict) -> list[str]:
    argv = row.get("ssh_args", [row["destination"]])
    if (
        not isinstance(argv, list)
        or not argv
        or len(argv) > 256
        or not all(isinstance(arg, str) for arg in argv)
    ):
        raise Error("invalid saved SSH arguments; use --edit to correct history")
    return argv


def credential_argument(value: str) -> bool:
    return bool(
        re.search(r"(?i)(?:password|passwd|token|secret)\s*[=:]", value)
        or re.search(r"[^\s/@:]+:[^\s/@]+@", value)
    )


def saveable_ssh_option(key: str, value: str) -> bool:
    """Only persist parameters with known, non-command, nonsecret semantics."""
    if not clean(value, 4096) or credential_argument(value):
        return False
    key = key.lower()
    if key in {"port"}:
        return safe_preview("port", value)
    if key == "proxyjump":
        return value == "none" or safe_preview("proxyjump", value)
    if key in {"user", "hostkeyalias"}:
        return bool(re.fullmatch(r"[\w.+-]+", value))
    if key == "hostname":
        return safe_preview("hostname", value)
    if key in {"identityfile", "userknownhostsfile"}:
        return True  # An exact path is data, not a command; keep spaces intact.
    if key in {
        "compression",
        "identitiesonly",
        "batchmode",
        "pubkeyauthentication",
        "passwordauthentication",
        "kbdinteractiveauthentication",
        "forwardagent",
        "forwardx11",
        "forwardx11trusted",
        "tcpkeepalive",
    }:
        return value.lower() in {"yes", "no"}
    if key == "stricthostkeychecking":
        return value.lower() in {"yes", "ask", "accept-new"}
    if key in {
        "serveraliveinterval",
        "serveralivecountmax",
        "connecttimeout",
        "connectionattempts",
    }:
        return value.isascii() and value.isdigit() and len(value) <= 8
    if key == "preferredauthentications":
        return bool(re.fullmatch(r"[a-z0-9,-]+", value))
    return False


def parse_ssh(argv: list[str]) -> tuple[str, bool]:
    # Deliberately only accept interactive-login options. Control actions, remote
    # commands, sshpass, and modes such as -N/-f/-G are not connection launches.
    takes_value = set("BbcDEeFIiJLlmoOpRS")
    flags = set("46AaCgvKkqTtVvXxYy") - set("V")
    index = 0
    destination = None
    unsafe_to_save = False
    while index < len(argv):
        arg = argv[index]
        if not clean(arg, 8192):
            raise Error(
                "SSH arguments contain unsupported control characters or are too long"
            )
        if credential_argument(arg):
            raise Error(
                "credential-bearing SSH arguments are not supported; use SSH prompts or an agent"
            )
        if destination is not None:
            raise Error("remote commands are unsupported; use ssh directly")
        if arg == "--":
            index += 1
            if index != len(argv) - 1:
                raise Error("expected one SSH destination")
            destination = argv[index]
        elif arg.startswith("-"):
            if len(arg) < 2 or arg[1] not in takes_value | flags:
                raise Error("unsupported SSH option for an interactive connection")
            opt = arg[1]
            if opt in takes_value:
                if len(arg) == 2:
                    index += 1
                    if index >= len(argv):
                        raise Error("SSH option requires a value")
                    val = argv[index]
                else:
                    val = arg[2:]
                if not clean(val, 8192):
                    raise Error(
                        "SSH option value contains unsupported control characters"
                    )
                if credential_argument(val):
                    raise Error(
                        "credential-bearing SSH arguments are not supported; use SSH prompts or an agent"
                    )
                if opt == "o":
                    fields = re.split(r"[=\s]+", val, maxsplit=1)
                    key = fields[0].lower()
                    if key in {
                        "remotecommand",
                        "sessiontype",
                        "forkafterauthentication",
                        "stdinnull",
                        "requesttty",
                    }:
                        raise Error(
                            "SSH mode or command overrides are unsupported; use ssh directly"
                        )
                    unsafe_to_save |= len(fields) != 2 or not saveable_ssh_option(
                        key, fields[-1]
                    )
                elif opt in {"i", "F"}:
                    pass  # Caller-specified key/config path, preserved without shell evaluation.
                elif opt == "p":
                    unsafe_to_save |= not saveable_ssh_option("port", val)
                elif opt == "l":
                    unsafe_to_save |= not saveable_ssh_option("user", val)
                elif opt == "J":
                    unsafe_to_save |= not saveable_ssh_option("proxyjump", val)
                else:
                    unsafe_to_save = True
                if opt == "O":
                    raise Error(
                        "SSH control commands are unsupported; use ssh directly"
                    )
            elif any(ch not in flags for ch in arg[1:]):
                raise Error(
                    "unsupported SSH option bundle; pass value options separately"
                )
        else:
            destination = arg
        index += 1
    if not destination_ok(destination):
        raise Error(
            "invalid SSH destination; use a host alias or user@host without credentials"
        )
    return destination, unsafe_to_save


def safe_preview(key: str, value: str) -> bool:
    if not clean(value) or re.search(r"password|token|secret", value, re.IGNORECASE):
        return False
    if key == "port":
        return value.isascii() and value.isdigit() and 1 <= int(value) <= 65535
    if key == "hostname":
        return destination_ok(value) and "@" not in value
    if key == "proxyjump":
        # Do not admit URI-style user:password@host. Only literal SSH jump
        # destinations (with an optional numeric port) are useful in previews.
        pattern = r"(?:[\w.+-]+@)?(?:[\w.-]+|\[[0-9a-fA-F:]+\])(?::[0-9]{1,5})?"
        return all(
            not part.startswith("-") and re.fullmatch(pattern, part)
            for part in value.split(",")
        )
    return False


def aliases() -> dict[str, dict[str, str]]:
    """Discover literal aliases without ssh -G, which can execute Match exec."""
    found: dict[str, dict[str, str]] = {}
    seen: set[Path] = set()
    ssh_dir = Path.home() / ".ssh"

    def read(path: Path, current: list[str], depth: int) -> list[str]:
        if depth > 12 or len(seen) >= 100:
            return current
        path = path.resolve()
        if path in seen:
            return current
        seen.add(path)
        try:
            lines = path.read_text().splitlines()
        except (OSError, UnicodeError):
            return current
        for line in lines:
            try:
                fields = shlex.split(line, comments=True)
            except ValueError:
                continue
            if not fields:
                continue
            if "=" in fields[0]:
                first, value = fields[0].split("=", 1)
                fields = [first, value, *fields[1:]]
            key, values = fields[0].lower(), fields[1:]
            if key == "host":
                current = [
                    v
                    for v in values
                    if destination_ok(v) and not any(c in v for c in "*?!")
                ]
                for host in current:
                    found.setdefault(host, {})
            elif key == "match":
                # Do not pretend conditional values describe all connections.
                current = []
            elif key == "include":
                for value in values:
                    if not clean(value, 4096) or "%" in value or "$" in value:
                        continue
                    pattern = Path(value).expanduser()
                    if not pattern.is_absolute():
                        pattern = ssh_dir / pattern
                    for match in sorted(glob.glob(str(pattern))):
                        current = read(Path(match), current, depth + 1)
            elif key in {"hostname", "port", "proxyjump"} and len(values) == 1:
                value = values[0]
                if safe_preview(key, value):
                    for host in current:
                        found[host].setdefault(key, value)
        return current

    read(ssh_dir / "config", [], 0)
    return found


def choose(rows: list[tuple[str, object]], prompt: str) -> object | None:
    if not rows:
        return None
    lines = [f"{i}\t{label}" for i, (label, _) in enumerate(rows)]
    result = subprocess.run(
        [
            require("fzf"),
            "--delimiter=\t",
            "--with-nth=2..",
            "--height=80%",
            "--reverse",
            "--border",
            f"--prompt={prompt} > ",
        ],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode in (1, 130):
        return None
    if result.returncode:
        raise Error("fzf could not open the connection picker")
    selected = result.stdout.rstrip("\n")
    if selected not in lines:
        raise Error("picker returned an invalid selection")
    return rows[lines.index(selected)][1]


def edit_history() -> None:
    with state_lock():
        path = state_dir() / "recent-hosts.json"
        check_file(path)
        if not path.exists():
            write_state("recent-hosts.json", {"version": 1, "connections": []})
        # Backup raw bytes to allow repairing an already malformed history file.
        fd, _backup = tempfile.mkstemp(
            prefix="recent-hosts.backup-", suffix=".json", dir=state_dir()
        )
        with os.fdopen(fd, "wb") as handle:
            handle.write(path.read_bytes())
        try:
            editor = shlex.split(os.environ.get("EDITOR") or "vi")
        except ValueError:
            raise Error("EDITOR has invalid quoting") from None
        if not editor:
            raise Error("EDITOR is empty")
        require(editor[0])
        result = subprocess.run([*editor, str(path)], check=False)
        check_file(path)
        if result.returncode:
            raise Error("editor exited with an error; history backup retained")
        read_state("recent-hosts.json")
        print("History validated. Private backup retained.")


def resolve_profile(rows: list[dict], target: str, *, label_only: bool = False) -> dict:
    matches = [row for row in rows if row["label"] == target]
    if not matches and not label_only:
        matches = [row for row in rows if row["destination"] == target]
    if len(matches) != 1:
        raise Error(
            "history target is missing or ambiguous; use a unique connection label or --edit"
        )
    return matches[0]


def parsed_tags(value: str) -> list[str]:
    tags = list(dict.fromkeys(v.strip() for v in value.split(",") if v.strip()))
    if len(tags) > 20 or not all(clean(tag, 40) for tag in tags):
        raise Error("invalid tags")
    return tags


def history_change(args) -> None:
    if args.edit:
        edit_history()
        return
    with state_lock():
        data = read_state("recent-hosts.json")
        rows = data["connections"]
        if args.clear:
            if not args.yes:
                raise Error("clearing history requires --yes")
            rows.clear()
        elif args.forget:
            selected = resolve_profile(rows, args.forget)
            rows.remove(selected)
        elif args.pin or args.unpin or args.tags:
            target = args.pin or args.unpin or args.tags[0]
            row = resolve_profile(rows, target)
            if args.tags:
                row["tags"] = parsed_tags(args.tags[1])
            else:
                row["pinned"] = bool(args.pin)
        write_state("recent-hosts.json", data)


def recent_rows(expire_days: int | None = None) -> list[dict]:
    rows = read_state("recent-hosts.json")["connections"]
    if expire_days is not None:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=expire_days)
        rows = [
            r
            for r in rows
            if r.get("pinned") or dt.datetime.fromisoformat(r["last_attempt"]) >= cutoff
        ]
    return sorted(
        rows,
        key=lambda r: (
            bool(r.get("pinned")),
            dt.datetime.fromisoformat(r["last_attempt"]),
        ),
        reverse=True,
    )


def menu(args) -> tuple[list[str], str] | None:
    while True:
        recent = recent_rows(args.expire_days)
        config = aliases()
        rows: list[tuple[str, object]] = []
        for r in recent:
            tags = ",".join(r.get("tags", []))
            label = f"{'★ ' if r.get('pinned') else ''}{r['label']} — {r['destination']}  {tags}  attempted {r['last_attempt']}"
            rows.append((label, (profile_args(r), r["label"])))
        known = {r["destination"] for r in recent}
        for host, details in sorted(config.items()):
            if host in known:
                continue
            preview = " ".join(f"{key}={value}" for key, value in details.items())
            rows.append((f"SSH alias: {host}  {preview}", ([host], host)))
        rows.extend(
            [
                ("New connection…", "new"),
                ("Edit history…", "edit"),
                ("Forget a recent connection…", "forget"),
            ]
        )
        selected = choose(rows, "rex-ssh")
        if selected is None:
            return None
        if selected == "edit":
            edit_history()
        elif selected == "forget":
            target = choose(
                [(r["label"] + " — " + r["destination"], r) for r in recent],
                "Forget",
            )
            if target:
                with state_lock():
                    data = read_state("recent-hosts.json")
                    data["connections"] = [
                        r
                        for r in data["connections"]
                        if (r["label"], profile_args(r))
                        != (target["label"], profile_args(target))
                    ]
                    write_state("recent-hosts.json", data)
        elif selected == "new":
            try:
                host = input("SSH destination: ").strip()
            except EOFError:
                return None
            if not host:
                return None
            if not destination_ok(host):
                raise Error("invalid SSH destination")
            return [host], host
        else:
            return selected[0], selected[1]


def duplicates(
    destination: str, session: str, ssh_args: list[str], label: str
) -> list[dict]:
    stored = read_state("active.json")["connections"]
    relevant = [
        r
        for r in stored
        if r["destination"] == destination
        and r["session_id"] == session
        and profile_args(r) == ssh_args
        and r.get("label", destination) == label
    ]
    if not relevant:
        return []
    live = response_rows(rex_json("block", "ls", "-s", session, "--json"), "blocks")
    return [
        r
        for r in relevant
        if any(
            b.get("block_id") == r["block_id"]
            and b.get("window_id") == r["window_id"]
            and b.get("placement") == "placed"
            for b in live
        )
    ]


def record(
    destination: str,
    label: str,
    session: str,
    created: dict,
    expire_days: int | None,
    ssh_args: list[str],
    tags: list[str] | None = None,
) -> None:
    blocks = created.get("block_ids", [])
    window = created.get("window_id")
    if (
        not isinstance(blocks, list)
        or not blocks
        or not resource_id(blocks[0], "block")
        or not resource_id(window, "window")
    ):
        raise Error("tab opened, but Rex returned no usable IDs; history was not saved")
    with state_lock():
        data = read_state("recent-hosts.json")
        existing = next(
            (
                r
                for r in data["connections"]
                if r["label"] == label and profile_args(r) == ssh_args
            ),
            {},
        )
        rows = recent_rows(expire_days)
        row = {
            "destination": destination,
            "label": label,
            "last_attempt": dt.datetime.now(dt.UTC).isoformat(),
            "pinned": existing.get("pinned", False),
            "tags": tags if tags is not None else existing.get("tags", []),
            "ssh_args": ssh_args,
        }
        rows = [
            row,
            *[r for r in rows if (r["label"], profile_args(r)) != (label, ssh_args)],
        ]
        rows.sort(
            key=lambda r: (
                bool(r.get("pinned")),
                dt.datetime.fromisoformat(r["last_attempt"]),
            ),
            reverse=True,
        )
        data["connections"] = rows[:50]
        write_state("recent-hosts.json", data)
        active = read_state("active.json")
        active["connections"] = [
            r for r in active["connections"] if r["block_id"] not in blocks
        ]
        active["connections"].append(
            {
                "destination": destination,
                "label": label,
                "ssh_args": ssh_args,
                "session_id": session,
                "window_id": window,
                "block_id": blocks[0],
            }
        )
        active["connections"] = active["connections"][-100:]
        write_state("active.json", active)


def notify_failure() -> None:
    if os.environ.get("REX_SESSION") and sys.stdout.isatty():
        # Constant text only; never interpolate remote output or user arguments.
        print(
            "\033]777;notify;rex-ssh;SSH exited with an error. See its terminal for details.\007",
            end="",
            flush=True,
        )


def connect_loop(argv: list[str]) -> int:
    if "--" not in argv:
        raise Error("invalid internal connection invocation")
    separator = argv.index("--")
    internal, ssh_args = argv[:separator], argv[separator + 1 :]
    parser = Parser(add_help=False)
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--no-store", action="store_true")
    parser.add_argument("--label")
    options = parser.parse_args(internal)
    destination, _ = parse_ssh(ssh_args)
    label = options.label or destination
    if not label_ok(label):
        raise Error("invalid internal connection label")
    ssh = require("ssh")
    payload = {
        "ssh_args": ssh_args,
        "label": label,
        "notify": options.notify,
        "no_store": options.no_store,
        "rex_path": str(Path(require("rex")).absolute()),
    }
    try:
        context = runtime_module().serve(payload)
        context.__enter__()
    except OSError:
        print(
            "rex-ssh: live split metadata unavailable; SSH can still connect",
            file=sys.stderr,
        )
        context = None
    try:
        while True:
            result = subprocess.run([ssh, *ssh_args], check=False)
            print(
                f"\n[rex-ssh] SSH exited with status {result.returncode}.", flush=True
            )
            if result.returncode and options.notify:
                notify_failure()
            if not sys.stdin.isatty():
                return (
                    result.returncode
                    if result.returncode >= 0
                    else 128 - result.returncode
                )
            try:
                reply = input("[r] Reconnect  [Enter] Close: ").strip().lower()
            except EOFError:
                return 0
            if reply != "r":
                return 0
    finally:
        if context:
            context.__exit__(None, None, None)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error includes unknown arguments, possibly secrets.
        raise Error("invalid command arguments; use --help (SSH options go after --)")


def main(argv: list[str] | None = None, *, split_anchor: str | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--_connect":
        return connect_loop(argv[1:])
    if argv and argv[0] == "--_native-split":
        private = Parser(add_help=False)
        private.add_argument("session")
        private.add_argument("block")
        private.add_argument("direction")
        private.add_argument("client", nargs="?")
        private.add_argument("--runtime-pid", type=int)
        selected = private.parse_args(argv[1:])
        return native_split(
            selected.session,
            selected.block,
            selected.direction,
            selected.client,
            runtime_pid=selected.runtime_pid,
        )
    parser = Parser(
        description=__doc__,
        epilog="SSH options: rex-ssh [helper options] -- -p 2222 user@host. Remote commands are unsupported.",
    )
    parser.add_argument("destination", nargs="?")
    parser.add_argument("--label")
    parser.add_argument(
        "--recent", metavar="LABEL", help="reopen one saved connection by exact label"
    )
    parser.add_argument("--session", "-s")
    parser.add_argument("--client", help="Rex app ID or label to select the new tab in")
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="do not write history or active-tab state",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="open another tab even if this target is already managed",
    )
    parser.add_argument(
        "--split",
        choices=["right", "down"],
        help="open a separate SSH connection beside the current pane",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="request a Rex desktop notification if SSH exits with an error",
    )
    parser.add_argument(
        "--expire-days",
        type=int,
        help="exclude old unpinned history, pruning it on the next stored launch",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--edit", action="store_true")
    group.add_argument("--forget", metavar="DESTINATION")
    group.add_argument("--clear", action="store_true")
    group.add_argument("--pin", metavar="DESTINATION")
    group.add_argument("--unpin", metavar="DESTINATION")
    parser.add_argument(
        "--tags",
        nargs="+",
        metavar="VALUE",
        help="connection tags, or TARGET TAGS to edit saved tags; put destination first or SSH args after --",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="add connection tags (comma-separated; repeatable)",
    )
    parser.add_argument("--yes", action="store_true", help="confirm --clear")
    if "--" in argv:
        pos = argv.index("--")
        own, ssh_args = argv[:pos], argv[pos + 1 :]
    else:
        own, ssh_args = argv, []
    args = parser.parse_args(own)
    if args.expire_days is not None and not 0 <= args.expire_days <= 36500:
        raise Error("--expire-days must be between 0 and 36500")
    connection_tags = None
    connection_context = bool(args.destination or ssh_args or args.recent or args.label)
    tag_management = bool(args.tags and len(args.tags) == 2 and not connection_context)
    if args.tags and not tag_management:
        if len(args.tags) != 1:
            raise Error(
                "use one comma-separated tag list with a connection; use TARGET TAGS for history editing"
            )
        connection_tags = parsed_tags(args.tags[0])
        args.tags = None
    if args.tag:
        connection_tags = list(
            dict.fromkeys([*(connection_tags or []), *parsed_tags(",".join(args.tag))])
        )
        if len(connection_tags) > 20:
            raise Error("invalid tags")
    management = (
        args.edit
        or args.forget
        or args.clear
        or args.pin
        or args.unpin
        or tag_management
    )
    if management:
        if (
            args.destination
            or ssh_args
            or args.no_store
            or args.split
            or args.new
            or args.label
            or args.notify
            or args.session
            or args.client
            or args.expire_days is not None
            or args.recent
            or connection_tags is not None
        ):
            raise Error("history management cannot be combined with connection options")
        for target in [
            args.forget,
            args.pin,
            args.unpin,
            args.tags[0] if args.tags else None,
        ]:
            if target is not None and not label_ok(target):
                raise Error("invalid history target")
        history_change(args)
        return 0
    if args.yes:
        raise Error("--yes is only supported with --clear")
    if args.destination:
        if ssh_args:
            raise Error("put the destination after the SSH options following --")
        ssh_args = [args.destination]
    label = args.label
    if args.recent:
        if ssh_args:
            raise Error("--recent cannot be combined with a destination or SSH options")
        saved = resolve_profile(
            read_state("recent-hosts.json")["connections"], args.recent, label_only=True
        )
        ssh_args = profile_args(saved)
        label = label or saved["label"]
    if not ssh_args and args.split:
        session = select_session(args.session)
        block = split_anchor or os.environ.get("REX_BLOCK", "")
        code = native_split(
            session,
            block,
            args.split,
            args.client,
            no_store=args.no_store,
            label_override=label,
            notify=args.notify,
            tags=connection_tags,
            expire_days=args.expire_days,
        )
        if code == 20:
            raise Error(
                "current pane is not managed by rex-ssh; provide an SSH destination"
            )
        return code
    if not ssh_args:
        selected = menu(args)
        if selected is None:
            return 0
        ssh_args, default_label = selected
        label = label or default_label
    destination, unsafe = parse_ssh(ssh_args)
    label = label or destination
    if not label_ok(label):
        raise Error(
            "label must be printable text without control characters (maximum 200 characters)"
        )
    require("ssh")
    session = select_session(args.session)
    store = not args.no_store and not unsafe
    if store:
        # Validate before any mutation of Rex; corruption must not open a tab.
        read_state("recent-hosts.json")
        read_state("active.json")
        existing = (
            []
            if args.new or args.split
            else duplicates(destination, session, ssh_args, label)
        )
        if existing:
            rows = [
                (f"Switch to existing tab ({i + 1})", r) for i, r in enumerate(existing)
            ]
            rows.append(("Open another connection", "new"))
            selected = choose(rows, "Already open")
            if selected is None:
                return 0
            if selected != "new":
                rex_json(
                    "focus", "-s", session, selected["block_id"], expect_json=False
                )
                focused = focus_created(session, selected, args.client)
                print(
                    "Selected existing managed tab."
                    if focused
                    else "Existing managed tab found; app focus was not confirmed."
                )
                return 0
    child = [sys.executable, str(Path(__file__).resolve()), "--_connect"]
    child.extend(["--label", label])
    if args.notify:
        child.append("--notify")
    if args.no_store:
        child.append("--no-store")
    child.extend(["--", *ssh_args])
    if args.split:
        block = split_anchor or os.environ.get("REX_BLOCK")
        if not resource_id(block, "block"):
            raise Error("--split requires a current Rex pane")
        live = response_rows(rex_json("block", "ls", "-s", session, "--json"), "blocks")
        anchor = next(
            (
                b
                for b in live
                if b.get("block_id") == block and b.get("placement") == "placed"
            ),
            None,
        )
        if not anchor:
            raise Error("current Rex pane is not present in the selected session")
        window = anchor.get("window_id")
        if not resource_id(window, "window"):
            raise Error("cannot determine the current Rex pane's window")
        created = rex_json(
            "split",
            "-s",
            session,
            "-b",
            block,
            "--split=" + ("below" if args.split == "down" else "right"),
            "--label",
            label,
            "--json",
            "--shell=none",
            "--",
            *child,
        )
        # `rex split` returns new block IDs but not a window ID: a split stays
        # in the anchor's existing window, unlike `rex window new`.
        created["window_id"] = window
    else:
        created = rex_json(
            "window",
            "new",
            "-s",
            session,
            label,
            "--json",
            "--shell=none",
            "--",
            *child,
        )
    if store:
        record(
            destination,
            label,
            session,
            created,
            args.expire_days,
            ssh_args,
            connection_tags,
        )
    elif unsafe and not args.no_store:
        print(
            "Connection contains SSH options outside the history allowlist and was not saved. Use an SSH alias or --no-store.",
            file=sys.stderr,
        )
    focused = focus_created(session, created, args.client)
    print(
        "Opened SSH terminal; requested focus in Rex."
        if focused
        else "Opened SSH terminal; app focus was not confirmed."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Error, OSError, UnicodeError) as exc:
        message = (
            str(exc)
            if isinstance(exc, Error)
            else "local file or command operation failed"
        )
        print("rex-ssh: " + message, file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
