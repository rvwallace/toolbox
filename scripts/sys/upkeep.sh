#!/usr/bin/env bash
# toolbox-platforms: linux,darwin
#
# upkeep - CLI Tool & Package Manager
# Manage and update packages across Homebrew, uv, npm, Cargo, and Go.

set -euo pipefail

# Check required and optional dependencies
check_prereqs() {
  if ! command -v fzf &>/dev/null; then
    echo "Error: Missing required dependency: fzf" >&2
    echo "Please install fzf to use upkeep." >&2
    exit 1
  fi

  local active_managers=0
  for cmd in brew uv npm cargo go; do
    if command -v "${cmd}" &>/dev/null; then
      ((active_managers++)) || true
    fi
  done

  if [[ ${active_managers} -eq 0 ]]; then
    echo "Error: No supported package managers found in PATH (brew, uv, npm, cargo, go)." >&2
    exit 1
  fi

  # Optional helper tools for cargo and go
  if command -v cargo &>/dev/null; then
    if ! command -v cargo-install-update &>/dev/null && ! cargo install-update --help &>/dev/null 2>&1; then
      echo "[!] Notice: 'cargo-update' is missing (needed for Cargo tool updates)."
      if [[ -t 0 ]]; then
        local yn="n"
        read -r -p "    Install cargo-update now? [y/N] " yn || yn="n"
        [[ "${yn}" =~ ^[Yy]$ ]] && cargo install cargo-update
      else
        echo "    Install with: cargo install cargo-update"
      fi
    fi
  fi

  if command -v go &>/dev/null; then
    if ! command -v gup &>/dev/null; then
      echo "[!] Notice: 'gup' is missing (recommended for Go binary management)."
      if [[ -t 0 ]]; then
        local yn="n"
        read -r -p "    Install gup now? [y/N] " yn || yn="n"
        [[ "${yn}" =~ ^[Yy]$ ]] && go install github.com/nao1215/gup@latest
      else
        echo "    Install with: go install github.com/nao1215/gup@latest"
      fi
    fi
  fi
}

# List installed or outdated packages across available package managers ($1: "all" or "outdated")
list_packages() {
  local mode="${1:-all}" gp

  if [[ "${mode}" == "outdated" ]]; then
    if command -v brew &>/dev/null; then
      brew outdated -q 2>/dev/null | awk '{print "[brew] " $0}' || true
    fi
    if command -v uv &>/dev/null; then
      uv tool list --outdated 2>/dev/null | awk '/^[a-zA-Z0-9]/ {print "[uv] " $1}' || true
    fi
    if command -v npm &>/dev/null; then
      npm outdated --global --depth=0 --json 2>/dev/null |
        node -e 'let data=""; process.stdin.on("data", chunk => data += chunk).on("end", () => { try { for (const name of Object.keys(JSON.parse(data))) console.log("[npm] " + name); } catch (_) {} });' || true
    fi
    if command -v cargo &>/dev/null; then
      if command -v cargo-install-update &>/dev/null || cargo install-update --help &>/dev/null 2>&1; then
        cargo install-update -l 2>/dev/null | awk '$NF == "Yes" {print "[cargo] " $1}' || true
      fi
    fi
    if command -v go &>/dev/null; then
      if command -v gup &>/dev/null; then
        gup check 2>/dev/null | awk '/\$ gup update/ {print "[go] " $4}' || true
      fi
    fi
  else
    if command -v brew &>/dev/null; then
      brew leaves -r 2>/dev/null | awk '{print "[brew] " $0}' || true
    fi
    if command -v uv &>/dev/null; then
      uv tool list 2>/dev/null | awk '/^[a-zA-Z0-9]/ {print "[uv] " $1}' || true
    fi
    if command -v npm &>/dev/null; then
      npm list --global --depth=0 --json 2>/dev/null |
        node -e 'let data=""; process.stdin.on("data", chunk => data += chunk).on("end", () => { try { for (const name of Object.keys((JSON.parse(data).dependencies) || {})) console.log("[npm] " + name); } catch (_) {} });' || true
    fi
    if command -v cargo &>/dev/null; then
      cargo install --list 2>/dev/null | awk '/:$/ {sub(/:$/, ""); print "[cargo] " $1}' || true
    fi
    if command -v go &>/dev/null; then
      if command -v gup &>/dev/null; then
        gup list 2>/dev/null | awk 'NF {print "[go] " $1}' || true
      else
        gp="$(go env GOPATH 2>/dev/null || echo "${HOME}/go")"
        [[ -d "${gp}/bin" ]] && ls -1 "${gp}/bin" 2>/dev/null | awk '{print "[go] " $0}' || true
      fi
    fi
  fi
}

# Update all packages across all available package managers
update_all() {
  local updated=0 npm_before npm_after npm_changes

  if command -v brew &>/dev/null; then
    echo "==> [brew] Updating Homebrew packages..."
    brew upgrade || true
    updated=1
  fi

  if command -v uv &>/dev/null; then
    [[ ${updated} -eq 1 ]] && echo ""
    echo "==> [uv] Updating uv tools..."
    uv tool upgrade --all || true
    updated=1
  fi

  if command -v npm &>/dev/null; then
    [[ ${updated} -eq 1 ]] && echo ""
    echo "==> [npm] Updating global packages..."
    npm_before="$(npm outdated --global --depth=0 --json 2>/dev/null || true)"
    npm update --global || true
    npm_after="$(npm outdated --global --depth=0 --json 2>/dev/null || true)"
    npm_changes="$(node -e 'const before = JSON.parse(process.argv[1] || "{}"); const after = JSON.parse(process.argv[2] || "{}"); for (const name of Object.keys(before)) { const oldVersion = before[name].current || "unknown"; const newVersion = after[name]?.current; if (newVersion !== oldVersion) console.log(name + ": " + oldVersion + " -> " + (newVersion || "no longer outdated")); }' "${npm_before}" "${npm_after}")"
    if [[ -n "${npm_changes}" ]]; then
      echo "Updated npm packages:"
      while IFS= read -r npm_change; do
        echo "  ${npm_change}"
      done <<< "${npm_changes}"
    else
      echo "No npm packages changed."
    fi
    updated=1
  fi

  if command -v cargo &>/dev/null; then
    [[ ${updated} -eq 1 ]] && echo ""
    echo "==> [cargo] Updating Cargo packages..."
    if command -v cargo-install-update &>/dev/null || cargo install-update --help &>/dev/null 2>&1; then
      cargo install-update -a || true
    else
      echo "cargo-update missing. Run: cargo install cargo-update"
    fi
    updated=1
  fi

  if command -v go &>/dev/null; then
    [[ ${updated} -eq 1 ]] && echo ""
    echo "==> [go] Updating Go binaries..."
    if command -v gup &>/dev/null; then
      gup update || true
    else
      echo "gup missing. Run: go install github.com/nao1215/gup@latest"
    fi
    updated=1
  fi

  echo -e "\n[✓] Finished updating packages."
}

# Select and remove installed packages with an interactive menu
browse_remove() {
  local packages selected confirm="n" item mgr pkg gp
  packages="$(list_packages all)"
  if [[ -z "${packages}" ]]; then
    echo "No installed packages found."
    return 0
  fi

  selected="$(echo "${packages}" | fzf -m --header "TAB to select, ENTER to uninstall" --prompt "Remove > " --height 40% --reverse || true)"
  [[ -z "${selected}" ]] && { echo "No packages selected."; return 0; }
  echo -e "\nSelected packages for uninstallation:\n${selected}\n"
  if [[ -t 0 ]]; then
    read -r -p "Confirm removal? [y/N] " confirm || confirm="n"
  else
    read -r -p "Confirm removal? [y/N] " confirm </dev/tty 2>/dev/null || confirm="n"
  fi
  [[ ! "${confirm}" =~ ^[Yy]$ ]] && { echo "Cancelled."; return 0; }

  while IFS= read -r item; do
    [[ -z "${item}" ]] && continue
    mgr="${item%%]*}"
    mgr="${mgr#\[}"
    pkg="${item#*] }"
    echo "--> Uninstalling [${mgr}] ${pkg}..."
    case "${mgr}" in
      brew)  brew uninstall "${pkg}" ;;
      uv)    uv tool uninstall "${pkg}" ;;
      npm)   npm uninstall --global "${pkg}" ;;
      cargo) cargo uninstall "${pkg}" ;;
      go)
        if command -v gup &>/dev/null; then
          gup remove "${pkg}"
        else
          gp="$(go env GOPATH 2>/dev/null || echo "${HOME}/go")"
          rm -f "${gp}/bin/${pkg}" && echo "Removed ${gp}/bin/${pkg}"
        fi
        ;;
    esac
  done <<< "${selected}"
  echo -e "\n[✓] Removal complete."
}

# Select and update outdated packages with an interactive menu
interactive_update() {
  echo "Checking for outdated packages..."
  local outdated selected item mgr pkg
  outdated="$(list_packages outdated)"
  [[ -z "${outdated}" ]] && { echo -e "[✓] All packages are up to date!"; return 0; }
  selected="$(echo "${outdated}" | fzf -m --header "TAB to select, ENTER to update" --prompt "Update > " --height 40% --reverse || true)"
  [[ -z "${selected}" ]] && { echo "No packages selected."; return 0; }

  while IFS= read -r item; do
    [[ -z "${item}" ]] && continue
    mgr="${item%%]*}"
    mgr="${mgr#\[}"
    pkg="${item#*] }"
    echo "--> Updating [${mgr}] ${pkg}..."
    case "${mgr}" in
      brew)  brew upgrade "${pkg}" ;;
      uv)    uv tool upgrade "${pkg}" ;;
      npm)   npm update --global "${pkg}" ;;
      cargo)
        if command -v cargo-install-update &>/dev/null || cargo install-update --help &>/dev/null 2>&1; then
          cargo install-update "${pkg}"
        else
          cargo install "${pkg}"
        fi
        ;;
      go)
        if command -v gup &>/dev/null; then
          gup update "${pkg}"
        else
          echo "gup needed to update Go binaries: go install github.com/nao1215/gup@latest"
        fi
        ;;
    esac
  done <<< "${selected}"
  echo -e "\n[✓] Update complete."
}

# Show help usage
show_help() {
  cat <<EOF
Usage: upkeep [OPTIONS]

Interactive CLI tool & package manager for Homebrew, uv, npm, Cargo, and Go.

Options:
  -a, --all        Update all packages across all detected package managers
  -r, --remove     Browse and remove installed packages interactively
  -u, --update     Check for and interactively update outdated packages
  -h, --help       Show this help message

Controls (interactive menu):
  TAB              Select or deselect one or more items
  ENTER            Confirm the selection
  ESC / Ctrl+C     Cancel the operation
EOF
}

# Parse command-line arguments or open the interactive menu
main() {
  check_prereqs
  local mode="${1:-}"

  case "${mode}" in
    -h|--help)
      show_help
      exit 0
      ;;
    -a|--all|*"Update All"*)
      update_all
      ;;
    -r|--remove|*"Browse / Remove"*)
      browse_remove
      ;;
    -u|--update|*"Interactive Update"*)
      interactive_update
      ;;
    "")
      mode="$(printf '%s\n' "1. Update All" "2. Browse / Remove" "3. Interactive Update" | \
        fzf --prompt="Select Mode > " --height=8 --reverse || true)"
      case "${mode}" in
        *"Update All"*)        update_all ;;
        *"Browse / Remove"*)    browse_remove ;;
        *"Interactive Update"*) interactive_update ;;
        *)                      echo "Operation cancelled." ;;
      esac
      ;;
    *)
      echo "Unknown option: ${mode}" >&2
      show_help >&2
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
