#!/usr/bin/env bash
# AI-related aliases

# claude-monitor via uv tool
if command -v claude &>/dev/null && command -v uv &>/dev/null; then
    claude.monitor() {
        uv tool run claude-monitor "$@"
    }
fi
