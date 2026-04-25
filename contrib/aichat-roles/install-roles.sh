#!/usr/bin/env bash
# Install toolbox aichat role files into aichat's roles directory.
# Default: symlink (edit in-repo files, aichat picks up changes).
# Usage: ./install-roles.sh [--copy] [--dry-run] [-f|--force]
set -euo pipefail

usage() {
	cat <<'EOF' >&2
Usage: install-roles.sh [--copy] [--dry-run] [-f|--force]

  Symlink toolbox role .md files into aichat's roles_dir (from aichat --info).
  --copy     copy files instead of symlinking
  --dry-run  print roles_dir and planned paths only
  -f         replace existing files/symlinks

If aichat --info is slow or unavailable, set AICHAT_ROLES_DIR to your roles directory.
EOF
	exit "${1:-0}"
}

MODE=symlink
DRY_RUN=0
FORCE=0
while (($# > 0)); do
	case "$1" in
		-h | --help) usage 0 ;;
		--copy) MODE=copy ;;
		--dry-run) DRY_RUN=1 ;;
		-f | --force) FORCE=1 ;;
		*) usage 1 ;;
	esac
	shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_aichat_roles_dir() {
	if [[ -n "${AICHAT_ROLES_DIR:-}" ]]; then
		printf '%s' "${AICHAT_ROLES_DIR%/}"
		return 0
	fi
	if ! command -v aichat &>/dev/null; then
		echo "install-roles: aichat not found in PATH (set AICHAT_ROLES_DIR to skip)" >&2
		return 1
	fi
	local line
	line="$(aichat --info 2>/dev/null | sed -n 's/^roles_dir[[:space:]]*//p' | head -n1 || true)"
	line="${line%"${line##*[![:space:]]}"}"
	if [[ -z "$line" ]]; then
		echo "install-roles: could not parse roles_dir from 'aichat --info'" >&2
		echo "install-roles: export AICHAT_ROLES_DIR=/path/to/aichat/roles and retry" >&2
		return 1
	fi
	printf '%s' "$line"
}

ROLES_DIR="$(_aichat_roles_dir)" || exit 1

ROLE_FILES=(review.md explain-review.md ask.md)
missing=()
for f in "${ROLE_FILES[@]}"; do
	[[ -f "$SCRIPT_DIR/$f" ]] || missing+=("$f")
done
((${#missing[@]} == 0)) || {
	echo "install-roles: missing source file(s): ${missing[*]}" >&2
	exit 1
}

if ((DRY_RUN)); then
	echo "Would use roles_dir: $ROLES_DIR"
	echo "Mode: $MODE"
	for f in "${ROLE_FILES[@]}"; do
		echo "  -> $ROLES_DIR/$f"
	done
	exit 0
fi

mkdir -p "$ROLES_DIR"

install_one() {
	local name="$1"
	local src="$SCRIPT_DIR/$name"
	local dest="$ROLES_DIR/$name"
	local src_abs
	src_abs="$(cd "$(dirname "$src")" && pwd)/$(basename "$src")"

	if [[ -e "$dest" || -L "$dest" ]]; then
		if ((FORCE)); then
			rm -f "$dest"
		else
			if [[ "$MODE" == symlink && -L "$dest" ]]; then
				local cur
				cur="$(readlink "$dest" || true)"
				if [[ "$cur" == "$src_abs" ]]; then
					echo "OK (already linked): $dest"
					return 0
				fi
			fi
			echo "install-roles: exists (use -f to replace): $dest" >&2
			return 1
		fi
	fi

	if [[ "$MODE" == copy ]]; then
		cp -a "$src_abs" "$dest"
		echo "Copied: $dest"
	else
		ln -s "$src_abs" "$dest"
		echo "Linked: $dest -> $src_abs"
	fi
}

for f in "${ROLE_FILES[@]}"; do
	install_one "$f"
done

echo "Done. Check with: aichat --list-roles"
