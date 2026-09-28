# aws-ec2

EC2 helpers: list instances, show details, and locate the **local SSH private key file** that matches an instance key pair name.

**Source:** `scripts/aws/aws-ec2.py`  
**After install:** `aws-ec2`

## Global options

All subcommands use:

- `--profile` / `-p` (`AWS_PROFILE`)
- `--region` / `-r` (`AWS_REGION` or `AWS_DEFAULT_REGION`)

Defaults come from your environment and boto3 resolution (see `resolve_profile` / `resolve_region` in the script).

## Subcommands

### `list`

Table of instances with Name, Id, State, Type, OS, Key, public and private IPs.

- `--name` / `-n`: substring on the **Name** tag (case-insensitive)
- `--state`: `instance-state-name` filter (e.g. `running`, `stopped`)
- `--json`: emit the canonical normalized JSON array described below

### `describe`

One instance by **instance id** (`i-...`) or by **Name tag substring** (substring match). If multiple names match, the command prints a short table and exits with an error; refine the name or pass an instance id.

- `--format` / `-f`: `table` (default), `json`, or `yaml`
- `--json`: emit one canonical normalized JSON object; this is distinct from
  the legacy provider-shaped `--format json` output

### `find-key`

Resolves the key pair name for an instance id or Name tag, then searches **`--keys-dir`** for a matching private key file (`.pem` or `.key`).

**Required:** set `AWS_EC2_KEY_DIR` to your key pair directory, or pass `--keys-dir` explicitly. The command exits with an error if neither is provided.

```bash
export AWS_EC2_KEY_DIR=~/aws-key-pairs   # add to ~/.zshrc.local.pre
```

- `--keys-dir` / `AWS_EC2_KEY_DIR`: directory to search for key files
- `--key-file-only`: print only the path when a file is found (useful for scripting)

## Scenarios

- **Inventory:** `aws-ec2 list --state running`
- **Structured inventory:** `aws-ec2 list --json`
- **Structured instance details:** `aws-ec2 describe i-0123456789abcdef0 --json`
- **Legacy provider-shaped dump:** `aws-ec2 describe i-0123456789abcdef0 -f json`
- **SSH prep:** `aws-ec2 find-key i-0123456789abcdef0` or `aws-ec2 find-key my-hostname --keys-dir ~/keys`

IAM calls use standard EC2 describe APIs; your IAM user or role needs matching permissions.

## Canonical JSON

`--json` writes exactly one normalized JSON value plus a trailing newline to
stdout. An empty list is `[]` and exits successfully. Diagnostics and provider
failures go to stderr without a JSON error object on stdout.

```json
{
  "instance_id": "i-0123456789abcdef0",
  "name": "web-01",
  "state": "running",
  "instance_type": "t3.small",
  "os": "Linux/UNIX",
  "architecture": "x86_64",
  "image_id": "ami-0123456789abcdef0",
  "availability_zone": "us-east-1a",
  "key_name": "prod-web",
  "iam_role": "WebInstanceRole",
  "private_ip": "10.0.12.34",
  "private_dns_name": "ip-10-0-12-34.ec2.internal",
  "public_ip": "203.0.113.42",
  "vpc_id": "vpc-0123456789abcdef0",
  "subnet_id": "subnet-0123456789abcdef0",
  "security_groups": [{"id": "sg-0123456789abcdef0", "name": "web"}],
  "launch_time": "2026-09-27T14:32:11Z",
  "tags": {"Name": "web-01", "Environment": "prod"}
}
```

The normalized output is intended for `jq`, Python, CI, and later Nushell
composition such as:

```nu
aws-ec2 list --json | from json
```

The existing `describe --format json` and `describe --format yaml` options are
preserved as legacy provider-shaped representations. They are not aliases for
the canonical `--json` mode.
