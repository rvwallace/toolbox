# shellcheck shell=bash
# Zmx UI integrations (interactive bash only)

toolbox_require_interactive zmx || return 0
toolbox_require_commands zmx zmx || return 0

# Zmx attach current directory basename — Alt-a
bind '"\ea":"zmx attach $(basename \"$PWD\")\n"'

# Zmx detach — Alt-d
bind '"\ed":"zmx detach\n"'

# Load native bash completions
eval "$(zmx completions bash 2>/dev/null)"
