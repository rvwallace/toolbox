# aws-screen-monitor

Polls **EC2 console screenshots** for one instance and shows them in the terminal. It also prints **instance state** and **instance / system status checks**, and can send a **desktop notification** when the instance is **running** with both status checks **ok** (handy during reboots or long Windows updates).

**Source:** `scripts/aws/aws-screen-monitor.sh`  
**After install:** `aws-screen-monitor`

## Requirements

- **aws** CLI (`aws ec2 get-console-screenshot`, `describe-instances`, `describe-instance-status`)
- A **supported terminal** with inline image support: Warp, Ghostty, kitty, iTerm2 (with `imgcat`), or WezTerm
- **base64** for decoding screenshot payload
- Optional: **fzf** for interactive instance pick when you run with **no** instance id
- Optional: **figurine** for an ASCII header (if missing, a plain text banner is used)

## Usage

```bash
aws-screen-monitor i-0123456789abcdef0
```

With no arguments, the script lists **running** instances (needs `fzf`), then monitors the one you pick.

Flags `-h` / `--help` print usage.

## Behavior

- Poll interval: **5 seconds** between screenshot fetches (constant in the script).
- **Screenshot:** written under your SilentCastle cache (`XDG_CACHE_HOME` or `~/.cache/silentcastle/`).
- **Status line:** shows EC2 state and instance / system status check fields with color when stderr is a TTY.
- **Notification:** on macOS uses `osascript` with a sound; on Linux uses `notify-send` if present. Fires **once** per transition to “ready”; if the instance leaves the ready state, the script can notify again on a later ready transition.

## Scenarios

- **Patch or reboot watch:** start the script before reboot; watch the console and status lines until status checks pass and the notification fires.
- **Pick instance interactively:** run with no args, select in `fzf`, then wait.

If the terminal is not one of the supported ones, the script exits early with an error before monitoring.

## Limitations

- Console screenshots are **low resolution** and lag real time; they are a rough view of boot or login screens, not a substitute for metrics or SSM.
