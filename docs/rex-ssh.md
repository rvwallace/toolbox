# rex-ssh

The launcher, runtime helper, tests and usage guide now live in
[rex-config](../../rex-config/docs/rex-ssh.md), alongside its Lua split bindings.

`toolbox install` still exposes `rex-ssh` through a small compatibility launcher.
Keep rex-config beside toolbox, or copy its `rex/` directory to `~/.config/rex`
(or `$XDG_CONFIG_HOME/rex`). No full toolbox reinstall is needed for an existing
`bin/rex-ssh` symlink.

Command options and private state paths are unchanged. Existing wrappers retain
support through the compatibility launcher and runtime module. New panes use the
canonical rex-config script. Do not remove the compatibility files while old
SSH panes remain open.

Run the maintained checks from rex-config:

```sh
uv run --python '>=3.11' python -m unittest discover -s tests -p 'test_rex_ssh*.py' -v
```
