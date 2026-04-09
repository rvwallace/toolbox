#!/usr/bin/env bash

# #############################################################################
# vmrss.sh - Print the VmRSS of a process and its children
# Robert Wallace
#
# This script prints the VmRSS (resident set size) of a process and its children.
#
# Usage: vmrss.sh [options]
# Options:
#   --help, -h      Show this help message
#   show <PID>      List VMRSS info for a specific <PID>
#   list [-f <size_in_mb>]   List all running processes on the system and optionally filter by size using -f flag
#
# Example:
#   vmrss.sh show 12345
#       Show the VmRSS of the process with PID 12345 and its children
#   vmrss.sh list
#       List all running processes on the system.
# 		The VmRSS of each parent process and its children will be shown
#   vmrss.sh list -f 1000
#	   List all running parent processes on the system and their children
#      filtering out only those with a total VmRSS greater than 1000 MB
#   NO_COLOR=1 vmrss.sh list -f 1000
#      prefix the command with NO_COLOR=1 or set env variable to disable 
#      color output this is useful when the output is being piped to another 
#      command to avoid color codes being included in the output
#
# #############################################################################

if [ -z "$NO_COLOR" ]; then
	RED='\033[0;31m'
	GREEN='\033[0;32m'
	YELLOW='\033[0;33m'
	BLUE='\033[0;34m'
	NC='\033[0m'
else
	RED=''
	GREEN=''
	YELLOW=''
	BLUE=''
	NC=''

fi
grand_total=0

# Display usage information
function show_usage {
	echo "Usage: $(basename "$0") [options]"
	echo "Options:"
	echo -e "\t--help, -h\tShow this help message"
	echo -e "\tshow <pid>\tList VMRSS info for a specific PID"
	echo -e "\tlist [-f <size_in_mb>]\tList all running processes on the system and optionally filter by size using -f flag"
	echo
}

# Print the VmRSS for a given PID and its children
print_vmrss() {
	local pid="$1"
	local threshold=${2:-0}
	local indent=0
	local total=0
	local children
	local pids=("$pid")
	local output=""

	while [ ${#pids[@]} -gt 0 ]; do
		pid=${pids[0]}
		indent=${pids[1]}
		pids=("${pids[@]:2}") # Remove the first two elements
		indent_space=$(printf "%${indent}s")

		full_name=$(ps -p "$pid" -o comm=)
		name=${full_name##*/}
		[ -z "$name" ] && name="Unknown"
		padding_length_name=$((25 - ${#indent_space}))
		namepad=$(printf "%-${padding_length_name}.${padding_length_name}s" "$name")
		if [ ${#name} -gt $padding_length_name ]; then
			namepad="${namepad}..."
		else
			namepad="${namepad}   "
		fi
		pidpad=$(printf "%6s" "$pid")

		mem=$(ps -o rss= -p "$pid" | grep -o '[0-9]\+' | awk '{print $1/1024}')
		if [[ -z $mem ]]; then
			mempad=$(printf "%10s" "N/A")
			output+="${BLUE}${indent_space}${namepad}(${YELLOW}$pidpad${BLUE}): ${RED}$mempad MB${NC}\n"
		else
			total=$(echo "$total + $mem" | bc)
			formatted_mem=$(printf "%.2f" "$mem")
			mempad=$(printf "%10s" "$formatted_mem")
			output+="${BLUE}${indent_space}${namepad}(${YELLOW}$pidpad${BLUE}): ${GREEN}$mempad MB${NC}\n"
		fi

		children=$(pgrep -P "$pid")
		for child in $children; do
			pids+=("$child" $((indent + 2)))
		done
	done

	if (($(echo "$total > $threshold" | bc -l))); then
		printf "$output"
		formatted_total=$(printf "%.2f" "$total")
		totalpad=$(printf "%31s" "$formatted_total")
		printf "${GREEN}%51s\n" "------------"
		printf "${BLUE}  - Total VmRSS: ${GREEN}$totalpad MB${NC}\n\n"
		grand_total=$(echo "scale=2; $grand_total + $total" | bc)
	fi
}

# Parse command line arguments
parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
		--help | -h | help)
			show_usage
			exit 0
			;;
		show)
			if [[ ! "$2" =~ ^[0-9]+$ ]]; then
				printf "${RED}ERROR: Invalid PID: $2${NC}\n"
				exit 1
			fi
			show_pid=$2
			return
			;;
		list)
			list=true
			if [[ "$2" == "-f" && "$3" =~ ^[0-9]+$ ]]; then
				filter=$3
				shift 2
			elif [[ "$2" == "-f" ]]; then
				printf "${RED}ERROR: Invalid size: $3${NC}\n"
				exit 1
			fi
			return
			;;
		--no-color)
			NO_COLOR=true
			;;
		*)
			printf "${RED}ERROR: Invalid argument: $1${NC}\n"
			exit 1
			;;
		esac
		shift
	done
}

# Main function to execute the script
main() {

	parse_args "$@"

	if [ -n "$show_pid" ]; then
		print_vmrss "$show_pid" 0
		exit 0
	fi

	if [ -n "$list" ]; then
		local top_level_pids
		top_level_pids=$(ps -eo pid,ppid | awk '$2 == 1 {print $1}')

		for pid in $top_level_pids; do
			print_vmrss "$pid" "$filter"
		done
		formatted_grand_total=$(printf "%.2f" "$grand_total")
		printf "${BLUE}Grand Total VmRSS: ${GREEN}$formatted_grand_total MB${NC}\n"

		exit 0
	fi
}

main "$@"
