#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer>=0.9",
#     "rich>=13.0",
#     "httpx>=0.27",
# ]
# bin-name = "httpkit"
# ///

"""HTTP helpers: redirect trace, quick probe, Cloudflare Rules Trace API.

cf-trace calls POST /accounts/{account_id}/request-tracer/trace. Auth is only
``--account-id`` and ``--api-token`` (or env ``CLOUDFLARE_ACCOUNT_ID`` and
``CLOUDFLARE_API_TOKEN``). The account ID is required in the URL path; the token
does not replace it.

Create an API token in the Cloudflare dashboard (User API Tokens → Create Custom
Token) with permission **Account → Request Tracer → Read** (the API docs call
this "Request Tracer Read"). Scope the token to the account that owns the zones
you trace.
"""

from __future__ import annotations

import json
import time
from typing import Annotated, Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx
import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def _section_banner(command: str, detail: str) -> Panel:
    """Section header that sizes to content (capped) so wide terminals stay readable."""
    term_w = console.width or 80
    cap = min(100, max(32, term_w - 6))
    text = Text.assemble((command, "bold"), " ", (detail, "cyan"))
    approx = len(command) + 1 + len(detail) + 6
    panel_w = max(28, min(approx, cap))
    return Panel(
        text,
        border_style="dim",
        box=box.ROUNDED,
        expand=False,
        padding=(0, 1),
        width=panel_w,
    )
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="HTTP utilities: trace redirects, probe a URL, run Cloudflare Rules Trace.",
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_REDIRECTS = 20
INTERESTING_HEADERS = (
    "location",
    "server",
    "cf-ray",
    "cf-cache-status",
    "cache-control",
    "content-type",
    "date",
)

TRACE_DETAIL_MAX_LEN = 96
_TRACE_PARAM_KEYS_FIRST = (
    "url",
    "target_url",
    "target",
    "redirect_url",
    "to",
    "status_code",
    "status",
    "http_status",
    "id",
    "ruleset_id",
    "ruleset",
    "phase",
    "name",
)

# Keys shown in other columns or structural only — everything else goes into detail.
_CF_TRACE_COLUMN_KEYS = frozenset(
    {
        "type",
        "Type",
        "matched",
        "Matched",
        "step_name",
        "stepName",
        "kind",
        "Kind",
        "action",
        "Action",
    }
)

# Prefer these keys first in detail (human-oriented), then remaining keys sorted.
_CF_TRACE_DETAIL_SKIP_IN_GENERIC = frozenset(
    {
        "public_name",
        "publicName",
        "trace",
        "Trace",
        "managed_headers",
        "managedHeaders",
    }
)

_CF_TRACE_DETAIL_KEY_ORDER = (
    "public_name",
    "publicName",
    "name",
    "Name",
    "rule_name",
    "ruleName",
    "description",
    "Description",
    "detail",
    "message",
    "reason",
    "expression",
    "Expression",
    "action_parameters",
    "actionParameters",
    "parameters",
    "params",
    "metadata",
    "Metadata",
    "result",
    "Result",
    "output",
    "Output",
    "value",
    "Value",
    "cache",
    "Cache",
)


def _json_compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


def _shorten(text: str, max_len: int) -> str:
    t = text.strip()
    if not t:
        return ""
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _format_action_parameters(params: Any, max_len: int) -> str:
    if params is None or params == {}:
        return ""
    if isinstance(params, dict):
        parts: list[str] = []
        seen: set[str] = set()
        for key in _TRACE_PARAM_KEYS_FIRST:
            if key not in params or params[key] in (None, ""):
                continue
            val = params[key]
            if isinstance(val, (dict, list)):
                continue
            parts.append(f"{key}={val}")
            seen.add(key)
        for k, v in sorted(params.items()):
            if k in seen or v in (None, "") or isinstance(v, (dict, list)):
                continue
            if isinstance(v, (str, int, float, bool)):
                parts.append(f"{k}={v}")
        return _shorten(" ".join(parts), max_len) if parts else _shorten(
            _json_compact(params), max_len
        )
    return _shorten(str(params), max_len)


def _cf_pick(step: dict[str, Any], *keys: str) -> Any:
    """Return first present non-empty value (Cloudflare uses snake_case and camelCase)."""
    for k in keys:
        if k not in step:
            continue
        v = step[k]
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (dict, list)) and len(v) == 0:
            continue
        return v
    return None


def _cf_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _cf_format_detail_value(key: str, v: Any, max_piece: int) -> str:
    if isinstance(v, (str, int, float, bool)):
        return f"{key}={_shorten(str(v), max_piece)}"
    try:
        s = _json_compact(v)
    except TypeError:
        s = repr(v)
    return f"{key}={_shorten(s, max_piece)}"


def _format_action_parameter_block(obj: Any, max_len: int) -> str:
    """Format rule action_parameter / action_parameters (incl. from_list redirects)."""
    if obj is None or obj == {}:
        return ""
    if not isinstance(obj, dict):
        return _shorten(str(obj), max_len)
    fl = obj.get("from_list")
    if isinstance(fl, dict):
        nm, ky = fl.get("name", ""), fl.get("key", "")
        parts = [f"${nm}"] if nm else []
        if ky:
            parts.append(str(ky))
        s = "list " + " · ".join(parts) if parts else ""
        return _shorten(s, max_len) if s.strip() else _format_action_parameters(obj, max_len)
    return _format_action_parameters(obj, max_len)


def _indent_multiline(text: str, prefix: str) -> str:
    if not text.strip():
        return text
    return "\n".join(prefix + line if line else line for line in text.split("\n"))


def _format_managed_headers_block(h: Any) -> str:
    if not isinstance(h, list) or not h:
        return ""
    parts: list[str] = []
    for mh in h:
        if not isinstance(mh, dict):
            continue
        hid = str(mh.get("id", "")).strip()
        if not hid:
            continue
        en = mh.get("enabled")
        parts.append(f"{hid}: {'on' if en else 'off'}")
    return "\n".join(parts) if parts else ""


def _summarize_cf_trace_node(node: dict[str, Any], max_expr: int = 72) -> str:
    """Multiline summary for a nested trace item (ruleset / rule / …)."""
    t = _cf_str(_cf_pick(node, "type", "Type")).lower()
    sub_indent = "  "
    if t == "rule":
        lines: list[str] = []
        desc = _cf_str(_cf_pick(node, "description", "Description"))
        if desc:
            lines.append(desc)
        act = _cf_str(_cf_pick(node, "action", "Action"))
        if act:
            lines.append(f"{sub_indent}action: {act}")
        ap = _cf_pick(
            node,
            "action_parameter",
            "action_parameters",
            "actionParameters",
        )
        ap_s = _format_action_parameter_block(ap, max_expr + 40)
        if ap_s:
            lines.append(f"{sub_indent}list: {ap_s}")
        expr = _cf_str(_cf_pick(node, "expression", "Expression"))
        if expr:
            lines.append(f"{sub_indent}expr: {_shorten(expr, max_expr)}")
        if lines:
            return "\n".join(lines)
        sid = _cf_str(_cf_pick(node, "step_name", "stepName"))
        return f"rule {sid}" if sid else "rule"
    if t == "ruleset":
        nm = _cf_str(_cf_pick(node, "name", "Name")) or "?"
        kd = _cf_str(_cf_pick(node, "kind", "Kind"))
        mt = _cf_pick(node, "matched", "Matched")
        mark = "✓" if mt else "✗"
        head = f"ruleset {nm}{f' ({kd})' if kd else ''} {mark}"
        sub = _cf_pick(node, "trace", "Trace")
        if isinstance(sub, list) and sub:
            blocks: list[str] = [head]
            for ch in sub:
                if isinstance(ch, dict):
                    child = _summarize_cf_trace_node(ch, max_expr)
                    blocks.append(_indent_multiline(child, "  "))
            return "\n".join(blocks)
        return head
    nm = _cf_str(_cf_pick(node, "name", "Name"))
    st = _cf_str(_cf_pick(node, "step_name", "stepName"))
    return nm or st or t or "?"


def _format_cf_trace_nested_list(items: list[Any], max_piece: int) -> str:
    if not items:
        return ""
    bits: list[str] = []
    for it in items:
        if isinstance(it, dict):
            bits.append(_summarize_cf_trace_node(it, max_expr=min(88, max_piece)))
        else:
            bits.append(str(it))
    return "\n\n".join(b for b in bits if b)


def _cf_deep_find_action(node: Any, depth: int = 0, max_depth: int = 16) -> str:
    """First non-empty action string in nested trace trees (phase → ruleset → rule)."""
    if depth > max_depth:
        return ""
    if isinstance(node, dict):
        a = _cf_pick(node, "action", "Action")
        if isinstance(a, str) and a.strip():
            return a.strip()
        for key in ("trace", "Trace"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    if found := _cf_deep_find_action(child, depth + 1, max_depth):
                        return found
    elif isinstance(node, list):
        for item in node:
            if found := _cf_deep_find_action(item, depth + 1, max_depth):
                return found
    return ""


def _cf_detail_extra_lines(step: dict[str, Any], max_piece: int) -> list[str]:
    """Format keys not handled as headline blocks (public_name, trace, managed_headers)."""
    param_keys = frozenset(
        ("action_parameters", "actionParameters", "parameters", "params")
    )
    ordered = [
        k
        for k in _CF_TRACE_DETAIL_KEY_ORDER
        if k not in _CF_TRACE_COLUMN_KEYS
        and k not in _CF_TRACE_DETAIL_SKIP_IN_GENERIC
    ]
    rest = sorted(
        k
        for k in step
        if k not in _CF_TRACE_COLUMN_KEYS
        and k not in _CF_TRACE_DETAIL_KEY_ORDER
        and k not in _CF_TRACE_DETAIL_SKIP_IN_GENERIC
    )
    lines: list[str] = []
    for k in (*ordered, *rest):
        if k not in step:
            continue
        v = step[k]
        if v is None or v == "" or v == {} or v == []:
            continue
        if k in param_keys:
            if ap_s := _format_action_parameters(v, max_len=max_piece):
                lines.append(ap_s)
        else:
            lines.append(_cf_format_detail_value(k, v, max_piece))
    return lines


def _dedupe_preserve_order(bits: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _format_cf_trace_detail(step: dict[str, Any], max_piece: int = TRACE_DETAIL_MAX_LEN) -> str:
    if not isinstance(step, dict):
        return "—"

    blocks: list[str] = []
    if pub := _cf_str(_cf_pick(step, "public_name", "publicName")):
        blocks.append(pub)

    tr = _cf_pick(step, "trace", "Trace")
    if isinstance(tr, list) and tr:
        if nested := _format_cf_trace_nested_list(tr, max_piece):
            blocks.append(nested)

    mh = _cf_pick(step, "managed_headers", "managedHeaders")
    if mh is not None and (mh_s := _format_managed_headers_block(mh)):
        blocks.append(mh_s)

    blocks.extend(_cf_detail_extra_lines(step, max_piece))
    out = _dedupe_preserve_order(blocks)
    return "\n".join(out) if out else "—"


def normalize_url(url: str) -> str:
    u = url.strip()
    if not urlparse(u).scheme:
        u = "https://" + u
    return u


def parse_header_options(values: list[str] | None) -> dict[str, str]:
    if not values:
        return {}
    out: dict[str, str] = {}
    for raw in values:
        if ":" not in raw:
            raise typer.BadParameter(f"Header must be Name: value, got: {raw!r}")
        name, value = raw.split(":", 1)
        out[name.strip()] = value.lstrip()
    return out


_HEADER_OPTION_HELP = (
    "Extra request header (repeatable). Each flag adds one header: "
    "Name: value — there must be a colon; everything after the first colon is the value "
    "(value may be empty). Quote the whole argument in the shell if the value contains spaces. "
    "Examples: -H 'User-Agent: curl/8' -H 'Accept: application/json' "
    "-H 'Authorization: Bearer mytoken'. "
    "If the same header name is passed more than once, the last wins."
)

_HEADER_OPTION_HELP_CFTRACE = (
    "Header for the URL Cloudflare simulates (repeatable). "
    "Same Name: value rules as --header on trace/probe; "
    "these are sent in the trace API payload, not as flags to curl. "
    "Examples: -H 'Cookie: foo=bar' -H 'Accept-Language: en'."
)

_URL_ARG_HELP = (
    "Target URL (scheme optional). If you omit the scheme, https:// is prepended."
)

_METHOD_OPTION_HELP_TRACE_PROBE = (
    "HTTP method for each request. Default HEAD is lightweight; "
    "some origins reject HEAD (405) — use -X GET in that case."
)

_MAX_REDIRECTS_TRACE_HELP = (
    "Maximum redirect hops to follow; stop with an error after this many 3xx responses."
)

_FOLLOW_PROBE_HELP = (
    "Follow redirects with httpx and summarize only the final response. "
    "When there are multiple hops, the printed chain lists each URL."
)

_MAX_REDIRECTS_PROBE_HELP = (
    "Only applies with --follow. Maximum redirect hops before failing."
)

_JSON_HELP_TRACE = (
    "Print the hop list as JSON instead of the human-readable hop output."
)

_JSON_HELP_PROBE = (
    "Print status, timing, final URL, redirect chain, and headers as JSON."
)

_METHOD_OPTION_HELP_CFTRACE = (
    "HTTP method for the simulated visitor request sent to Cloudflare (default GET)."
)

_CF_ACCOUNT_HELP = (
    "Cloudflare account ID (required; or CLOUDFLARE_ACCOUNT_ID). "
    "Shown on Account Home / Account Overview in the dashboard."
)

_CF_API_TOKEN_HELP = (
    "API token with Account → Request Tracer → Read (or CLOUDFLARE_API_TOKEN). "
    "Create a custom token in the dashboard if you do not already have one."
)

_PROTOCOL_CFTRACE_HELP = (
    'Protocol label for the simulated request (default "HTTP/2"). '
    'Use "HTTP/1.1" when you want rules evaluated as if the client used HTTP/1.1.'
)

_CF_TIMEOUT_HELP = (
    "Timeout for the Cloudflare trace API request (not per-hop timing to your origin)."
)

_JSON_HELP_CFTRACE = (
    "Print the Cloudflare API JSON envelope instead of the rule table."
)

_MATCHED_ONLY_HELP = (
    "Show only trace steps with matched=true (rules that applied to this request)."
)


def build_client(
    timeout: float,
    insecure: bool,
    *,
    follow_redirects: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        verify=not insecure,
        follow_redirects=follow_redirects,
        max_redirects=max_redirects,
    )


def next_url_from_response(response: httpx.Response) -> str | None:
    if response.status_code not in (301, 302, 303, 307, 308):
        return None
    loc = response.headers.get("location")
    if not loc:
        return None
    return urljoin(str(response.request.url), loc)


def _interesting_headers(response: httpx.Response) -> dict[str, str]:
    return {
        k: v
        for k, v in response.headers.items()
        if k.lower() in INTERESTING_HEADERS
    }


def _print_interesting_headers(hdrs: dict[str, str]) -> None:
    if not hdrs:
        return
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    for k, v in sorted(hdrs.items(), key=lambda kv: kv[0].lower()):
        tbl.add_row(k, v)
    console.print(tbl)


def _cf_step_matched(obj: Any) -> bool:
    return isinstance(obj, dict) and bool(_cf_pick(obj, "matched", "Matched"))


def _cf_trace_action_cell(step: dict[str, Any]) -> str:
    act_v = _cf_pick(step, "action", "Action")
    if act_v is None:
        return _cf_deep_find_action(step) or "—"
    if isinstance(act_v, (str, int, float, bool)):
        return _cf_str(act_v) or _cf_deep_find_action(step) or "—"
    return _shorten(_json_compact(act_v), 48)


@app.command("trace")
def trace_cmd(
    url: Annotated[str, typer.Argument(help=_URL_ARG_HELP)],
    method: Annotated[
        str,
        typer.Option("--method", "-X", help=_METHOD_OPTION_HELP_TRACE_PROBE),
    ] = "HEAD",
    max_redirects: Annotated[
        int,
        typer.Option("--max-redirects", help=_MAX_REDIRECTS_TRACE_HELP),
    ] = DEFAULT_MAX_REDIRECTS,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Per-request timeout in seconds."),
    ] = DEFAULT_TIMEOUT,
    insecure: Annotated[
        bool,
        typer.Option("--insecure", help="Skip TLS certificate verification."),
    ] = False,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help=_HEADER_OPTION_HELP),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help=_JSON_HELP_TRACE),
    ] = False,
) -> None:
    """Follow redirects and print each hop (status, URL, key headers)."""
    start_url = normalize_url(url)
    headers = parse_header_options(header)
    method_u = method.upper()
    hops: list[dict[str, Any]] = []

    with build_client(timeout, insecure) as client:
        current = start_url
        for i in range(max_redirects + 1):
            t0 = time.monotonic()
            try:
                resp = client.request(method_u, current, headers=headers)
            except httpx.RequestError as e:
                console.print(f"[bold red]Request failed:[/bold red] {e}")
                raise typer.Exit(1) from e
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            hop: dict[str, Any] = {
                "hop": i + 1,
                "url": current,
                "status_code": resp.status_code,
                "elapsed_ms": round(elapsed_ms, 2),
                "headers": _interesting_headers(resp),
            }
            hops.append(hop)

            nxt = next_url_from_response(resp)
            if nxt is None:
                break
            current = nxt
        else:
            console.print(
                f"[bold red]Stopped:[/bold red] exceeded {max_redirects} redirect(s)."
            )
            raise typer.Exit(1)

    if json_out:
        console.print_json(data={"hops": hops})
        return

    console.print(_section_banner("trace", start_url))
    for h in hops:
        console.print(
            f"\n[bold]Hop {h['hop']}[/bold] [cyan]{h['status_code']}[/cyan] "
            f"[dim]{h['elapsed_ms']} ms[/dim]\n  {h['url']}"
        )
        _print_interesting_headers(h["headers"])


@app.command("probe")
def probe_cmd(
    url: Annotated[str, typer.Argument(help=_URL_ARG_HELP)],
    method: Annotated[
        str,
        typer.Option("--method", "-X", help=_METHOD_OPTION_HELP_TRACE_PROBE),
    ] = "HEAD",
    follow: Annotated[
        bool,
        typer.Option("--follow", "-L", help=_FOLLOW_PROBE_HELP),
    ] = False,
    max_redirects: Annotated[
        int,
        typer.Option("--max-redirects", help=_MAX_REDIRECTS_PROBE_HELP),
    ] = DEFAULT_MAX_REDIRECTS,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Per-request timeout in seconds."),
    ] = DEFAULT_TIMEOUT,
    insecure: Annotated[
        bool,
        typer.Option("--insecure", help="Skip TLS certificate verification."),
    ] = False,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help=_HEADER_OPTION_HELP),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help=_JSON_HELP_PROBE),
    ] = False,
) -> None:
    """Send one request (or follow redirects) and summarize status, timing, headers."""
    target = normalize_url(url)
    headers = parse_header_options(header)
    method_u = method.upper()

    with build_client(
        timeout,
        insecure,
        follow_redirects=follow,
        max_redirects=max_redirects,
    ) as client:
        t0 = time.monotonic()
        try:
            r = client.request(method_u, target, headers=headers)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
        except httpx.TooManyRedirects as e:
            console.print(
                f"[bold red]Too many redirects[/bold red] (>{max_redirects}): {e}"
            )
            raise typer.Exit(1) from e
        except httpx.RequestError as e:
            console.print(f"[bold red]Request failed:[/bold red] {e}")
            raise typer.Exit(1) from e

    history = list(r.history) + [r]
    chain = [str(x.request.url) for x in history]

    interesting = _interesting_headers(r)

    payload: dict[str, Any] = {
        "url": target,
        "final_url": str(r.url),
        "status_code": r.status_code,
        "elapsed_ms": round(elapsed_ms, 2),
        "method": method_u,
        "followed": follow,
        "chain": chain,
        "headers": interesting,
    }

    if json_out:
        console.print_json(data=payload)
        return

    console.print(_section_banner("probe", target))
    console.print(
        f"[cyan]{r.status_code}[/cyan] [dim]{payload['elapsed_ms']} ms[/dim] "
        f"[dim]{method_u}[/dim]"
    )
    console.print(f"Final URL: {r.url}")
    if follow and len(chain) > 1:
        console.print("[dim]Chain:[/dim]")
        for u in chain:
            console.print(f"  • {u}")
    _print_interesting_headers(interesting)


@app.command("cf-trace")
def cf_trace_cmd(
    url: Annotated[str, typer.Argument(help=_URL_ARG_HELP)],
    account_id: Annotated[
        str | None,
        typer.Option(
            "--account-id",
            envvar="CLOUDFLARE_ACCOUNT_ID",
            help=_CF_ACCOUNT_HELP,
        ),
    ] = None,
    api_token: Annotated[
        str | None,
        typer.Option(
            "--api-token",
            envvar="CLOUDFLARE_API_TOKEN",
            help=_CF_API_TOKEN_HELP,
        ),
    ] = None,
    method: Annotated[
        str,
        typer.Option("--method", "-X", help=_METHOD_OPTION_HELP_CFTRACE),
    ] = "GET",
    protocol: Annotated[
        str,
        typer.Option("--protocol", help=_PROTOCOL_CFTRACE_HELP),
    ] = "HTTP/2",
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help=_HEADER_OPTION_HELP_CFTRACE),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help=_CF_TIMEOUT_HELP),
    ] = DEFAULT_TIMEOUT,
    json_out: Annotated[
        bool,
        typer.Option("--json", help=_JSON_HELP_CFTRACE),
    ] = False,
    matched_only: Annotated[
        bool,
        typer.Option("--matched-only", help=_MATCHED_ONLY_HELP),
    ] = False,
) -> None:
    """Run Cloudflare Rules Trace (simulated request through zone configuration).

    Auth: --account-id and --api-token (or CLOUDFLARE_ACCOUNT_ID and
    CLOUDFLARE_API_TOKEN). Token must have Account / Request Tracer / Read; see
    module docstring.
    """
    target = normalize_url(url)
    if not account_id:
        console.print(
            "[bold red]Missing account ID:[/bold red] set --account-id or "
            "CLOUDFLARE_ACCOUNT_ID."
        )
        raise typer.Exit(1)

    if not api_token:
        console.print(
            "[bold red]Missing API token:[/bold red] set --api-token or "
            "CLOUDFLARE_API_TOKEN (Account → Request Tracer → Read)."
        )
        raise typer.Exit(1)

    body: dict[str, Any] = {
        "method": method.upper(),
        "url": target,
        "protocol": protocol,
        "headers": parse_header_options(header),
    }

    endpoint = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/request-tracer/trace"
    )
    req_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}",
    }

    try:
        r = httpx.post(
            endpoint,
            headers=req_headers,
            json=body,
            timeout=timeout,
        )
    except httpx.RequestError as e:
        console.print(f"[bold red]API request failed:[/bold red] {e}")
        raise typer.Exit(1) from e

    try:
        data = r.json()
    except json.JSONDecodeError:
        console.print(
            f"[bold red]Non-JSON response[/bold red] (HTTP {r.status_code}):\n{r.text}"
        )
        raise typer.Exit(1)

    if json_out:
        console.print_json(data=data)
        return

    if not data.get("success"):
        errs = data.get("errors") or [{"message": r.text or f"HTTP {r.status_code}"}]
        msgs = [
            (err.get("message", err) if isinstance(err, dict) else err) for err in errs
        ]
        # Cloudflare returns a TLS error when the domain is not proxied through
        # this account — give an actionable hint instead of a raw API error.
        _NOT_CF_SIGNALS = ("tls certificate error", "trace unavailable")
        not_on_cf = any(
            all(s in str(m).lower() for s in _NOT_CF_SIGNALS) for m in msgs
        )
        if not_on_cf:
            parsed = normalize_url(url)
            console.print(
                f"[bold yellow]Domain not managed by Cloudflare[/bold yellow] "
                f"(or not in this account): [cyan]{parsed}[/cyan]\n"
                f"  Try: [bold]httpkit trace {parsed}[/bold]"
            )
        else:
            for msg in msgs:
                console.print(
                    f"[bold red]API error[/bold red] (HTTP {r.status_code}): {msg}"
                )
        raise typer.Exit(1)

    if r.status_code != 200:
        console.print(
            f"[bold red]Unexpected HTTP status[/bold red] {r.status_code}: {r.text[:500]}"
        )
        raise typer.Exit(1)

    result = data.get("result") or {}
    trace = result.get("trace") or []
    status_code = result.get("status_code")

    console.print(_section_banner("cf-trace", target))
    if status_code is not None:
        console.print(f"Origin / simulated status_code (API): [cyan]{status_code}[/cyan]")
    console.print(f"Trace steps: {len(trace)}")

    rows = [t for t in trace if not matched_only or _cf_step_matched(t)]
    if not rows:
        console.print("[dim]No steps to display.[/dim]")
        return

    tbl = Table(show_lines=True)
    tbl.add_column("#", justify="right", style="dim")
    tbl.add_column("M", justify="center")
    tbl.add_column("type")
    tbl.add_column("kind", style="dim")
    tbl.add_column("step")
    tbl.add_column("action", style="dim")
    tbl.add_column("detail", overflow="fold", max_width=100)

    for i, step in enumerate(rows, start=1):
        if not isinstance(step, dict):
            tbl.add_row(str(i), "—", "", "", "", "—", repr(step))
            continue

        matched = _cf_pick(step, "matched", "Matched")
        m = "Y" if matched else ("N" if matched is not None else "—")

        typ = _cf_str(_cf_pick(step, "type", "Type"))
        kind = _cf_str(_cf_pick(step, "kind", "Kind"))
        step_name = _cf_str(_cf_pick(step, "step_name", "stepName"))

        row_style = "bold green" if matched else None

        tbl.add_row(
            str(i),
            m,
            typ,
            kind,
            step_name,
            _cf_trace_action_cell(step),
            _format_cf_trace_detail(step),
            style=row_style,
        )
    console.print(tbl)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
