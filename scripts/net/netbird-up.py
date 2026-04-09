#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "playwright",
#     "rich",
# ]
# bin-name = "netbird-up"
# ///

"""
Automate the NetBird SSO login flow with JumpCloud.

Usage:
  uv run src/temp/netbird_up.py
  uv run --script src/temp/netbird_up.py

The script:
  - Launches `netbird up --no-browser` and captures the JumpCloud redirect URL.
  - Automates the JumpCloud login (username, password, TOTP) via Playwright.
  - Optionally pulls credentials and a fresh OTP from the 1Password CLI (`op`).
    We intentionally use the CLI, not an SDK, so each secret fetch still requires
    an authenticated desktop session rather than stored tokens in code.
  - Cleans up the NetBird process on success or failure.

When running locally with the 1Password desktop app, the CLI path removes prompts.
During SSH sessions, or if `op` is unavailable, the script falls back to
interactive prompts for username, password, and MFA.

Prerequisites:
  - Run `uv run playwright install chromium` once to download the browser binary
    that Playwright launches during the JumpCloud automation.
  - Set `NETBIRD_SHOW_BROWSER=1` before running to see the Chromium window
    locally. The flag is ignored when the script detects an SSH session.
  - Set `NETBIRD_DEBUG=1` to print verbose details such as NetBird logs and the
    JumpCloud callback URL.
  - If you rely on 1Password, ensure the item is named `JumpCloud` and exposes
    `username`, `password`, and TOTP fields. The CLI pulls secrets by those labels.
"""

import getpass
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable

from playwright.sync_api import Playwright, sync_playwright, Error as PlaywrightError
from rich.console import Console
from rich.status import Status

DEBUG_ENABLED = os.environ.get("NETBIRD_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

console = Console()

def debug_log(message: str) -> None:
    if DEBUG_ENABLED:
        console.log(message)

NETBIRD_TIMEOUT = 300  # seconds - maximum time to wait for netbird process after URL capture

def watch_netbird_for_url(timeout: int = 120, status: Status | None = None) -> tuple[str | None, subprocess.Popen]:
    """Run `netbird up --no-browser` and wait for the localhost redirect URL or connection confirmation."""
    proc = subprocess.Popen(
        ["netbird", "up", "--no-browser"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    url: str | None = None
    start = time.time()
    pattern = re.compile(r"https?://[^\s]+")
    connected_messages = {"connected", "already connected"}

    while True:
        if time.time() - start > timeout:
            proc.kill()
            raise TimeoutError("Timed out waiting for localhost redirect URL from NetBird")
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        message = line.rstrip()
        if status is not None:
            status.update(f"[bold cyan]netbird:[/bold cyan] {message}")
        elif DEBUG_ENABLED:
            debug_log(f"[dim]{message}[/dim]")
        m = pattern.search(line)
        if m:
            url = m.group(0)
            break
        if line.strip().lower() in connected_messages:
            break

    return url, proc

def running_over_ssh() -> bool:
    """Detect whether the current shell session is using SSH."""
    return any(os.environ.get(var) for var in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))

def _run_op_command(args: list[str]) -> str:
    """Execute a 1Password CLI command and return stripped stdout."""
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as err:
        stderr = (err.stderr or "").strip()
        stdout = (err.stdout or "").strip()
        details = stderr or stdout or "Unknown 1Password CLI error"
        raise RuntimeError(details) from err
    return result.stdout.strip()

def ensure_op_cli_available() -> None:
    """Ensure 1Password CLI is installed."""
    if shutil.which("op") is None:
        raise FileNotFoundError("1Password CLI (op) not found in PATH")



def terminate_process(proc: subprocess.Popen, wait_timeout: float = 5) -> None:
    """Terminate a subprocess and swallow timeout errors."""
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            pass

def determine_headless_mode(ssh_session: bool) -> bool:
    """Return whether Playwright should run headless."""
    env_value = os.environ.get("NETBIRD_SHOW_BROWSER", "").strip()
    show_browser = env_value.lower() in {"1", "true", "yes", "on"}
    if ssh_session and show_browser:
        console.log("[yellow]Ignoring NETBIRD_SHOW_BROWSER in SSH session.[/yellow]")
    return not show_browser or ssh_session

def run_jumpcloud_login(
    playwright: Playwright,
    login_url: str,
    username: str,
    password: str,
    otp_supplier: Callable[[], str],
    status: Status | None = None,
    headless: bool = True,
) -> str:
    """Automate JumpCloud login via Playwright and wait for localhost redirect."""
    try:
        browser = playwright.chromium.launch(headless=headless)
    except PlaywrightError as exc:
        lowered = str(exc).lower()
        if "playwright install" in lowered or "executable doesn't exist" in lowered:
            raise RuntimeError(
                "Playwright browser binaries missing. Run `uv run playwright install chromium` and retry."
            ) from exc
        raise
    context = browser.new_context()
    page = context.new_page()

    try:
        if status is not None:
            status.update("Navigating to JumpCloud login page")
        page.goto(login_url)
        email_input = page.get_by_role("textbox", name="User Email Address")
        continue_button = page.get_by_role("button", name="Continue")
        password_input = page.get_by_role("textbox", name="User Password")
        login_button = page.locator('[data-test-id="UserLogin__PasswordEntry"]').get_by_role("button", name="Login")
        totp_button = page.locator('[data-test-id="UserLogin__MfaChooser__MfaButtons__totp"]')
        auth_error_locator = page.locator('[data-test-id="UserWrapper"] div').filter(has_text="Authentication failed.").first

        if status is not None:
            status.update("Submitting username to JumpCloud")
        email_input.fill(username)
        continue_button.click()

        deadline = time.time() + 20
        while time.time() < deadline:
            if auth_error_locator.is_visible():
                raise RuntimeError("JumpCloud rejected the username or password")
            if password_input.is_visible():
                break
            page.wait_for_timeout(200)
        else:
            raise TimeoutError("Timed out waiting for password entry after submitting username")

        if status is not None:
            status.update("Submitting password to JumpCloud")
        password_input.fill(password)
        login_button.click()

        deadline = time.time() + 30
        while time.time() < deadline:
            if auth_error_locator.is_visible():
                raise RuntimeError("JumpCloud rejected the username or password")
            if totp_button.is_visible():
                totp_button.click()
                break
            page.wait_for_timeout(250)
        else:
            raise TimeoutError("Timed out waiting for MFA chooser after password submission")

        error_locator = page.locator('[data-test-id="UserWrapper"] div').filter(has_text="Verification code was invalid").first
        inputs = page.locator(".TotpInput__loginInput")
        inputs.first.wait_for(state="visible", timeout=10000)
        num_inputs = inputs.count()
        redirect_url = None

        for attempt in range(2):
            if status is not None:
                status.update(f"Submitting MFA code attempt {attempt + 1}")
            mfa_code = otp_supplier()
            if not re.match(r'^\d{6}$', mfa_code):
                raise ValueError("MFA code must be exactly 6 digits")

            for i, digit in enumerate(mfa_code):
                if i >= num_inputs:
                    raise RuntimeError("Unexpected number of MFA input fields on JumpCloud login page")
                inputs.nth(i).fill(digit)

            submission_time = time.time()
            deadline = submission_time + 120

            while time.time() < deadline:
                if page.url.startswith("http://localhost"):
                    redirect_url = page.url
                    break
                if error_locator.is_visible() and time.time() - submission_time > 1:
                    break
                page.wait_for_timeout(250)

            if redirect_url is not None:
                break

            if not error_locator.is_visible():
                raise TimeoutError("Timed out waiting for JumpCloud to redirect after MFA submission")

            if attempt == 0:
                # Clear out the inputs for the retry
                for i in range(num_inputs):
                    inputs.nth(i).fill("")
                page.wait_for_timeout(250)
            else:
                raise RuntimeError("JumpCloud reported the MFA verification code was invalid")

        if redirect_url is None:
            raise RuntimeError("JumpCloud reported the MFA verification code was invalid")

        if status is not None:
            status.update("Received JumpCloud callback")
        debug_log(f"[cyan]Callback URL from JumpCloud login:[/cyan] {redirect_url}")
        return redirect_url
    finally:
        context.close()
        browser.close()

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Credentials:
    username: str
    password: str

class CredentialProvider(ABC):
    """Abstract base class for credential providers."""

    @property
    @abstractmethod
    def is_interactive(self) -> bool:
        """Whether this provider requires user interaction (stdin/stdout)."""
        pass

    @abstractmethod
    def get_credentials(self) -> Credentials:
        """Retrieve the username and password."""
        pass

    @abstractmethod
    def get_otp(self) -> str:
        """Retrieve the current OTP."""
        pass

class OnePasswordProvider(CredentialProvider):
    """Provider that fetches credentials from 1Password CLI."""

    @property
    def is_interactive(self) -> bool:
        return False

    def get_credentials(self) -> Credentials:
        ensure_op_cli_available()
        username = _run_op_command(["op", "item", "get", "JumpCloud", "--fields", "label=username"])
        password = _run_op_command(["op", "item", "get", "JumpCloud", "--fields", "label=password", "--reveal"])
        return Credentials(username=username, password=password)

    def get_otp(self) -> str:
        ensure_op_cli_available()
        return _run_op_command(["op", "item", "get", "JumpCloud", "--otp"])

class ManualProvider(CredentialProvider):
    """Provider that prompts the user for credentials via stdin."""

    @property
    def is_interactive(self) -> bool:
        return True

    def get_credentials(self) -> Credentials:
        username = input("Enter your username: ").strip()
        password = getpass.getpass("Enter your password: ")
        return Credentials(username=username, password=password)

    def get_otp(self) -> str:
        return input("Enter your 6-digit MFA code: ").strip()

def get_credential_provider() -> CredentialProvider:
    """Factory to return the appropriate credential provider."""
    # 1. Allow explicit override via env var
    provider_name = os.environ.get("NETBIRD_PROVIDER", "").strip().lower()
    if provider_name == "1password":
        return OnePasswordProvider()
    elif provider_name == "manual":
        return ManualProvider()

    # 2. Fallback to Manual if running over SSH
    if running_over_ssh():
        console.log("[yellow]SSH session detected; defaulting to manual input.[/yellow]")
        return ManualProvider()

    # 3. Prefer 1Password if available
    if shutil.which("op"):
        console.log("[green]1Password CLI detected; using OnePasswordProvider.[/green]")
        return OnePasswordProvider()

    # 4. Default to Manual
    console.log("[yellow]No automated provider found; defaulting to manual input.[/yellow]")
    return ManualProvider()

def main():
    try:
        with console.status("Waiting for NetBird authentication prompt...", spinner="dots") as netbird_status:
            url_netbird, proc_netbird = watch_netbird_for_url(status=netbird_status)
    except Exception as exc:
        raise RuntimeError("Failed to start NetBird login flow") from exc

    if url_netbird is None:
        console.log("[green]NetBird reported an active session; skipping JumpCloud login.[/green]")
        try:
            proc_netbird.wait(timeout=10)
        except subprocess.TimeoutExpired:
            console.log("[yellow]NetBird process did not exit promptly; killing it.[/yellow]")
            terminate_process(proc_netbird)
        return

    console.log(f"[cyan]Captured NetBird login URL:[/cyan] {url_netbird}")

    try:
        provider = get_credential_provider()
        
        if not provider.is_interactive:
             with console.status("Fetching JumpCloud credentials...", spinner="dots"):
                creds = provider.get_credentials()
        else:
            creds = provider.get_credentials()

        ssh_session = running_over_ssh()
        headless = determine_headless_mode(ssh_session)
        if not headless:
            console.log("[yellow]Launching Playwright with visible browser window.[/yellow]")
        elif DEBUG_ENABLED:
            debug_log("Running Playwright headless")

        with sync_playwright() as playwright:
            with console.status("Completing JumpCloud login...", spinner="dots") as login_status:
                url_jumpcloud = run_jumpcloud_login(
                    playwright,
                    url_netbird,
                    creds.username,
                    creds.password,
                    provider.get_otp,
                    status=login_status,
                    headless=headless,
                )

            # The headless Playwright browser already called the URL for us.
            console.log("[green]Completed JumpCloud login; NetBird should proceed automatically.[/green]")
            debug_log(f"[cyan]Final URL called by Playwright:[/cyan] {url_jumpcloud}")

            with console.status("Waiting for NetBird to finalize...", spinner="dots"):
                try:
                    proc_netbird.wait(timeout=NETBIRD_TIMEOUT)
                    console.log(f"[green]NetBird up process exited with code {proc_netbird.returncode}[/green]")
                except subprocess.TimeoutExpired:
                    console.log(f"[red]NetBird up process still running after {NETBIRD_TIMEOUT}s; killing it.[/red]")
                    terminate_process(proc_netbird)
    except Exception:
        console.log("[red]An error occurred during the JumpCloud login process; terminating NetBird up process.[/red]")
        terminate_process(proc_netbird)
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
