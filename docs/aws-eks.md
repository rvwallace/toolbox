# aws-eks

EKS helpers: list clusters, show cluster details, and write a **kubeconfig** file via `aws eks update-kubeconfig`.

**Source:** `scripts/aws/aws-eks.py`  
**After install:** `aws-eks`

## Global options

- `--profile` / `-p` (`AWS_PROFILE`)
- `--region` / `-r` (`AWS_REGION` or `AWS_DEFAULT_REGION`)

## Subcommands

### `list`

Lists clusters in the region, then `describe` each cluster for a short table (name, ARN, version, status).

### `describe`

Takes one cluster `name` argument.

- `--format` / `-f`: `table` (default), `json`, or `yaml`

### `kubeconfig`

Runs:

`aws eks update-kubeconfig --name <cluster> --kubeconfig ~/.kube/<file>`

- `--kubeconfig` / `-k`: name of the file under `~/.kube/` (default: same as cluster name)

The script sets `AWS_PROFILE` and `AWS_REGION` in the subprocess environment when you passed profile and region on the CLI.

After success, it prints a sample `kubectl --kubeconfig <path> get nodes`.

## Scenarios

- **Pick a cluster:** `aws-eks list`
- **Inspect one cluster as YAML:** `aws-eks describe my-cluster -f yaml`
- **Dedicated kubeconfig file:** `aws-eks kubeconfig my-cluster -k my-cluster-kubeconfig`

You need IAM permissions for `eks:ListClusters`, `eks:DescribeCluster`, and the permissions behind `aws eks update-kubeconfig` (same as the AWS CLI).
