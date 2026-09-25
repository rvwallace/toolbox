# AWS shell helpers for Nushell

def aws_env_commands [] {
    [
        { value: "set", description: "Select AWS profile and region interactively" }
        { value: "profile", description: "Select AWS profile only" }
        { value: "region", description: "Select AWS region only" }
        { value: "show", description: "Display current AWS environment" }
        { value: "token-status", description: "Check AWS token expiration" }
        { value: "clear", description: "Clear all AWS environment variables" }
    ]
}

# AWS environment switcher
export def --env "aws.env" [
    cmd: string@aws_env_commands = "set"
    ...args: string
] {
    if (which aws-env | is-empty) {
        print -e "aws.env: aws-env command not found"
        return 1
    }

    match $cmd {
        "set" | "profile" | "region" => {
            let out = (aws-env $cmd ...$args | lines)
            if ($out | is-empty) { return }

            let env_vars = (
                $out
                | parse "export {key}={val}"
                | update val { str trim -c '"' }
                | transpose -r -d
            )
            load-env $env_vars
        }
        "show" | "token-status" => {
            aws-env $cmd ...$args
        }
        "clear" => {
            hide-env -i AWS_PROFILE AWS_REGION AWS_DEFAULT_REGION AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
            print "AWS env cleared"
        }
        _ => {
            aws-env --help
        }
    }
}

# Get AWS caller identity as structured record
export def "aws.caller_identity" [] {
    if (which aws | is-empty) {
        print -e "aws CLI not found"
        return 1
    }
    aws sts get-caller-identity --output json | from json
}

# Query EC2 instances as structured data
export def "aws.ec2" [
    filter?: string              # Substring match on Name tag or exact Instance ID (i-xxxx)
    --name (-n): string          # Substring match on Name tag
    --state (-s): string         # Filter by state (running, stopped, pending, etc.)
    --profile (-p): string       # AWS profile name (overrides $env.AWS_PROFILE)
    --region (-r): string        # AWS region (overrides $env.AWS_REGION)
    --raw                        # Return raw AWS JSON records instead of formatted table
] {
    if (which aws | is-empty) {
        print -e "aws.ec2: aws CLI not found"
        return 1
    }

    let profile_args = (if ($profile | is-not-empty) { ["--profile", $profile] } else { [] })
    let region_args = (if ($region | is-not-empty) { ["--region", $region] } else { [] })

    # Build server-side AWS CLI filters if specified
    mut cli_filters = []
    if ($name | is-not-empty) {
        $cli_filters = ($cli_filters | append [$"Name=tag:Name,Values=*($name)*"])
    }
    if ($state | is-not-empty) {
        $cli_filters = ($cli_filters | append [$"Name=instance-state-name,Values=($state)"])
    }

    let filter_args = (if ($cli_filters | is-not-empty) {
        ["--filters", ...$cli_filters]
    } else {
        []
    })

    let res = (do -i {
        ^aws ec2 describe-instances --output json ...$profile_args ...$region_args ...$filter_args
    } | complete)

    if $res.exit_code != 0 {
        print -e $"aws.ec2: ($res.stderr | str trim)"
        return
    }

    let raw_data = ($res.stdout | from json)
    let instances = ($raw_data.Reservations?.Instances? | default [] | flatten)

    if ($instances | is-empty) {
        return []
    }

    if $raw {
        return $instances
    }

    let mapped = ($instances | each { |inst|
        let tag_rec = (if ($inst.Tags? | is-empty) { {} } else {
            $inst.Tags | select Key Value | transpose -r -d
        })
        {
            name: ($tag_rec.Name? | default "")
            id: $inst.InstanceId
            state: ($inst.State?.Name? | default "unknown")
            type: ($inst.InstanceType? | default "")
            os: ($inst.PlatformDetails? | default ($inst.Platform? | default "Linux/UNIX"))
            key: ($inst.KeyName? | default "")
            public_ip: ($inst.PublicIpAddress? | default "")
            private_ip: ($inst.PrivateIpAddress? | default "")
            launch_time: ($inst.LaunchTime? | default "")
            tags: $tag_rec
        }
    })

    # If a positional filter was given (e.g. `aws.ec2 my-host` or `aws.ec2 i-12345`):
    if ($filter | is-not-empty) {
        if ($filter =~ '^i-[0-9a-fA-F]+$') {
            $mapped | where id == $filter
        } else {
            $mapped | where { |row|
                (($row.name | str lowercase | str contains ($filter | str lowercase)) or ($row.id | str contains $filter))
            }
        }
    } else {
        $mapped
    }
}

# Locate local SSH private key file for an EC2 instance
export def "aws.ec2-key" [
    identifier: string           # Instance ID (i-xxxx) or Name tag substring
    --keys-dir (-d): path        # Directory containing private keys (defaults to $env.AWS_EC2_KEY_DIR)
    --profile (-p): string       # AWS profile
    --region (-r): string        # AWS region
] {
    let key_dir = (if ($keys_dir | is-not-empty) {
        $keys_dir
    } else if ($env.AWS_EC2_KEY_DIR? | is-not-empty) {
        $env.AWS_EC2_KEY_DIR
    } else {
        print -e "aws.ec2-key: set $env.AWS_EC2_KEY_DIR or provide --keys-dir"
        return 1
    })

    if not ($key_dir | path exists) {
        print -e $"aws.ec2-key: key directory '($key_dir)' does not exist"
        return 1
    }

    # Find the instance to get its KeyName
    let matches = (aws.ec2 $identifier --profile $profile --region $region)
    if ($matches | is-empty) {
        print -e $"aws.ec2-key: no instance found matching '($identifier)'"
        return 1
    }

    let key_name = ($matches.0.key? | default "")
    if ($key_name | is-empty) {
        print -e $"aws.ec2-key: instance '($matches.0.id)' does not have a KeyName assigned"
        return 1
    }

    let search_patterns = [
        $key_name,
        $"($key_name).pem",
        $"($key_name).key",
        ($key_name | str lowercase),
        $"($key_name | str lowercase).pem",
        $"($key_name | str lowercase).key",
    ]

    let found_file = (
        glob $"($key_dir)/**/*"
        | where { |f| ($f | path basename) in $search_patterns }
        | get 0?
    )

    if ($found_file | is-empty) {
        print -e $"aws.ec2-key: key file for '($key_name)' not found in ($key_dir)"
        return 1
    }

    $found_file
}

# Alias for compatibility with aws-ec2 naming
export alias "aws-ec2-nu" = aws.ec2
