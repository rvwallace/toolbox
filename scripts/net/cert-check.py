#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer>=0.9",
#     "rich>=13.0",
# ]
# bin-name = "cert-check"
# ///

"""Check and describe SSL/TLS certificates for a domain using stdlib only.

Uses ssl + socket — no openssl binary required.
"""

from __future__ import annotations

import os
import re
import socket
import ssl
import tempfile
from datetime import datetime, timezone
from typing import Any

import typer
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Check and describe SSL/TLS certificates for a domain.",
)

PORT = 443
TIMEOUT = 10


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------

# Each label: starts and ends with alnum, optional hyphen-containing middle.
# Single-char labels (a-z0-9) are valid too.
# TLD must be all-alpha, 2+ chars.  Total length capped at 253.
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)"
    r"+[a-zA-Z]{2,}$"
)


def validate_domain(domain: str) -> str:
    if not DOMAIN_RE.match(domain):
        console.print(f"[bold red]✗[/bold red] Invalid domain name format: {domain}")
        raise typer.Exit(1)
    return domain


# ---------------------------------------------------------------------------
# Certificate retrieval
# ---------------------------------------------------------------------------


def fetch_cert(domain: str, port: int, timeout: float) -> dict[str, Any]:
    """Return the peer certificate dict from an SSL handshake.

    ssl.get_server_certificate() gives PEM, but getpeercert() retrieves the
    decoded dict directly — no PEM parsing needed for check mode.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    try:
        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()  # returns decoded dict
                return cert or {}
    except ssl.SSLCertVerificationError as exc:
        # Still try to pull the cert for reporting; disable verification
        return _fetch_cert_unverified(domain, port, timeout, trust_error=str(exc))
    except (socket.timeout, socket.gaierror, ConnectionRefusedError) as exc:
        console.print(
            f"[bold red]✗[/bold red] Connection failed for {domain}:{port}: {exc}"
        )
        raise typer.Exit(1)


def _decode_der(der: bytes) -> dict[str, Any]:
    """Decode raw DER certificate bytes into a getpeercert()-compatible dict.

    Uses the private CPython API ssl._ssl._test_decode_cert, which is the only
    stdlib path that produces the same decoded dict structure as getpeercert().
    It has been stable across CPython 3.x releases and is used by the stdlib
    test suite itself, but it is not part of the public API.

    If the attribute is absent (future CPython, PyPy, etc.) we return a minimal
    dict containing only the PEM so callers can still display the raw cert.
    The _api_limited flag signals to the caller that field-level data is missing.
    """
    pem = ssl.DER_cert_to_PEM_cert(der)

    if not hasattr(ssl, "_ssl") or not hasattr(ssl._ssl, "_test_decode_cert"):  # type: ignore[attr-defined]
        return {"_pem": pem, "_api_limited": True}

    fd, tmp_path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(pem)
        decoded: dict[str, Any] = ssl._ssl._test_decode_cert(tmp_path)  # type: ignore[attr-defined]
    finally:
        os.unlink(tmp_path)

    decoded["_pem"] = pem
    return decoded


def _fetch_cert_unverified(
    domain: str, port: int, timeout: float, trust_error: str
) -> dict[str, Any]:
    """Fetch and decode a cert even when chain verification fails.

    ssl.getpeercert() returns an empty dict under CERT_NONE, so we grab the
    raw DER bytes via binary_form=True then decode via _decode_der().
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                der = ssock.getpeercert(binary_form=True)
    except (socket.timeout, socket.gaierror, ConnectionRefusedError) as exc:
        console.print(f"[bold red]✗[/bold red] Connection failed for {domain}: {exc}")
        raise typer.Exit(1)

    if not der:
        console.print(
            f"[bold red]✗[/bold red] Server returned no certificate for {domain}"
        )
        raise typer.Exit(1)

    cert = _decode_der(der)
    cert["_trust_error"] = trust_error
    return cert


def fetch_cert_pem(
    domain: str, port: int, timeout: float, cert: dict[str, Any] | None = None
) -> str:
    """Return the PEM string for describe mode.

    If we already decoded an untrusted cert (self-signed etc.) the PEM is
    stashed in cert['_pem'].  Otherwise use ssl.get_server_certificate which
    works fine for trusted certs.
    """
    if cert and "_pem" in cert:
        return cert["_pem"]  # type: ignore[return-value]
    try:
        return ssl.get_server_certificate((domain, port), timeout=timeout)
    except (
        ssl.SSLError,
        socket.timeout,
        socket.gaierror,
        ConnectionRefusedError,
    ) as exc:
        console.print(
            f"[bold red]✗[/bold red] Could not retrieve certificate for {domain}: {exc}"
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_ssl_date(date_str: str) -> datetime:
    """Parse the date format returned by ssl.getpeercert(): 'Jan  1 00:00:00 2025 GMT'."""
    return datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z").replace(
        tzinfo=timezone.utc
    )


def subject_cn(cert: dict[str, Any]) -> str:
    for rdn in cert.get("subject", ()):
        for key, val in rdn:
            if key == "commonName":
                return val
    return "n/a"


def rdn_str(cert: dict[str, Any], field: str) -> str:
    """Format an RDN field (subject or issuer) as a comma-separated string."""
    parts = [f"{key}={val}" for rdn in cert.get(field, ()) for key, val in rdn]
    return ", ".join(parts) if parts else "n/a"


def get_sans(cert: dict[str, Any]) -> list[str]:
    return [val for kind, val in cert.get("subjectAltName", ()) if kind == "DNS"]


def _render_cert_value(val: Any) -> str:
    """Render cert dict values to a readable string.

    ssl.getpeercert() nests values as:
      - tuple[tuple[tuple[str,str],...],...]  for subject/issuer/subjectAltName
      - plain str/int for scalar fields
    We detect depth and flatten accordingly.
    """
    if not isinstance(val, (list, tuple)):
        return str(val)
    lines: list[str] = []
    for item in val:
        if isinstance(item, (list, tuple)):
            if item and isinstance(item[0], (list, tuple)):
                lines.append(", ".join(f"{k}={v}" for k, v in item))
            elif len(item) == 2 and all(isinstance(x, str) for x in item):
                lines.append(f"{item[0]}={item[1]}")
            else:
                lines.append(str(item))
        else:
            lines.append(str(item))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def check(
    domain: str = typer.Argument(..., help="Domain to check (e.g. example.com)"),
    port: int = typer.Option(
        443, "--port", "-p", help="TCP port to connect to.", show_default=True
    ),
    timeout: float = typer.Option(
        10.0,
        "--timeout",
        "-t",
        help="Connection timeout in seconds.",
        show_default=True,
    ),
) -> None:
    """Check certificate validity, trust, and key details."""
    domain = validate_domain(domain)
    cert = fetch_cert(domain, port, timeout)

    if cert.get("_api_limited"):
        console.print(
            "[bold yellow]⚠[/bold yellow]  ssl._ssl._test_decode_cert is unavailable on this "
            "Python runtime. Field-level details cannot be shown; PEM is still available via "
            "[bold]describe[/bold]."
        )
        raise typer.Exit(1)

    now = datetime.now(tz=timezone.utc)
    not_before = parse_ssl_date(cert["notBefore"])
    not_after = parse_ssl_date(cert["notAfter"])
    days_remaining = (not_after - now).days
    trust_error: str | None = cert.get("_trust_error")  # type: ignore[assignment]

    # ── Details grid ────────────────────────────────────────────────────────
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()

    # Subject: strip the "commonName=" prefix for cleaner display
    cn = subject_cn(cert)
    subject_display = cn if cn != "n/a" else rdn_str(cert, "subject")

    # Issuer: keep org + CN only
    issuer_parts = {k: v for rdn in cert.get("issuer", ()) for k, v in rdn}
    issuer_display = issuer_parts.get(
        "commonName",
        rdn_str(cert, "issuer"),
    )
    org = issuer_parts.get("organizationName")
    if org and org not in issuer_display:
        issuer_display = f"{org} — {issuer_display}"

    # Expiry colour
    if now > not_after:
        validity_text = Text("Expired", style="bold red")
    elif days_remaining < 30:
        validity_text = Text(
            f"{not_after.strftime('%Y-%m-%d')}  ({days_remaining}d remaining)",
            style="yellow",
        )
    else:
        validity_text = Text(
            f"{not_after.strftime('%Y-%m-%d')}  ({days_remaining}d remaining)",
            style="green",
        )

    grid.add_row("Subject", subject_display)
    grid.add_row("Issuer", issuer_display)
    grid.add_row("Valid from", not_before.strftime("%Y-%m-%d"))
    grid.add_row("Expires", validity_text)

    panel_title = (
        f"[bold]{domain}[/bold]" if port == 443 else f"[bold]{domain}:{port}[/bold]"
    )
    console.print(
        Panel(
            grid,
            title=panel_title,
            title_align="left",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )

    # ── Checks ──────────────────────────────────────────────────────────────
    console.print(Rule("Checks", style="bright_blue"))

    def ok(msg: str) -> None:
        console.print(f"  [bold green]✓[/bold green]  {msg}")

    def warn(msg: str) -> None:
        console.print(f"  [bold yellow]⚠[/bold yellow]  {msg}")

    def err(msg: str) -> None:
        console.print(f"  [bold red]✗[/bold red]  {msg}")

    if now > not_after:
        err("Certificate has expired")
    elif days_remaining < 30:
        warn(f"Certificate expires in {days_remaining} days")
    else:
        ok(f"Certificate is valid ({days_remaining} days remaining)")

    if now < not_before:
        err("Certificate is not yet valid")

    if cert.get("issuer") == cert.get("subject"):
        warn("Certificate is self-signed")

    if trust_error:
        err(f"Chain not trusted — {trust_error}")
    else:
        ok("Certificate chain is trusted")

    # ── SANs ────────────────────────────────────────────────────────────────
    sans = get_sans(cert)
    console.print(Rule("Subject Alternative Names", style="bright_blue"))
    if sans:
        # Render as wrapped columns when there are many
        san_texts = [Text(f"  {san}", style="cyan") for san in sans]
        console.print(Columns(san_texts, padding=(0, 2)))
    else:
        warn("No SANs found")

    console.print()


@app.command()
def describe(
    domain: str = typer.Argument(..., help="Domain to describe (e.g. example.com)"),
    port: int = typer.Option(
        443, "--port", "-p", help="TCP port to connect to.", show_default=True
    ),
    timeout: float = typer.Option(
        10.0,
        "--timeout",
        "-t",
        help="Connection timeout in seconds.",
        show_default=True,
    ),
) -> None:
    """Print all certificate fields and PEM for a domain."""
    domain = validate_domain(domain)
    cert = fetch_cert(domain, port, timeout)

    # Build a rich table from all fields in the decoded cert dict
    table = Table(
        title=f"Certificate Details — {domain}"
        if port == 443
        else f"Certificate Details — {domain}:{port}",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value")

    skip = {"_trust_error", "_pem", "_api_limited"}
    for field, value in cert.items():
        if field not in skip:
            table.add_row(field, _render_cert_value(value))

    console.print(table)

    # Also show PEM so the user can inspect or pipe it
    console.print(Rule("PEM", style="bright_blue"))
    pem = fetch_cert_pem(domain, port, timeout, cert)
    console.print(Text(pem, style="dim"))


if __name__ == "__main__":
    app()
