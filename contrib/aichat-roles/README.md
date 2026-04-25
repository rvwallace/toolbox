# Optional aichat roles (toolbox Alt+e)

The shell widget in `shell/modules/ai.sh` calls these **custom** roles by name:

| Prefix (after `#`) | Role name           | Built-in? |
|--------------------|---------------------|-----------|
| `#ex`, `#explain`  | `%explain-shell%`   | yes       |
| `#rv`, `#review`   | `review`            | no — copy from here |
| `#er`              | `explain-review`    | no — copy from here |
| `#ask`             | `ask`               | no — copy from here |

Install (recommended):

```bash
./contrib/aichat-roles/install-roles.sh
```

Symlinks `review.md`, `explain-review.md`, and `ask.md` into aichat’s `roles_dir` (parsed from `aichat --info`, or use `AICHAT_ROLES_DIR` if set). Options: `--copy` to copy instead of symlink, `--dry-run`, `-f` / `--force` to replace existing files.

List roles with `aichat --list-roles`.

Role files omit `temperature` in YAML so your default model settings apply (some models reject `temperature: 0`).
