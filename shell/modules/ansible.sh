#!/usr/bin/env bash
# shellcheck shell=bash
# Ansible aliases using uv for isolated, reproducible environments

toolbox_require_commands uv uv || return 0

alias ansible='uv run --with ansible-core ansible'
alias ansible-playbook='uv run --with ansible-core ansible-playbook'
alias ansible-vault='uv run --with ansible-core ansible-vault'
alias ansible-galaxy='uv run --with ansible-core ansible-galaxy'
alias ansible-lint='uv run --with ansible-lint ansible-lint'
