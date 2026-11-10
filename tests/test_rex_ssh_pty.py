"""Exercise reconnect and close using a real terminal and a fake SSH process."""

from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class ReconnectTerminalTest(unittest.TestCase):
    def test_reconnect_then_close(self):
        script = Path(__file__).resolve().parents[1] / "scripts/ssh/rex-ssh.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "ssh-calls"
            fake = root / "ssh"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import os\n"
                "with open(os.environ['SSH_TEST_LOG'], 'a') as f: f.write('called\\n')\n"
                "print('FAKE_SSH_EXIT')\n"
            )
            fake.chmod(0o700)
            master, slave = pty.openpty()
            process = subprocess.Popen(
                [sys.executable, str(script), "--_connect", "--", "fixture-host"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "SSH_TEST_LOG": str(log),
                },
            )
            os.close(slave)
            try:
                output = bytearray()

                def wait_for_prompts(count):
                    deadline = time.monotonic() + 5
                    while output.count(b"[r] Reconnect") < count:
                        if time.monotonic() >= deadline:
                            self.fail("reconnect prompt was not displayed")
                        if select.select([master], [], [], 0.1)[0]:
                            output.extend(os.read(master, 8192))

                wait_for_prompts(1)
                os.write(master, b"r\n")
                wait_for_prompts(2)
                os.write(master, b"\n")
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertEqual(log.read_text().splitlines(), ["called", "called"])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                os.close(master)


if __name__ == "__main__":
    unittest.main()
