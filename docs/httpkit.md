# httpkit

`httpkit` runs three commands: `trace` (redirect chain), `probe` (one request, optional redirect follow), and `cf-trace` (Cloudflare Request Tracer for a URL in your zone).

**Source:** `scripts/net/httpkit.py`  
**After install:** `httpkit` (after `./toolbox install`)

## Requirements

- **trace / probe:** No credentials; plain HTTPS requests.
- **cf-trace:** Cloudflare API - account ID and API token with **Account → Request Tracer → Read**. Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, or pass `--account-id` and `--api-token`.

## Subcommands

| Command | Purpose |
|--------|---------|
| `trace <url>` | Walk the redirect chain hop-by-hop (default method `HEAD`; use `-X GET` if the origin rejects `HEAD`). |
| `probe <url>` | One request; `-L` / `--follow` follows redirects and summarizes the final response. |
| `cf-trace <url>` | Call Cloudflare to show how zone rules apply to a URL (simulated request). |

Run `httpkit <command> --help` for the full option list.

### Common flags (all subcommands)

| Flag | Default | Purpose |
|------|---------|---------|
| `-X METHOD` / `--method` | `HEAD` (trace/probe), `GET` (cf-trace) | HTTP method |
| `-H 'Name: value'` / `--header` | — | Extra request header (repeatable; last wins on duplicate) |
| `--timeout` | 10s | Per-request or API call timeout in seconds |
| `--insecure` | off | Skip TLS certificate verification (useful for self-signed certs) |
| `--json` | off | Machine-readable output instead of the formatted table/hops |

### cf-trace specific flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--matched-only` | off | Show only trace steps where a rule matched |
| `--protocol` | `HTTP/2` | Protocol label sent to Cloudflare (`HTTP/1.1` to simulate legacy clients) |
| `--max-redirects` | 10 | Max hops before failing (probe/trace only) |

---

## Scenarios

### 1. Probe with redirects (final URL and chain)

If a bare domain redirects to `www` or HTTPS, `probe -L` prints the **last** response and the redirect **chain**.

```bash
httpkit probe crunchyroll.com -L
```

Example output (timings and Ray IDs change over time):

```
╭───────────────────────────────╮
│ probe https://crunchyroll.com │
╰───────────────────────────────╯
403 241.73 ms HEAD
Final URL: https://www.crunchyroll.com/
Chain:
  • https://crunchyroll.com
  • https://www.crunchyroll.com/
  cache-control    public, max-age=1, must-revalidate
  cf-ray           9e029010a82fbe93-IAH
  content-type     text/html; charset=UTF-8
  date             Sun, 22 Mar 2026 04:48:12 GMT
  server           cloudflare
```

The **chain** lists apex to `www`, then headers for the final hop.

### 2. Trace redirect hops (one row per hop)

`trace` prints **each** status and URL in order, not only the final response.

```bash
httpkit trace https://www.exercise.com
```

If there is no redirect, you get one hop:

```
╭────────────────────────────────╮
│ trace https://www.exercise.com │
╰────────────────────────────────╯

Hop 1 200 153.71 ms
  https://www.exercise.com
  cache-control      private, max-age=14400
  cf-cache-status    HIT
  ...
```

If the site returns `405` to `HEAD`, use `-X GET`.

### 3. Cloudflare Rules Trace (full table)

Cloudflare walks phases (WAF, cache, Workers, etc.) for the URL. You need API access to the account that owns the zone.

```bash
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."   # Request Tracer → Read

httpkit cf-trace 'https://www.exercise.com'
```

Output includes a banner, simulated status code, step count, and a Rich table. Column **`M`** is **matched** (Y/N): whether that step's rule evaluation matched this request. Matched rows use green styling when the terminal supports it.

Long zones produce many rows. Use **`--json`** for the raw API envelope, or **`--matched-only`** to list only steps with `matched=true` (scenario 4).

Example (excerpt - middle rows omitted):

```
╭───────────────────────────────────╮
│ cf-trace https://www.exercise.com │
╰───────────────────────────────────╯
Origin / simulated status_code (API): 200
Trace steps: 13
┏━━━━┳━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  # ┃ M ┃ type            ┃ kind ┃ step                           ┃ action             ┃ detail                         ┃
┡━━━━╇━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│  1 │ N │ phase           │      │ http_request_dynamic_redirect  │ -                  │ Single Redirects               │
│    │   │                 │      │                                │                    │ ruleset default (zone) no      │
├────┼───┼─────────────────┼──────┼────────────────────────────────┼────────────────────┼────────────────────────────────┤
│  2 │ N │ product         │      │ file_upload_scan               │ -                  │ Uploaded Content Scanning      │
├────┼───┼─────────────────┼──────┼────────────────────────────────┼────────────────────┼────────────────────────────────┤
│  7 │ Y │ phase           │      │ http_request_cache_settings    │ set_cache_settings │ Cache Rules                    │
│    │   │                 │      │                                │                    │ ruleset default (zone) yes     │
│    │   │                 │      │                                │                    │   Home Page Cache              │
│    │   │                 │      │                                │                    │     action: set_cache_settings │
│    │   │                 │      │                                │                    │     list: cache=True           │
│    │   │                 │      │                                │                    │     expr:                      │
│    │   │                 │      │                                │                    │ (http.request.full_uri eq      │
│    │   │                 │      │                                │                    │ "https://www.exercise.com/")   │
│    │   │                 │      │                                │                    │ or (http.request.full_uri eq   │
│    │   │                 │      │                                │                    │ "...                           │
├────┼───┼─────────────────┼──────┼────────────────────────────────┼────────────────────┼────────────────────────────────┤
│ 13 │ N │ phase           │      │ http_response_headers_transfo... │ -                  │ Transform Rules - HTTP         │
│    │   │                 │      │                                │                    │ Response Headers               │
│    │   │                 │      │                                │                    │ ruleset default (zone) no      │
└────┴───┴─────────────────┴──────┴────────────────────────────────┴────────────────────┴────────────────────────────────┘
```

### 4. Cloudflare Rules Trace: matched steps only

If you only need rules that matched this request:

```bash
httpkit cf-trace 'https://www.exercise.com' --matched-only
```

Example output (same zone as above; row count and columns depend on terminal width):

```
╭───────────────────────────────────╮
│ cf-trace https://www.exercise.com │
╰───────────────────────────────────╯
Origin / simulated status_code (API): 200
Trace steps: 13
┏━━━┳━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ M ┃ type  ┃ kind ┃ step                        ┃ action             ┃ detail                                       ┃
┡━━━╇━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ Y │ phase │      │ http_request_cache_settings │ set_cache_settings │ Cache Rules                                  │
│   │   │       │      │                             │                    │ ruleset default (zone) yes                   │
│   │   │       │      │                             │                    │   Home Page Cache                            │
│   │   │       │      │                             │                    │     action: set_cache_settings               │
│   │   │       │      │                             │                    │     list: cache=True                         │
│   │   │       │      │                             │                    │     expr: (http.request.full_uri eq          │
│   │   │       │      │                             │                    │ "https://www.exercise.com/") or              │
│   │   │       │      │                             │                    │ (http.request.full_uri eq "...               │
├───┼───┼───────┼──────┼─────────────────────────────┼────────────────────┼──────────────────────────────────────────────┤
│ 2 │ Y │ cache │      │ request                     │ -                  │ Cache Parameters                             │
│   │   │       │      │                             │                    │ cache={"key":{"zone_id":"...","scheme":"https" │
│   │   │       │      │                             │                    │ ,"host":"www.exercise.co...                  │
└───┴───┴───────┴──────┴─────────────────────────────┴────────────────────┴──────────────────────────────────────────────┘
```

**Trace steps:** still shows the total count from the API; the **table** only lists matching rows.

### 5. Domain not managed by Cloudflare

If the domain is not proxied through Cloudflare (or not in the account you authenticated with), the API returns a TLS error. `httpkit` catches this and tells you what to do instead:

```bash
httpkit cf-trace --account-id $CLOUDFLARE_ACCOUNT_ID 'hdc-p-ols.spectrumng.net'
```

```
Domain not managed by Cloudflare (or not in this account): https://hdc-p-ols.spectrumng.net
  Try: httpkit trace https://hdc-p-ols.spectrumng.net
```

Use `httpkit trace` for domains that aren't behind Cloudflare.

---

## Tips

- **Scheme:** URLs without `https://` get `https://` prepended (see `--help` on each command).
- **Custom headers:** `-H 'Name: value'` (repeatable). Same format for `cf-trace` headers in the simulated request.
- **Self-signed / internal certs:** add `--insecure` to skip TLS verification on `trace` or `probe`.
- **Scripting:** `--json` on each subcommand prints structured output for piping or saving.

## See also

- Cloudflare Request Tracer API: [Create trace](https://developers.cloudflare.com/api/resources/request_tracers/subresources/traces/methods/create/)
