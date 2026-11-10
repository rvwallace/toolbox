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
                key = row["destination"]
            else:
                if set(row) != {"destination", "session_id", "window_id", "block_id"}:
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
    except (ValueError, TypeError, KeyError, OverflowError):
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
        [require("rex"), "--autostart=false", *args], capture_output=True, text=True
    )
    if result.returncode:
        raise Error("Rex request failed; verify the local server and selected session")
    if not expect_json:
        return None
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except ValueError:
        raise Error("Rex returned an invalid response") from None


def response_rows(data: dict, key: str) -> list[dict]:
    rows = data.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise Error("Rex returned an invalid response")
    return rows


def select_session(requested: str | None) -> str:
    endpoint = os.environ.get("REX_SERVER", "")
    if endpoint and not (endpoint.startswith("unix://") or endpoint.startswith("/")):
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


def parse_ssh(argv: list[str]) -> tuple[str, bool]:
    # Deliberately only accept interactive-login options. Control actions, remote
    # commands, sshpass, and modes such as -N/-f/-G are not connection launches.
    takes_value = set("BbcDEeFIiJLlmoOpRS")
    flags = set("46AaCgvKkqTtVvXxYy") - set("V")
    index = 0
    destination = None
    extra = False
    while index < len(argv):
        arg = argv[index]
        if not clean(arg, 8192):
            raise Error(
                "SSH arguments contain unsupported control characters or are too long"
            )
        if re.search(r"(?i)(?:password|passwd|token|secret)\s*[=:]", arg):
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
            extra = True
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
                if re.search(r"(?i)(?:password|passwd|token|secret)\s*[=:]", val):
                    raise Error(
                        "credential-bearing SSH arguments are not supported; use SSH prompts or an agent"
                    )
                if opt == "o":
                    key = re.split(r"[=\s]", val, maxsplit=1)[0].lower()
                    if key in {
                        "remotecommand",
                        "sessiontype",
                        "forkafterauthentication",
                        "stdinnull",
                        "requesttty",
                        "localcommand",
                        "permitlocalcommand",
                    }:
                        raise Error(
                            "SSH mode or command overrides are unsupported; use ssh directly"
                        )
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
    return destination, extra


def safe_preview(key: str, value: str) -> bool:
    if not clean(value) or re.search(r"password|token|secret", value, re.I):
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
        fd, backup = tempfile.mkstemp(
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
        result = subprocess.run([*editor, str(path)])
        check_file(path)
        if result.returncode:
            raise Error("editor exited with an error; history backup retained")
        read_state("recent-hosts.json")
        print("History validated. Private backup retained.")


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
            rows[:] = [r for r in rows if r["destination"] != args.forget]
        elif args.pin or args.unpin or args.tags:
            target = args.pin or args.unpin or args.tags[0]
            row = next((r for r in rows if r["destination"] == target), None)
            if row is None:
                raise Error("destination is not in recent history")
            if args.tags:
                tags = [v.strip() for v in args.tags[1].split(",") if v.strip()]
                if len(tags) > 20 or not all(clean(t, 40) for t in tags):
                    raise Error("invalid tags")
                row["tags"] = list(dict.fromkeys(tags))
            else:
                row["pinned"] = bool(args.pin)
        write_state("recent-hosts.json", data)


def recent_rows(expire_days: int | None = None) -> list[dict]:
    rows = read_state("recent-hosts.json")["connections"]
    if expire_days is not None:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=expire_days)
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
            rows.append((label, (r["destination"], r["label"])))
        known = {r["destination"] for r in recent}
        for host, details in sorted(config.items()):
            if host in known:
                continue
            preview = " ".join(f"{key}={value}" for key, value in details.items())
            rows.append((f"SSH alias: {host}  {preview}", (host, host)))
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
                [
                    (r["label"] + " — " + r["destination"], r["destination"])
                    for r in recent
                ],
                "Forget",
            )
            if target:
                with state_lock():
                    data = read_state("recent-hosts.json")
                    data["connections"] = [
                        r for r in data["connections"] if r["destination"] != target
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
            return [selected[0]], selected[1]


def duplicates(destination: str, session: str) -> list[dict]:
    stored = read_state("active.json")["connections"]
    relevant = [
        r
        for r in stored
        if r["destination"] == destination and r["session_id"] == session
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
    destination: str, label: str, session: str, created: dict, expire_days: int | None
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
            (r for r in data["connections"] if r["destination"] == destination), {}
        )
        rows = recent_rows(expire_days)
        row = {
            "destination": destination,
            "label": label,
            "last_attempt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "pinned": existing.get("pinned", False),
            "tags": existing.get("tags", []),
        }
        rows = [row, *[r for r in rows if r["destination"] != destination]]
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
    notify = False
    if argv and argv[0] == "--notify":
        notify = True
        argv = argv[1:]
    if not argv or argv[0] != "--":
        raise Error("invalid internal connection invocation")
    ssh_args = argv[1:]
    parse_ssh(ssh_args)
    ssh = require("ssh")
    while True:
        result = subprocess.run([ssh, *ssh_args])
        print(f"\n[rex-ssh] SSH exited with status {result.returncode}.", flush=True)
        if result.returncode and notify:
            notify_failure()
        if not sys.stdin.isatty():
            return (
                result.returncode if result.returncode >= 0 else 128 - result.returncode
            )
        try:
            reply = input("[r] Reconnect  [Enter] Close: ").strip().lower()
        except EOFError:
            return 0
        if reply != "r":
            return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error includes unknown arguments, possibly secrets.
        raise Error("invalid command arguments; use --help (SSH options go after --)")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--_connect":
        return connect_loop(argv[1:])
    parser = Parser(
        description=__doc__,
        epilog="SSH options: rex-ssh [helper options] -- -p 2222 user@host. Remote commands are unsupported.",
    )
    parser.add_argument("destination", nargs="?")
    parser.add_argument("--label")
    parser.add_argument("--session", "-s")
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
    group.add_argument(
        "--tags", nargs=2, metavar=("DESTINATION", "COMMA_SEPARATED_TAGS")
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
    management = (
        args.edit or args.forget or args.clear or args.pin or args.unpin or args.tags
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
            or args.expire_days is not None
        ):
            raise Error("history management cannot be combined with connection options")
        for target in [
            args.forget,
            args.pin,
            args.unpin,
            args.tags[0] if args.tags else None,
        ]:
            if target is not None and not destination_ok(target):
                raise Error("invalid history destination")
        history_change(args)
        return 0
    if args.yes:
        raise Error("--yes is only supported with --clear")
    if args.destination:
        if ssh_args:
            raise Error("put the destination after the SSH options following --")
        ssh_args = [args.destination]
    label = args.label
    if not ssh_args:
        selected = menu(args)
        if selected is None:
            return 0
        ssh_args, default_label = selected
        label = label or default_label
    destination, extra = parse_ssh(ssh_args)
    label = label or destination
    if not label_ok(label):
        raise Error(
            "label must be printable text without control characters (maximum 200 characters)"
        )
    require("ssh")
    session = select_session(args.session)
    store = not args.no_store and not extra
    if store:
        # Validate before any mutation of Rex; corruption must not open a tab.
        read_state("recent-hosts.json")
        read_state("active.json")
        existing = [] if args.new or args.split else duplicates(destination, session)
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
                print("Selected existing managed tab (login state is not verified).")
                return 0
    child = [sys.executable, str(Path(__file__).resolve()), "--_connect"]
    if args.notify:
        child.append("--notify")
    child.extend(["--", *ssh_args])
    if args.split:
        block = os.environ.get("REX_BLOCK")
        if not resource_id(block, "block"):
            raise Error("--split requires a current Rex pane")
        live = response_rows(rex_json("block", "ls", "-s", session, "--json"), "blocks")
        if not any(
            b.get("block_id") == block and b.get("placement") == "placed" for b in live
        ):
            raise Error("current Rex pane is not present in the selected session")
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
        record(destination, label, session, created, args.expire_days)
    elif extra and not args.no_store:
        print(
            "Connection with extra SSH options was not saved. Use an SSH alias for reusable connections.",
            file=sys.stderr,
        )
    print("Opened SSH terminal. Authentication and login are handled there.")
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
