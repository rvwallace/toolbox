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
