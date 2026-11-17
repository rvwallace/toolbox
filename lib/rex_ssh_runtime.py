"""Compatibility for SSH wrappers started before the move to rex-config."""

import os
import runpy
from pathlib import Path

source = Path(__file__).resolve()
candidates = [
    source.parents[2] / "rex-config/rex/scripts/rex_ssh_runtime.py",
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "rex/scripts/rex_ssh_runtime.py",
]
target = next((p for p in candidates if p.is_file()), None)
if target is None:
    raise OSError(
        "rex-ssh runtime moved; install rex-config beside toolbox or at ~/.config/rex"
    )
_runtime = runpy.run_path(str(target))
for _name in ("read", "serve", "same_user", "socket_path"):
    globals()[_name] = _runtime[_name]
