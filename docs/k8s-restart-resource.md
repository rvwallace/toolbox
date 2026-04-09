# k8s-restart-resource

Bash script that runs **`kubectl rollout restart`** on a **Deployment** or **DaemonSet**, waits for the rollout to finish (timeout 300 seconds), and validates the resource exists first.

**Source:** `scripts/k8s/k8s-restart-resource.sh`  
**After install:** `k8s-restart-resource` (symlink name follows `toolbox` rules)

## Usage

```text
k8s-restart-resource <resource_type> <namespace> <resource_name>
```

**Resource type** can be:

- `daemonset` or `ds`
- `deployment` or `deploy`

## Examples

```bash
k8s-restart-resource daemonset monitoring aws-for-fluent-bit
k8s-restart-resource deployment kube-system coredns
k8s-restart-resource ds kube-system node-exporter
k8s-restart-resource deploy default my-app
```

## Requirements

- `kubectl` configured for the right cluster
- `jq` for JSON handling
- `tr` (standard on Unix)
- RBAC on the namespace for `get` / `patch` / rollout status as needed

## Behavior

- Exits with an error if arguments are wrong, dependencies are missing, or the resource is not found.
- On success, prints a success log line; on failure, prints context (including current kubectl context when a kubectl command fails).

## Scenarios

- **Bounce a DaemonSet after config change:** pass `ds`, namespace, and name.
- **Rolling restart of an app Deployment:** pass `deploy`, namespace, and name.

Run `k8s-restart-resource` with no arguments to print the embedded usage from the script header.
