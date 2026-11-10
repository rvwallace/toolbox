"""Black-box rex-ssh checks; all external tools and user state are disposable."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ssh/rex-ssh.py"
SESSION = "session:11111111-1111-7111-8111-111111111111"
WINDOW = "window:22222222-2222-7222-8222-222222222222"
BLOCK = "block:33333333-3333-7333-8333-333333333333"


class RexSshCliTests(unittest.TestCase):
    """Exercise command boundaries rather than implementation-specific helpers."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="rex-ssh-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.private = self.state / "silentcastle/rex-ssh"
        self.history = self.private / "recent-hosts.json"
        self.log = self.root / "calls.jsonl"
        self.picker_input = self.root / "picker.txt"
        self.scenario = self.root / "rex.json"
        self.configure_rex()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "REX_SESSION": SESSION,
            "REX_BLOCK": BLOCK,
            "REX_SERVER": "unix:///tmp/rex-ssh-test-only.sock",
            "REX_SSH_TEST_LOG": str(self.log),
            "REX_SSH_TEST_SCENARIO": str(self.scenario),
            "REX_SSH_TEST_PICKER": str(self.picker_input),
            "EDITOR": "fake-editor --wait",
        }
        # No inherited application context may select a real client or server.
        for key in ("REX_CLIENT", "REX_SSH_HISTORY_FILE", "REX_SSH_STATE_DIR"):
            self.env.pop(key, None)
        self.executable(
            "rex",
            """
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:1] == ['--autostart=false']:
    args = args[1:]
with open(os.environ['REX_SSH_TEST_LOG'], 'a') as f:
    f.write(json.dumps({'tool': 'rex', 'args': args}) + '\\n')
s = json.loads(Path(os.environ['REX_SSH_TEST_SCENARIO']).read_text())
if 'raw_response' in s:
    print(s['raw_response'])
    sys.exit(0)
if args[:1] == ['ls']:
    print(json.dumps({'sessions': s['sessions']}))
elif args[:2] == ['window', 'new'] or args[:1] == ['split']:
    if s.get('create_error'):
        print('fixture create failed', file=sys.stderr)
        sys.exit(1)
    print(json.dumps({'block_ids': [s['block']], 'window_id': s['window']}))
elif args[:2] == ['block', 'ls']:
    print(json.dumps({'blocks': s.get('blocks', [])}))
elif args[:1] == ['focus']:
    print('{}')
else:
    print('unsupported fake Rex call', file=sys.stderr)
    sys.exit(9)
""",
        )
        self.executable(
            "ssh",
            """
import json, os, sys
with open(os.environ['REX_SSH_TEST_LOG'], 'a') as f:
    f.write(json.dumps({'tool': 'ssh', 'args': sys.argv[1:]}) + '\\n')
sys.exit(int(os.environ.get('REX_SSH_TEST_SSH_EXIT', '0')))
""",
        )
        self.executable(
            "fzf",
            """
import os, sys
from pathlib import Path
text = sys.stdin.read()
with open(os.environ['REX_SSH_TEST_PICKER'], 'a') as f:
    f.write(text)
match = os.environ.get('REX_SSH_TEST_PICK', '')
if not match:
    sys.exit(130)
if match == '__forged__':
    print('999999\\tFORGED DESTINATION')
    sys.exit(0)
for line in text.splitlines():
    if match in line:
        print(line)
        sys.exit(0)
sys.exit(1)
""",
        )
        self.executable(
            "fake-editor",
            """
import json, os, sys
from pathlib import Path
with open(os.environ['REX_SSH_TEST_LOG'], 'a') as f:
    f.write(json.dumps({'tool': 'editor', 'args': sys.argv[1:]}) + '\\n')
if 'REX_SSH_TEST_EDIT' in os.environ:
    Path(sys.argv[-1]).write_text(os.environ['REX_SSH_TEST_EDIT'])
""",
        )

    def executable(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + body.lstrip())
        path.chmod(0o700)

    def configure_rex(self, **changes: object) -> None:
        scenario = {
            "sessions": [{"session_id": SESSION, "label": "fixture"}],
            "block": BLOCK,
            "window": WINDOW,
            **changes,
        }
        self.scenario.write_text(json.dumps(scenario))

    def run_cli(self, *args: str, input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=self.env,
            input=input,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )

    def calls(self, tool: str = "rex") -> list[list[str]]:
        if not self.log.exists():
            return []
        return [
            row["args"]
            for line in self.log.read_text().splitlines()
            if (row := json.loads(line))["tool"] == tool
        ]

    def creations(self) -> list[list[str]]:
        return [
            args
            for args in self.calls()
            if args[:2] == ["window", "new"] or args[:1] == ["split"]
        ]

    def seed_history(self, *records: dict[str, object]) -> None:
        self.private.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.history.write_text(json.dumps({"version": 1, "connections": records}))
        self.history.chmod(0o600)

    @staticmethod
    def record(destination: str, **changes: object) -> dict[str, object]:
        return {
            "destination": destination,
            "label": destination,
            "last_attempt": "2026-11-01T12:00:00+00:00",
            **changes,
        }

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_help_requires_no_rex_connection_or_state(self) -> None:
        self.assert_ok(self.run_cli("--help"))
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.private.exists())

    def test_direct_connection_launches_child_without_contacting_host(self) -> None:
        self.assert_ok(self.run_cli("--label", "Production DB", "ops@db.example"))
        created = self.creations()
        self.assertEqual(len(created), 1)
        self.assertIn(SESSION, created[0])
        self.assertIn("Production DB", created[0])
        self.assertIn("--_connect", created[0])
        self.assertEqual(created[0][-1], "ops@db.example")
        self.assertEqual(self.calls("ssh"), [])

    def test_history_contains_destination_and_attempt_not_command_arguments(
        self,
    ) -> None:
        self.assert_ok(self.run_cli("--label", "Database", "db"))
        data = json.loads(self.history.read_text())
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["connections"]), 1)
        item = data["connections"][0]
        self.assertEqual(item["destination"], "db")
        self.assertEqual(item["label"], "Database")
        self.assertTrue(item["last_attempt"])
        self.assertFalse({"args", "argv", "command", "password"} & set(item))
        self.assertEqual(stat.S_IMODE(self.private.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.history.stat().st_mode), 0o600)

    def test_repeated_destination_is_deduplicated(self) -> None:
        self.assert_ok(self.run_cli("db"))
        self.assert_ok(self.run_cli("--new", "--label", "Database", "db"))
        records = json.loads(self.history.read_text())["connections"]
        self.assertEqual([r["destination"] for r in records], ["db"])
        self.assertEqual(records[0]["label"], "Database")

    def test_no_store_creates_no_private_state(self) -> None:
        self.assert_ok(self.run_cli("--no-store", "db"))
        self.assertEqual(len(self.creations()), 1)
        self.assertFalse(self.private.exists())

    def test_no_store_does_not_rewrite_existing_history(self) -> None:
        self.seed_history(self.record("existing"))
        before = self.history.read_bytes()
        self.assert_ok(self.run_cli("--no-store", "private-target"))
        self.assertEqual(self.history.read_bytes(), before)

    def test_ssh_option_arguments_preserved_but_not_persisted(self) -> None:
        marker = self.root / "must-not-exist"
        identity = f"/tmp/identity with spaces $(touch {marker})"
        ssh_args = [
            "-p",
            "2222",
            "-J",
            "jump",
            "-i",
            identity,
            "-o",
            "Compression=yes",
            "private-target",
        ]
        self.assert_ok(self.run_cli("--label", "Advanced", "--", *ssh_args))
        created = self.creations()[0]
        start = created.index("--_connect")
        self.assertEqual(created[start + 1 :], ["--", *ssh_args])
        self.assertFalse(marker.exists())
        if self.private.exists():
            for file in self.private.iterdir():
                if file.is_file():
                    text = file.read_text()
                    self.assertNotIn("private-target", text)
                    self.assertNotIn(identity, text)

    def test_remote_command_is_rejected_without_contacting_host(self) -> None:
        result = self.run_cli("--", "db", "uname", "-a")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.creations(), [])
        self.assertEqual(self.calls("ssh"), [])

    def test_secret_bearing_inputs_are_rejected_without_echo(self) -> None:
        for args in (
            ["ssh://user:sentinel-secret@db"],
            ["--", "-o", "Password=sentinel-secret", "db"],
            ["--", "--password", "sentinel-secret", "db"],
        ):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("sentinel-secret", result.stdout + result.stderr)
        self.assertFalse(self.private.exists())
        self.assertEqual(self.creations(), [])

    def test_control_characters_cannot_enter_labels_or_history(self) -> None:
        result = self.run_cli("--label", "unsafe\x1b]9;injected\x07", "db")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("\x1b", result.stdout + result.stderr)
        self.assertEqual(self.creations(), [])

    def test_label_cannot_be_interpreted_as_a_rex_option(self) -> None:
        result = self.run_cli("--label=--session=other-session", "db")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.creations(), [])
        self.assertFalse(self.history.exists())

    def test_malformed_rex_response_fails_without_a_traceback(self) -> None:
        self.configure_rex(raw_response="[]")
        result = self.run_cli("db")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual(self.creations(), [])

    def test_stale_inherited_session_is_not_silently_replaced(self) -> None:
        self.env["REX_SESSION"] = "session:44444444-4444-7444-8444-444444444444"
        result = self.run_cli("db")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.creations(), [])

    def test_explicit_session_overrides_stale_inherited_session(self) -> None:
        self.env["REX_SESSION"] = "session:44444444-4444-7444-8444-444444444444"
        self.assert_ok(self.run_cli("--session", SESSION, "db"))
        self.assertIn(SESSION, self.creations()[0])

    def test_rex_creation_failure_does_not_claim_or_save_attempt(self) -> None:
        self.configure_rex(create_error=True)
        result = self.run_cli("db")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.history.exists())

    def test_malformed_history_is_not_overwritten_by_connection(self) -> None:
        self.private.mkdir(parents=True)
        self.history.write_text("{broken")
        result = self.run_cli("db")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.history.read_text(), "{broken")
        self.assertEqual(self.creations(), [])

    def test_edited_history_cannot_supply_ssh_arguments(self) -> None:
        self.seed_history(
            self.record("db", args=["-o", "ProxyCommand=touch /tmp/unwanted"])
        )
        result = self.run_cli("db")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.creations(), [])

    def test_fzf_cancel_leaves_no_connection(self) -> None:
        self.assert_ok(self.run_cli())
        self.assertEqual(self.creations(), [])

    def test_picker_selection_must_match_generated_rows(self) -> None:
        self.env["REX_SSH_TEST_PICK"] = "__forged__"
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.creations(), [])

    def test_alias_discovery_includes_files_without_executing_match(self) -> None:
        ssh_dir = self.home / ".ssh"
        included = ssh_dir / "conf.d"
        included.mkdir(parents=True)
        marker = self.root / "must-not-exist"
        (ssh_dir / "config").write_text(
            "Host alpha *.example !excluded\n  HostName alpha.internal\n"
            "Include conf.d/*.conf\n"
            f'Match exec "touch {marker}"\n  User nobody\n'
        )
        (included / "hosts.conf").write_text(
            "Host beta\n  HostName beta.internal\n  Port 2222\n"
        )
        self.assert_ok(self.run_cli())
        menu = self.picker_input.read_text()
        self.assertIn("alpha", menu)
        self.assertIn("beta", menu)
        self.assertNotIn("*.example", menu)
        self.assertNotIn("excluded", menu)
        self.assertFalse(marker.exists())
        self.assertEqual(self.calls("ssh"), [])

    def test_picker_can_open_an_ssh_config_alias(self) -> None:
        ssh_dir = self.home / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text("Host beta\n  HostName beta.internal\n")
        self.env["REX_SSH_TEST_PICK"] = "beta"
        self.assert_ok(self.run_cli())
        self.assertEqual(self.creations()[0][-1], "beta")

    def test_alias_preview_omits_credential_bearing_values(self) -> None:
        ssh_dir = self.home / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text("Host beta\n  ProxyJump user:s3nt1nel@jump\n")
        self.assert_ok(self.run_cli())
        self.assertNotIn("s3nt1nel", self.picker_input.read_text())

    def test_editor_gets_arguments_and_history_path_without_shell_eval(self) -> None:
        self.seed_history(self.record("db"))
        self.assert_ok(self.run_cli("--edit"))
        calls = self.calls("editor")
        self.assertEqual(calls, [["--wait", str(self.history)]])
        self.assertEqual(self.creations(), [])

    def test_invalid_editor_result_is_preserved_for_correction(self) -> None:
        self.seed_history(self.record("db"))
        before = self.history.read_text()
        self.env["REX_SSH_TEST_EDIT"] = "{invalid edit"
        result = self.run_cli("--edit")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.history.read_text(), "{invalid edit")
        copies = [
            p for p in self.private.iterdir() if p.is_file() and p != self.history
        ]
        self.assertTrue(any(p.read_text() == before for p in copies))
        self.assertEqual(self.creations(), [])

    def test_forget_removes_one_destination_without_rex_calls(self) -> None:
        self.seed_history(self.record("db"), self.record("web"))
        self.assert_ok(self.run_cli("--forget", "db"))
        self.assertEqual(
            [
                r["destination"]
                for r in json.loads(self.history.read_text())["connections"]
            ],
            ["web"],
        )
        self.assertEqual(self.calls(), [])

    def test_clear_requires_confirmation_when_noninteractive(self) -> None:
        self.seed_history(self.record("db"))
        result = self.run_cli("--clear")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(json.loads(self.history.read_text())["connections"])
        self.assert_ok(self.run_cli("--clear", "--yes"))
        self.assertFalse(json.loads(self.history.read_text())["connections"])

    def test_pins_and_tags_are_history_metadata_only(self) -> None:
        self.seed_history(self.record("db"))
        self.assert_ok(self.run_cli("--pin", "db"))
        self.assert_ok(self.run_cli("--tags", "db", "prod,database"))
        item = json.loads(self.history.read_text())["connections"][0]
        self.assertIs(item["pinned"], True)
        self.assertEqual(set(item["tags"]), {"prod", "database"})
        self.assert_ok(self.run_cli("--unpin", "db"))
        self.assertFalse(
            json.loads(self.history.read_text())["connections"][0]["pinned"]
        )
        self.assertEqual(self.calls(), [])

    def test_active_duplicate_switches_without_opening_another_tab(self) -> None:
        self.seed_history(self.record("db"))
        (self.private / "active.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "connections": [
                        {
                            "destination": "db",
                            "session_id": SESSION,
                            "window_id": WINDOW,
                            "block_id": BLOCK,
                        }
                    ],
                }
            )
        )
        self.configure_rex(
            blocks=[{"block_id": BLOCK, "window_id": WINDOW, "placement": "placed"}]
        )
        self.env["REX_SSH_TEST_PICK"] = "Switch"
        self.assert_ok(self.run_cli("db"))
        self.assertEqual(self.creations(), [])
        self.assertTrue(
            any(args[:1] == ["focus"] and BLOCK in args for args in self.calls())
        )

    def test_stale_active_record_does_not_focus_unavailable_pane(self) -> None:
        self.seed_history(self.record("db"))
        (self.private / "active.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "connections": [
                        {
                            "destination": "db",
                            "session_id": SESSION,
                            "window_id": WINDOW,
                            "block_id": BLOCK,
                        }
                    ],
                }
            )
        )
        self.configure_rex(blocks=[])
        self.assert_ok(self.run_cli("db"))
        self.assertEqual(len(self.creations()), 1)
        self.assertFalse(any(args[:1] == ["focus"] for args in self.calls()))

    def test_split_opens_ssh_child_in_requested_direction(self) -> None:
        self.configure_rex(
            blocks=[{"block_id": BLOCK, "window_id": WINDOW, "placement": "placed"}]
        )
        self.assert_ok(self.run_cli("--split", "right", "--no-store", "db"))
        created = self.creations()
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][0], "split")
        self.assertTrue("--split=right" in created[0] or "right" in created[0])
        self.assertIn("--_connect", created[0])
        self.assertEqual(created[0][-1], "db")
        self.assertEqual(self.calls("ssh"), [])

    def test_expiry_keeps_pinned_and_recent_history(self) -> None:
        old = (datetime.now().astimezone() - timedelta(days=90)).isoformat()
        recent = datetime.now().astimezone().isoformat()
        self.seed_history(
            self.record("old", last_attempt=old),
            self.record("pinned", last_attempt=old, pinned=True),
            self.record("recent", last_attempt=recent),
        )
        self.assert_ok(self.run_cli("--expire-days", "30", "--new", "new-host"))
        destinations = {
            r["destination"]
            for r in json.loads(self.history.read_text())["connections"]
        }
        self.assertNotIn("old", destinations)
        self.assertTrue({"pinned", "recent", "new-host"}.issubset(destinations))

    def test_child_mode_uses_exact_ssh_argv_and_returns_exit_status(self) -> None:
        self.env["REX_SSH_TEST_SSH_EXIT"] = "255"
        args = ["-p", "2222", "user@db"]
        result = self.run_cli("--_connect", "--", *args)
        self.assertEqual(result.returncode, 255, result.stdout + result.stderr)
        self.assertEqual(self.calls("ssh"), [args])
        self.assertFalse(self.private.exists())


if __name__ == "__main__":
    unittest.main()
