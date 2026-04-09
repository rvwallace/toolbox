#!/usr/bin/env bash

#/ Script to restart a Kubernetes daemonset or deployment by performing a rolling restart
#/
#/ Usage: k8s_restart_resource.sh <resource_type> <namespace> <resource_name>
#/
#/ Arguments:
#/   <resource_type>   The type of resource to restart (daemonset or deployment)
#/   <namespace>       The Kubernetes namespace containing the resource
#/   <resource_name>   The name of the resource to restart
#/
#/ Examples:
#/   k8s_restart_resource.sh daemonset monitoring aws-for-fluent-bit
#/   k8s_restart_resource.sh deployment kube-system coredns
#/   k8s_restart_resource.sh ds kube-system node-exporter
#/   k8s_restart_resource.sh deploy default my-app
#/
#/ Description:
#/   This script performs a rolling restart of a Kubernetes daemonset or deployment using
#/   'kubectl rollout restart'. It includes validation to ensure the resource
#/   exists before attempting the restart and waits for the rollout to complete
#/   with a 300-second timeout.
#/
#/ Prerequisites:
#/   - kubectl must be installed and configured
#/   - jq must be installed for JSON parsing
#/   - tr must be installed for string manipulation
#/   - User must have appropriate RBAC permissions for the target namespace
#/
#/ Exit Codes:
#/   0 - Success
#/   1 - Error (invalid arguments, missing kubectl, resource not found, or restart failed)
#/
#/ Author: Robert Wallace

set -o pipefail
set -o nounset
set -o errexit

log() {
	if [[ -t 2 ]]; then
		local red='\033[31m'
		local green='\033[32m'
		local yellow='\033[33m'
		local blue='\033[34m'
		local nc='\033[0m'
	else
		local red='' green='' yellow='' blue='' nc=''
	fi

	local level
	level=$(echo "$1" | tr '[:lower:]' '[:upper:]')
	shift

	case "$level" in
	ERROR)
		printf "${red}[ERROR  ]${nc} %s\n" "$@" >&2
		;;
	WARN)
		printf "${yellow}[WARN   ]${nc} %s\n" "$@" >&2
		;;
	SUCCESS)
		printf "${green}[SUCCESS]${nc} %s\n" "$@"
		;;
	INFO)
		printf "${blue}[INFO   ]${nc} %s\n" "$@"
		;;
	*)
		printf "%s\n" "$level $*"
		;;
	esac
}

cleanup() {
	local exit_code=$?
	if (( exit_code != 0 )); then
		log ERROR "Script terminated with errors. Cleaning up..."
		log ERROR "Exiting with status code ${exit_code}"
	else
		log INFO "Script completed successfully."
	fi
}

error_handler() {
	local exit_code=$?
	local line_number=$1
	local command="${BASH_COMMAND:-<unknown command>}"
	log ERROR "Error in command: '${command}' at line ${line_number} with exit code ${exit_code}"

	if [[ "$command" == *"kubectl"* ]]; then
		local context=$(kubectl config current-context 2>/dev/null || echo "unknown")
		log ERROR "Current Kubernetes context: $context"
	fi

	exit 1
}

# Set up signal handlers
trap cleanup EXIT
trap 'error_handler ${LINENO}' ERR

usage() {
	grep '^#/' <"$0" | cut -c 4-
	exit 1
}

check_dependencies() {
	local -a missing_deps=()
	local dep
	for dep in "$@"; do
		if ! command -v "$dep" >/dev/null 2>&1; then
			missing_deps+=("$dep")
		fi
	done

	if (( ${#missing_deps[@]} != 0 )); then
		if command -v log >/dev/null 2>&1; then
			log ERROR "Missing dependencies: ${missing_deps[*]}"
		else
			printf 'Missing dependencies: %s\n' "${missing_deps[*]}" >&2
		fi
		return 1
	fi
}

check_resource_exists() {
	local resource_type="$1"
	local namespace="$2"
	local resource_name="$3"

	if ! kubectl get "$resource_type" "$resource_name" -n "$namespace" &>/dev/null; then
		log ERROR "$resource_type '$resource_name' not found in namespace '$namespace'"
		exit 1
	fi
}

log_resource_info() {
	local resource_type="$1"
	local namespace="$2"
	local resource_name="$3"

	log INFO "Resource type: $resource_type"
	log INFO "Namespace: $namespace"
	log INFO "Resource name: $resource_name"

	# Fetch all needed fields in a single kubectl call
	local status_json
	status_json=$(kubectl get "$resource_type" "$resource_name" -n "$namespace" -o json)

	local replicas available updated ready
	replicas=$(echo "$status_json" | jq -r '.status.replicas // "N/A"')
	available=$(echo "$status_json" | jq -r '.status.availableReplicas // "N/A"')
	updated=$(echo "$status_json" | jq -r '.status.updatedReplicas // "N/A"')
	ready=$(echo "$status_json" | jq -r '.status.readyReplicas // "N/A"')

	log INFO "Current status of $resource_type '$resource_name':"
	log INFO "  Replicas: $replicas"
	log INFO "  Available: $available"
	log INFO "  Updated: $updated"
	log INFO "  Ready: $ready"
}

restart_resource() {
	local resource_type="$1"
	local namespace="$2"
	local resource_name="$3"

	log INFO "Capturing current state before restart..."
	log_resource_info "$resource_type" "$namespace" "$resource_name"
	log INFO "Restarting $resource_type '$resource_name' in namespace '$namespace'..."

	if kubectl rollout restart "$resource_type" "$resource_name" -n "$namespace"; then
		log INFO "Successfully initiated restart of $resource_type '$resource_name'"
		log INFO "Waiting for rollout to complete (timeout=300s)..."

		if kubectl rollout status "$resource_type" "$resource_name" -n "$namespace" --timeout=300s; then
			log SUCCESS "$resource_type '$resource_name' successfully restarted and rolled out"
			log INFO "Post-restart status:"
			log_resource_info "$resource_type" "$namespace" "$resource_name"
		else
			log WARN "Timeout waiting for rollout to complete. Check status manually with:"
			log WARN "kubectl rollout status $resource_type $resource_name -n $namespace"
			log INFO "Current status after timeout:"
			log_resource_info "$resource_type" "$namespace" "$resource_name"
			exit 1
		fi
	else
		log ERROR "Failed to restart $resource_type '$resource_name'"
		log INFO "State when failure occurred:"
		log_resource_info "$resource_type" "$namespace" "$resource_name"
		exit 1
	fi
}

validate_resource_type() {
	local resource_type="$1"

	resource_type=$(echo "$resource_type" | tr '[:upper:]' '[:lower:]')

	case "$resource_type" in
	daemonset | ds)
		echo "daemonset"
		;;
	deployment | deploy)
		echo "deployment"
		;;
	*)
		log ERROR "Invalid resource type '$resource_type'. Supported types: daemonset (ds), deployment (deploy)"
		exit 1
		;;
	esac
}

main() {
	if [[ $# -ne 3 ]]; then
		log ERROR "Invalid number of arguments"
		usage
	fi

	check_dependencies "kubectl" "jq" "tr" || exit 1

	local resource_type="$1"
	local namespace="$2"
	local resource_name="$3"

	# Validate inputs
	if [[ -z "$resource_type" || -z "$namespace" || -z "$resource_name" ]]; then
		log ERROR "Resource type, namespace, and resource name cannot be empty"
		usage
	fi

	# Validate and normalize resource type
	resource_type=$(validate_resource_type "$resource_type")

	# Check if resource exists
	check_resource_exists "$resource_type" "$namespace" "$resource_name"

	# Restart the resource
	restart_resource "$resource_type" "$namespace" "$resource_name"
}

# Call main function with all arguments
main "$@"
