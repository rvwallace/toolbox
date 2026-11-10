"""Live local IPC checks with fake Rex; no SSH host or real Rex is contacted."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import unittest
from pathlib import Path
from unittest.mock import patch

import test_rex_ssh as fixtures

BLOCK, SCRIPT, SESSION, WINDOW = (
    fixtures.BLOCK,
    fixtures.SCRIPT,
    fixtures.SESSION,
    fixtures.WINDOW,
)

source = Path(__file__).resolve().parents[1] / "lib/rex_ssh_runtime.py"
spec = importlib.util.spec_from_file_location("runtime_test_subject", source)
assert spec and spec.loader
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RexSshCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.payload = {
            "ssh_args": ["-i", "/tmp/key with spaces", "user@fixture"],
            "label": "JumpCloud fixture",
            "notify": True,
            "no_store": True,
            "rex_path": str(self.fixture.bin / "rex"),
        }

    def configure_child(self, **extra):
        self.fixture.configure_rex(
            process={"child": {"pid": os.getpid(), "script": str(SCRIPT)}},
            blocks=[{"block_id": BLOCK, "window_id": WINDOW, "placement": "placed"}],
            **extra,
        )

    def test_socket_round_trip_permissions_and_cleanup(self):
        path = runtime.socket_path(os.getpid())
        with runtime.serve(self.payload):
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertTrue(stat.S_ISSOCK(path.stat().st_mode))
            self.assertEqual(runtime.read(os.getpid()), self.payload)
        self.assertFalse(path.exists())

    def test_peer_check_fails_closed(self):
        with (
            runtime.serve(self.payload),
            patch.object(runtime, "same_user", return_value=False),
        ):
            with self.assertRaises(OSError):
                runtime.read(os.getpid())

    def test_native_split_reuses_exact_in_memory_arguments_without_history(self):
        self.configure_child()
        with runtime.serve(self.payload):
            result = self.fixture.run_cli("--_native-split", SESSION, BLOCK, "right")
        self.fixture.assert_ok(result)
        created = self.fixture.creations()[0]
        self.assertEqual(created[0], "split")
        self.assertIn("--split=right", created)
        self.assertEqual(created[created.index("-b") + 1], BLOCK)
        inner = created[created.index("--_connect") + 1 :]
        self.assertIn("--no-store", inner)
        self.assertIn("--notify", inner)
        self.assertEqual(inner[inner.index("--label") + 1], self.payload["label"])
        self.assertEqual(inner[inner.index("--") + 1 :], self.payload["ssh_args"])
        self.assertFalse(self.fixture.history.exists())
        self.assertFalse((self.fixture.private / "active.json").exists())

    def test_native_split_unmanaged_pane_returns_fallthrough_code(self):
        self.fixture.configure_rex(
            process={"child": {"pid": os.getpid(), "script": "/other/tool.py"}}
        )
        result = self.fixture.run_cli("--_native-split", SESSION, BLOCK, "right")
        self.assertEqual(result.returncode, 20)
        self.assertFalse(self.fixture.creations())

    def test_managed_pane_without_live_socket_fails_instead_of_splitting_locally(self):
        self.configure_child()
        result = self.fixture.run_cli("--_native-split", SESSION, BLOCK, "right")
        self.assertEqual(result.returncode, 1)
        self.assertIn("updated rex-ssh", result.stderr)
        self.assertFalse(self.fixture.creations())

    def test_malformed_runtime_arguments_never_reach_rex_creation(self):
        self.configure_child()
        payload = {
            **self.payload,
            "ssh_args": ["-o", "Token=sentinel-secret", "fixture"],
        }
        with runtime.serve(payload):
            result = self.fixture.run_cli("--_native-split", SESSION, BLOCK, "right")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("sentinel-secret", result.stdout + result.stderr)
        self.assertFalse(self.fixture.creations())

    def test_explicit_split_without_destination_uses_current_connection(self):
        self.configure_child()
        with runtime.serve(self.payload):
            result = self.fixture.run_cli("--split", "down")
        self.fixture.assert_ok(result)
        self.assertIn("--split=below", self.fixture.creations()[0])

    def test_inferred_split_honors_explicit_no_store_and_label(self):
        self.configure_child()
        with runtime.serve({**self.payload, "no_store": False}):
            result = self.fixture.run_cli(
                "--split", "right", "--no-store", "--label", "Private split"
            )
        self.fixture.assert_ok(result)
        inner = self.fixture.creations()[0]
        self.assertIn("--no-store", inner)
        self.assertIn("Private split", inner)
        self.assertFalse(self.fixture.history.exists())

    def test_native_split_derives_window_when_real_cli_omits_it(self):
        self.configure_child(split_without_window=True)
        with runtime.serve({**self.payload, "no_store": False}):
            result = self.fixture.run_cli("--_native-split", SESSION, BLOCK, "right")
        self.fixture.assert_ok(result)
        saved = json.loads(self.fixture.history.read_text())["connections"][0]
        self.assertEqual(saved["ssh_args"], self.payload["ssh_args"])
        actions = [r for r in self.fixture.calls() if "session.select" in r]
        self.assertIn("window_id=" + WINDOW, actions[-1])

    def test_native_split_bootstraps_rex_when_config_action_path_lacks_it(self):
        self.configure_child()
        only_ssh = self.fixture.root / "ssh-only"
        only_ssh.mkdir()
        (only_ssh / "ssh").symlink_to(self.fixture.bin / "ssh")
        self.fixture.env["PATH"] = str(only_ssh)
        with runtime.serve(self.payload):
            result = self.fixture.run_cli(
                "--_native-split",
                SESSION,
                BLOCK,
                "right",
                "--runtime-pid",
                str(os.getpid()),
            )
        self.fixture.assert_ok(result)
        self.assertEqual(len(self.fixture.creations()), 1)


if __name__ == "__main__":
    unittest.main()
