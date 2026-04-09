# k8s-hpa-analyzer

Inspect **HorizontalPodAutoscaler** objects: scaling metrics, conditions, and related events. Uses the Kubernetes Python client (`kubeconfig` or in-cluster config).

**Source:** `scripts/k8s/k8s-hpa-analyzer.py`  
**After install:** `k8s-hpa-analyzer`

## Options

| Flag | Meaning |
|------|---------|
| `-n` / `--namespace` | Limit work to one namespace (also used when resolving a short HPA name) |
| `-a` / `--all-hpas` | Analyze every HPA in scope without prompting |
| `--hpa` | One HPA as `namespace/name` or just `name` (see below) |
| `--no-cli-pager` | Print full output to stdout instead of piping through a pager |

Do **not** pass both `--hpa` and `--all-hpas`.

## How to specify an HPA

- **`namespace/name`:** always unambiguous.
- **`name` only:** if you also set `--namespace`, that namespace is used. If you set neither namespace nor a unique name, the tool may search the cluster or prompt (interactive fuzzy picker) depending on how many matches exist.

If the name matches a namespace but not an HPA name, the tool prints a hint to use `--namespace` or `namespace/name`.

## Output

For each selected HPA you get Rich panels such as:

- Scaling configuration (min/max replicas, references)
- Metric status and current values where available
- Conditions (AbleToScale, ScalingActive, etc.)
- Events related to the HPA

Use `--no-cli-pager` when you want to capture everything in a file or CI log.

## Scenarios

- **One HPA in a known namespace:** `k8s-hpa-analyzer -n prod --hpa api-gateway`
- **Explicit:** `k8s-hpa-analyzer --hpa prod/api-gateway`
- **Scan cluster:** `k8s-hpa-analyzer --all-hpas` (can be heavy on large clusters)

RBAC: your kube user or service account needs `get`, `list`, and `watch` (as required by the client) on HPAs and read access to events in the namespaces you touch.
