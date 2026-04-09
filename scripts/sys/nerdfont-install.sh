#!/usr/bin/env bash

# Formatting Colors
FMT_RED=$(printf '\033[31m')
FMT_GREEN=$(printf '\033[32m')
FMT_YELLOW=$(printf '\033[33m')

# Reset all formatting
FMT_RESET=$(printf '\033[0m')

# BFR is a carriage return and erase line escape sequence
BFR="\\r\\033[K"
HOLD="-"
CROSS="${FMT_RED}✘${FMT_RESET}"
TICK="${FMT_GREEN}✔${FMT_RESET}"

# Message functions
function status:info() {
    local message=$1
    echo -ne " ${FMT_YELLOW}${HOLD} ${message}..."
}

function status:update() {
    local message=$1
    echo -ne "${BFR} ${FMT_YELLOW}${HOLD} ${message}..."
}

function msg:success() {
    local message=$1
    echo -e "${BFR} ${FMT_GREEN} ${TICK} ${message}${FMT_RESET}"
}

function msg:error() {
    local message=$1
    echo -e "${BFR} ${FMT_RED} ${CROSS} ${message}${FMT_RESET}"
}

function check_dependencies() {
    local dependencies=("$@")
    for cmd in "${dependencies[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            msg:error "$cmd is not installed. Please install $cmd and try again."
            exit 1
        fi
    done
}

function macos() {
    check_dependencies "brew" "fzf"

    # Fetch list of available nerd fonts
    status:info "Fetching list of available nerd fonts..."
    fonts=$(brew search --casks nerd-font)
    if [ -z "$fonts" ]; then
        msg:error "No nerd fonts found. Exiting..."
        exit 1
    fi
    msg:success "Fetched list of available nerd fonts."

    # Prompt user to select a nerd font using fzf
    status:info "Select a nerd font to install:"
    selected_font=$(echo "$fonts" | fzf --height 20 --reverse --border --prompt "Select a nerd font > "\
        --preview="brew info --cask {}" --preview-window="right:60%:wrap")
    if [ -z "$selected_font" ]; then
        msg:error "No font selected. Exiting..."
        exit 1
    fi
    msg:success "Selected font: $selected_font"

    brew install --cask "$selected_font"
}

function fetch_fonts_from_nerd_fonts() {
    curl -s "https://api.github.com/repos/ryanoasis/nerd-fonts/contents/patched-fonts?ref=master" |
        grep "\"name\"" |
        sed -E 's/.*"name": "([^"]+)".*/\1/' |
        sort -u
}

function linux() {
    check_dependencies "curl" "unzip" "wget" "fzf"

    # Fetch list of available nerd fonts
    status:info "Fetching list of available nerd fonts..."
    fonts=$(fetch_fonts_from_nerd_fonts)
    if [ -z "$fonts" ]; then
        msg:error "No nerd fonts found. Exiting..."
        exit 1
    fi
    msg:success "Fetched list of available nerd fonts."

    # Prompt user to select a nerd font using fzf
    status:info "Select a nerd font to install:"
    selected_font=$(echo "$fonts" | fzf --height 20 --reverse --border --prompt "Select a nerd font > ")
    if [ -z "$selected_font" ]; then
        msg:error "No font selected. Exiting..."
        exit 1
    fi
    msg:success "Selected font: $selected_font"

    local install_dir="$HOME/.local/share/fonts"
    mkdir -p "$install_dir"

    status:info "Installing $selected_font\n"
    font_name="${selected_font// /-}" # Replace spaces with hyphens for URL
    wget -P "$install_dir" "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/$font_name.zip"

    if [ ! -f "$install_dir/$font_name.zip" ]; then
        msg:error "\nDownload failed. Exiting"
        exit 1
    fi

    unzip -o "$install_dir/$font_name.zip" -d "$install_dir"
    fc-cache -fv

    msg:success "\nInstalled $selected_font"
}

# Run the appropriate function based on the OS type
if [[ "$OSTYPE" == "darwin"* ]]; then
    macos
else
    linux
fi
