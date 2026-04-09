# PagerDuty tools (`pyduty`, `pd-incident`, `pd-report`)

Three toolbox scripts talk to the PagerDuty REST API. They use **different** env var names in places; read the section for each tool before you set secrets.

**Sources:**

- `scripts/pagerduty/pyduty.py` - `pyduty`
- `scripts/pagerduty/pd-incident.py` - `pd-incident`
- `scripts/pagerduty/pd-report.py` - `pd-report`

---

## Shared auth notes

| Tool | Token env | Config file |
|------|-------------|-------------|
| `pyduty` | `PAGERDUTY_API_TOKEN` | `~/.config/silentcastle/pagerduty.json` with `{"api_token": "..."}` |
| `pd-incident` | `PAGERDUTY_API_KEY` or `PD_API_KEY` | Optional `.env` via `python-dotenv` |
| `pd-report` | `PAGERDUTY_API_KEY` | Optional `.env` via `python-dotenv` |

If both env and file exist for `pyduty`, the code path is defined in the script (see `get_api_token()` there).

---

## `pyduty` (Typer)

Maintenance windows and service lookup.

| Command | Role |
|---------|------|
| `pyduty maint-window list` | List windows (`--service-id`, `--limit`) |
| `pyduty maint-window create` | Create window (`--start`, `--end`, service IDs, optional `--description`, `--tz`) |
| `pyduty maint-window end` | End a window by ID |
| `pyduty maint-window display` | Show one window |
| `pyduty maint-window check-tz` | Print resolved timezone helper |
| `pyduty service list` | List services |
| `pyduty service search <query>` | Search |
| `pyduty service display <id>` | Show one service |

Datetime strings for create accept ISO-style or `YYYY-MM-DD HH:MM:SS`; timezone handling is documented in `--help` and `maint-window check-tz`.

**Example:**

```bash
export PAGERDUTY_API_TOKEN="..."

pyduty maint-window list --limit 10
pyduty maint-window create SVC1 SVC2 --start "2026-03-22 10:00:00" --end "2026-03-22 12:00:00" --tz America/Chicago
```

---

## `pd-incident` (argparse)

Fetch one incident by ID or number with notes and alerts.

**Arguments:**

- `incident_id` (required)
- `-f` / `--format`: `text`, `markdown`, `compact`, `json`
- `-c` / `--clipboard`: copy formatted output to the clipboard
- `-o` / `--output`: write formatted output to a file

**Auth:** `PAGERDUTY_API_KEY` or `PD_API_KEY`.

**Example:**

```bash
export PAGERDUTY_API_KEY="..."

pd-incident Q3ABC123 --format compact --clipboard
pd-incident Q3ABC123 --format markdown -o incident.md
```

Rich status output goes to **stderr** so you can pipe the formatted body from stdout.

---

## `pd-report` (Click)

Multi-service incident report over a time range.

**Env:**

- `PAGERDUTY_API_KEY` (required)
- `PAGERDUTY_SERVICES` (required): comma-separated **service IDs**

**Options:**

- `-i` / `--interval`: e.g. `7d`, `2w`, `1m`, `12h` (relative window ending at now)
- `-o` / `--output`: `markdown` (default), `json`, or `yaml`
- `-f` / `--file`: output path; if omitted, writes under `pagerduty_reports/` with an auto-generated name

If `--interval` is omitted, the script uses its default range logic (see source for `get_default_time_range`).

**Example:**

```bash
export PAGERDUTY_API_KEY="..."
export PAGERDUTY_SERVICES="PABC123,PDEF456"

pd-report --interval 14d --output markdown
```

---

## When to use which

- **One incident, deep dive, clipboard or file:** `pd-incident`
- **Maintenance windows or service search:** `pyduty`
- **Batch report across services and dates:** `pd-report`

Run `pyduty --help`, `pd-incident --help`, and `pd-report --help` for the full option lists.
