# ssm-parameter

Select and read an **AWS Systems Manager Parameter Store** parameter value with interactive `fzf` search or direct lookup by name. Decrypts `SecureString` values automatically.

**Source:** `scripts/aws/ssm-parameter.sh`
**After install:** `ssm-parameter`

## Requirements

- **AWS CLI** (`aws ssm describe-parameters`, `aws ssm get-parameter`)
- **fzf** (for interactive selection mode; optional when passing `-n` / `--name`)
- IAM permissions: `ssm:DescribeParameters` to list parameter names and `ssm:GetParameter` with decryption access (`kms:Decrypt` for KMS keys used by SecureString parameters)

## Configuration and Cache

- **Cache location:** `$XDG_CACHE_HOME/silentcastle/ssm-parameter/` (defaults to `~/.cache/silentcastle/ssm-parameter/`)
- Caches parameter names per profile and region (`ssm-parameters-<profile>-<region>.txt`)
- **Note:** The cache contains parameter **names only**, never parameter values or secrets.

## CLI Usage

```bash
ssm-parameter [OPTIONS] [PROFILE] [REGION]
```

### Options

| Flag | Meaning |
|------|---------|
| `-n`, `--name PARAMETER` | Read specified parameter directly without interactive `fzf` |
| `-q`, `--quiet` | Print only the decrypted parameter value (suitable for shell scripts / pipes) |
| `-r`, `--refresh` | Force download of an updated parameter-name list from AWS |
| `--show-cache` | Display the active cache directory and exit |
| `--clear-cache` | Delete all cached parameter-name lists and exit |
| `-h`, `--help` | Show usage help |

### Positional Arguments & Defaults

- `PROFILE`: AWS CLI profile to use (defaults to `$AWS_PROFILE`, or `default` if unset)
- `REGION`: AWS region (defaults to `$AWS_REGION`, `$AWS_DEFAULT_REGION`, or configured profile region)

## Examples

Interactive fuzzy search with `fzf`:

```bash
ssm-parameter example-profile us-east-1
```

Download a fresh list of parameter names before launching `fzf`:

```bash
ssm-parameter --refresh example-profile us-east-1
```

Read a parameter by name directly (no fzf):

```bash
ssm-parameter --name /example/application/password example-profile us-east-1
```

Capture parameter secret value in a script or pipeline:

```bash
db_pass=$(ssm-parameter -q -n /example/application/password example-profile us-east-1)
```

Copy a secret parameter to the clipboard:

```bash
ssm-parameter -q -n /example/application/api-key example-profile us-east-1 | pbcopy
```

Show or clear cache:

```bash
ssm-parameter --show-cache
ssm-parameter --clear-cache
```

## Security Note

The tool prints secret values to `stdout`. Do not redirect output to persistent logs or commit captured values to source control.
