#!/usr/bin/env bash
# shellcheck shell=bash
# Bootstrap: build bin/toolbox, macOS Homebrew via generated Brewfile + brew bundle (with confirm),
# or auto-install via pacman/paru/apt/dnf on Linux (falls back to paste-line hints).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TOOLBOX_ROOT="$ROOT"
BIN="$ROOT/bin/toolbox"

ensure_toolbox_binary() {
	if ! command -v go &>/dev/null; then
		echo "bootstrap: Go is required to build bin/toolbox. Install Go and re-run." >&2
		exit 1
	fi
	mkdir -p "$ROOT/bin"
	( cd "$ROOT" && go build -o "$BIN" ./cmd/toolbox )
	echo "bootstrap: built $BIN"
}

preflight_darwin() {
	local missing=()
	command -v brew &>/dev/null || missing+=("brew (https://brew.sh)")
	command -v uv &>/dev/null || missing+=("uv (https://docs.astral.sh/uv/)")
	command -v go &>/dev/null || missing+=("go")
	command -v swift &>/dev/null || missing+=("swift (Xcode CLT)")
	command -v swiftc &>/dev/null || missing+=("swiftc (Xcode CLT)")
	if [[ ${#missing[@]} -gt 0 ]]; then
		echo "bootstrap: missing on PATH:" >&2
		printf '  - %s\n' "${missing[@]}" >&2
		exit 1
	fi
	if ! brew bundle -h &>/dev/null; then
		echo "bootstrap: 'brew bundle' not available. Try: brew tap Homebrew/bundle" >&2
		exit 1
	fi
}

preflight_linux() {
	local missing=()
	command -v uv &>/dev/null || missing+=("uv (https://docs.astral.sh/uv/)")
	command -v go &>/dev/null || missing+=("go")
	if [[ ${#missing[@]} -gt 0 ]]; then
		echo "bootstrap: missing on PATH:" >&2
		printf '  - %s\n' "${missing[@]}" >&2
		exit 1
	fi
}

# Generate a temp Brewfile from deps YAML (--only toolbox|tools), then optionally brew bundle install.
brew_bundle_batch() {
	local title=$1
	local only=$2
	local bf
	bf=$("$BIN" bootstrap brew-bundle --only="$only" --path-only)
	[[ -z "$bf" ]] && return 0
	if brew bundle check --file="$bf" &>/dev/null; then
		echo "bootstrap: $title — brew bundle check OK (nothing missing)."
		return 0
	fi
	echo "bootstrap: $title — generated Brewfile (not in repo):"
	echo "  $bf"
	echo
	echo "Example:"
	printf '  brew bundle install --file=%q\n' "$bf"
	echo
	read -r -p "Run brew bundle install now? [y/N] " ans || true
	case "$ans" in
		[yY]|[yY][eE][sS]) ;;
		*) echo "bootstrap: skipped $title (run the command above when ready)."; return 0 ;;
	esac
	brew bundle install --file="$bf"
}

# Install paru from AUR using makepkg. Requires base-devel and git.
install_paru() {
	echo "bootstrap: installing paru (AUR helper)..."
	sudo pacman -S --needed --noconfirm base-devel git
	local tmpdir
	tmpdir=$(mktemp -d)
	git clone https://aur.archlinux.org/paru.git "$tmpdir"
	( cd "$tmpdir" && makepkg -si --noconfirm )
	rm -rf "$tmpdir"
	echo "bootstrap: paru installed."
}

# On Arch, install paru if pacman is available but paru is not.
ensure_paru() {
	command -v paru &>/dev/null && return 0
	command -v pacman &>/dev/null || return 0
	echo "bootstrap: paru not found on Arch — installing via makepkg."
	install_paru
}

uv_tool_installs() {
	mkdir -p "$HOME/.local/bin"
	local tools=(rich-cli)
	for tool in "${tools[@]}"; do
		echo "bootstrap: uv tool install $tool"
		uv tool install "$tool"
	done
}

setup_lazyvim() {
	if ! command -v nvim &>/dev/null; then
		echo "bootstrap: nvim not found — skipping LazyVim setup."
		return 0
	fi
	if [[ -d "$HOME/.config/nvim" ]]; then
		echo "bootstrap: ~/.config/nvim already exists."
		read -r -p "Set up LazyVim? Existing config will be backed up to ~/.config/nvim.bak [y/N] " ans || true
		case "$ans" in
			[yY]|[yY][eE][sS]) ;;
			*) echo "bootstrap: skipped LazyVim setup."; return 0 ;;
		esac
		mv "$HOME/.config/nvim" "$HOME/.config/nvim.bak"
		[[ -d "$HOME/.local/share/nvim" ]] && mv "$HOME/.local/share/nvim" "$HOME/.local/share/nvim.bak"
		[[ -d "$HOME/.local/state/nvim" ]] && mv "$HOME/.local/state/nvim" "$HOME/.local/state/nvim.bak"
		[[ -d "$HOME/.cache/nvim" ]] && mv "$HOME/.cache/nvim" "$HOME/.cache/nvim.bak"
		echo "bootstrap: backed up existing nvim config."
	fi
	echo "bootstrap: cloning LazyVim starter..."
	git clone https://github.com/LazyVim/starter "$HOME/.config/nvim"
	rm -rf "$HOME/.config/nvim/.git"
	echo "bootstrap: LazyVim installed. Run 'nvim' to complete plugin setup."
}

darwin_bootstrap() {
	preflight_darwin
	ensure_toolbox_binary
	brew_bundle_batch "Toolbox prerequisites" toolbox
	brew_bundle_batch "Optional usual tools" tools
	uv_tool_installs
	setup_lazyvim
	echo "bootstrap: run './toolbox install' to symlink and build commands."
}

linux_bootstrap() {
	preflight_linux
	ensure_toolbox_binary
	ensure_paru
	echo
	"$BIN" bootstrap linux-install
	echo
	uv_tool_installs
	setup_lazyvim
	echo "bootstrap: run './toolbox install' to symlink and build commands."
}

main() {
	case "$(uname -s)" in
		Darwin) darwin_bootstrap ;;
		Linux) linux_bootstrap ;;
		*)
			echo "bootstrap: unsupported OS $(uname -s); run ensure_toolbox_binary manually." >&2
			ensure_toolbox_binary
			;;
	esac
}

main "$@"
