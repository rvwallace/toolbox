#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# toolbox-platforms: linux,darwin
"""Compatibility launcher; rex-config owns rex-ssh."""

import os
import runpy
import sys
from pathlib import Path

source = Path(__file__).resolve()
candidates = [
    source.parents[3] / "rex-config/rex/scripts/rex-ssh.py",
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "rex/scripts/rex-ssh.py",
]
target = next((p for p in candidates if p.is_file()), None)
if target is None:
    sys.exit("rex-ssh: install rex-config beside toolbox or at ~/.config/rex")
sys.argv[0] = str(target)
runpy.run_path(str(target), run_name="__main__")
