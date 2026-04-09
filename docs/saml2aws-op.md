# saml2aws-op

Wrapper around **`saml2aws login`** for JumpCloud: it fills **username**, **password**, and **TOTP** from **1Password** when possible, then runs `saml2aws` with `--skip-prompt` and MFA set to TOTP.

**Source:** `scripts/aws/saml2aws-op.py`  
**After install:** `saml2aws-op`

## Requirements

- **`saml2aws`** on `PATH`
- **`op`** (1Password CLI) on `PATH` when you want non-interactive auth (local machine, 1Password unlocked)
- A 1Password item (default name: `JumpCloud`) with username, password, and OTP fields compatible with `op item get` / `op --otp`

## Behavior

- **Default saml2aws alias:** `techops` (positional argument overrides it).
- **Default 1Password item:** `JumpCloud` (`--op-item` overrides).
- **SSH sessions:** if `SSH_CONNECTION`, `SSH_CLIENT`, or `SSH_TTY` is set, the script **does not** call 1Password; it prompts for username, password, and OTP in the terminal.
- **Extra flags:** anything after the known options is forwarded to `saml2aws` (for example profile-specific flags your org documents).

## Examples

```bash
# Default alias techops, item JumpCloud
saml2aws-op

# Named profile alias
saml2aws-op production

# Another 1Password item
saml2aws-op --op-item "JumpCloud Work"

# Extra arguments after the alias are forwarded to saml2aws
saml2aws-op techops --session-duration 3600
```

Parse `saml2aws-op --help` for the exact argument layout on your version.

## Retry

If 1Password was used and the first login fails, the script may fetch a **fresh OTP** and retry once.

## Scenarios

- **Laptop with 1Password unlocked:** run `saml2aws-op`; credentials and OTP come from `op`.
- **Over SSH:** run `saml2aws-op`; you type credentials and OTP when prompted (no `op` access).

If `saml2aws` is missing, the script exits with a clear error.
