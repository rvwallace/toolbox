#!/usr/bin/env bash
# shellcheck shell=bash
# Ansible: prefer a persistent `uv tool install` over the ephemeral `uv run --with`
# wrapper. These are placeholders only — once installed, the real PATH binaries
# take over and these functions are simply never defined.

toolbox_require_commands ansible uv || return 0

_ansible_install_hint() {
    cat >&2 <<EOF
'$1' is not installed.

Install with:
  uv tool install ansible-core
  uv tool install ansible-lint

Then restart your shell (or run: exec \$SHELL) to pick up the new binaries.
EOF
    return 127
}

for _ansible_cmd in ansible ansible-playbook ansible-vault ansible-galaxy ansible-lint \
    ansible-doc ansible-config ansible-console ansible-inventory ansible-pull; do
    command -v "$_ansible_cmd" >/dev/null 2>&1 || eval "${_ansible_cmd}() { _ansible_install_hint ${_ansible_cmd}; }"
done
unset _ansible_cmd
