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

### `describe`

One instance by **instance id** (`i-...`) or by **Name tag substring** (substring match). If multiple names match, the command prints a short table and exits with an error; refine the name or pass an instance id.

- `--format` / `-f`: `table` (default), `json`, or `yaml`

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
- **Dump JSON for automation:** `aws-ec2 describe i-0123456789abcdef0 -f json`
- **SSH prep:** `aws-ec2 find-key i-0123456789abcdef0` or `aws-ec2 find-key my-hostname --keys-dir ~/keys`

IAM calls use standard EC2 describe APIs; your IAM user or role needs matching permissions.
