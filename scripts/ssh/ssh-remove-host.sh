#!/usr/bin/env bash
#/
#/ DESCRIPTION
#/   Interactively remove SSH host entries from ~/.ssh/known_hosts
#/
#/   Uses fzf to select hosts and ssh-keygen -R to remove them.
#/   Creates a backup before making changes.
#/-
#/ USAGE
#/   ssh-remove-host.sh [OPTIONS]
#/-
#/ OPTIONS
#/   -h, --help      Show this help message
#/

set -o nounset
set -o pipefail

usage() {
    grep '^#/' <"$0" | cut -c 4-
}

log() {
    local level="$1"
    shift
    case "$level" in
        ERROR) echo "[ERROR] $*" >&2 ;;
        INFO)  echo "[INFO] $*" ;;
        *)     echo "$*" ;;
    esac
}

# Handle arguments
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

# Check dependencies
for cmd in fzf ssh-keygen awk; do
    if ! command -v "$cmd" &>/dev/null; then
        log ERROR "Missing required command: $cmd"
        exit 1
    fi
done

readonly known_hosts_file="${HOME}/.ssh/known_hosts"

if [[ ! -f "$known_hosts_file" ]]; then
    log INFO "No known_hosts file found. Nothing to do."
    exit 0
fi

if [[ ! -w "$known_hosts_file" ]]; then
    log ERROR "Cannot write to known_hosts file. Check permissions."
    exit 1
fi

# Generate host list for fzf
generate_host_list() {
    awk '
    {
        host = $1
        key_type = $2
        
        # Skip empty lines and comments
        if (host == "" || host ~ /^#/) next
        
        # Group key types by host
        if (!(host in hosts)) {
            order[++count] = host
        }
        hosts[host] = hosts[host] ? hosts[host] ", " key_type : key_type
    }
    END {
        for (i = 1; i <= count; i++) {
            h = order[i]
            print h " [" hosts[h] "]"
        }
    }' "$known_hosts_file"
}

host_list=$(generate_host_list)

if [[ -z "$host_list" ]]; then
    log INFO "No hosts found in known_hosts file."
    exit 0
fi

# Let user select hosts to remove
selections=$(echo "$host_list" | fzf \
    --multi \
    --height=60% \
    --border=rounded \
    --prompt="Select host(s) to remove > " \
    --header="Use TAB/Shift-TAB to multi-select. Enter to confirm." \
    --preview-window="right:50%:wrap" \
    --preview="host_key=\$(echo {} | awk '{print \$1}'); \
awk -v host=\"\${host_key}\" '\$1 == host' \"$known_hosts_file\"")

if [[ -z "$selections" ]]; then
    log INFO "No hosts selected. Aborting."
    exit 0
fi

# Create backup
backup_file="${known_hosts_file}.bak.$(date +%Y%m%d-%H%M%S)"
cp "$known_hosts_file" "$backup_file"
log INFO "Backed up known_hosts to $(basename "$backup_file")"

# Clean up old backups (keep 5 most recent)
backup_dir="$(dirname "$known_hosts_file")"
backup_pattern="$(basename "$known_hosts_file").bak.*"

# Find and remove old backup files, keeping only the 5 most recent
find "$backup_dir" -maxdepth 1 -name "$backup_pattern" -type f -print0 2>/dev/null | \
    xargs -0r ls -t | \
    tail -n +6 | \
    xargs -r rm -f

log INFO "Cleaned up old backups (keeping 5 most recent)"

# Remove hosts using ssh-keygen -R
removed_count=0
failed_count=0

# Process selections line by line using a temp file approach
echo "$selections" > /tmp/ssh_selections.$$

while IFS= read -r line; do
    host=$(echo "$line" | awk '{print $1}')
    # log INFO "Removing host: $host"
    
    # Remove any existing .old file that might conflict  
    rm -f "${known_hosts_file}.old"
    
    # Remove the host
    ssh-keygen -R "$host" -f "$known_hosts_file" >/dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        ((removed_count++))
        log INFO "Successfully removed: $host"
    else
        log ERROR "Failed to remove host: $host"
        ((failed_count++))
    fi
    
done < /tmp/ssh_selections.$$

# Cleanup temp file
rm -f /tmp/ssh_selections.$$

# Report results
if [[ $removed_count -gt 0 ]]; then
    log INFO "Successfully removed $removed_count host(s)"
fi

if [[ $failed_count -gt 0 ]]; then
    log ERROR "$failed_count host(s) failed to remove"
    exit 1
fi

log INFO "Done"