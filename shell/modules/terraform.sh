#!/usr/bin/env bash
# shellcheck shell=bash
# Terraform shell module: defaults, MR plan archive helpers, aliases.
# tf.amd64 (end of file) is a special-case linux/amd64 runner on Apple Silicon only.

toolbox_require_commands terraform terraform || return 0

: "${TF_PLANS_DIR:=$HOME/silentcastle/tf-plans}"
: "${TF_PLAN_NO_COLOR:=1}"
: "${TF_PLAN_KEEP_ON_APPLY_ABORT:=1}"
export TF_PLANS_DIR TF_PLAN_NO_COLOR TF_PLAN_KEEP_ON_APPLY_ABORT

_tf_ticket_resolve() {
    if [[ -n "${TICKET:-}" ]]; then
        return 0
    fi
    printf 'Ticket (e.g. TCM-1060): ' >&2
    read -r TICKET
    if [[ -z "${TICKET:-}" ]]; then
        printf 'tf: TICKET is required (set TICKET or enter at prompt)\n' >&2
        return 1
    fi
    export TICKET
}

_tf_root_resolve() {
    local root="${TF_ROOT:-$PWD}"

    root="$(cd "$root" && pwd)" || {
        printf 'tf: cannot access TF_ROOT %s\n' "${TF_ROOT:-$PWD}" >&2
        return 1
    }

    if [[ ! -f "$root/versions.tf" && ! -f "$root/terraform.tfstate" && ! -d "$root/.terraform" ]]; then
        printf 'tf: not a Terraform root (need versions.tf, terraform.tfstate, or .terraform/)\n' >&2
        printf 'tf: cwd=%s\n' "$root" >&2
        return 1
    fi

    TF_ROOT="$root"
    cd "$TF_ROOT" || return 1
}

_tf_timestamp() {
    date +%Y%m%d-%H%M%S
}

_tf_paths_build() {
    local ticket="$1"
    local stamp="$2"

    mkdir -p "$TF_PLANS_DIR" || return 1

    PLAN_FILE="$TF_PLANS_DIR/${ticket}-${stamp}.tfplan"
    TXT_FILE="$TF_PLANS_DIR/${ticket}-${stamp}.txt"
    SHOW_FILE="$TF_PLANS_DIR/${ticket}-${stamp}-show.txt"
}

_tf_uses_no_color() {
    [[ "${TF_PLAN_NO_COLOR:-1}" == "1" ]]
}

_tf_maybe_tfswitch() {
    command -v tfswitch >/dev/null 2>&1 || return 0
    tfswitch -b "${HOME}/.local/bin/terraform" >/dev/null 2>&1 || true
}

_tf_maybe_init() {
    local run_init="$1"
    local init_exit=0

    if [[ "$run_init" == "true" ]] || [[ ! -d .terraform ]]; then
        if _tf_uses_no_color; then
            terraform init -no-color || init_exit=$?
        else
            terraform init || init_exit=$?
        fi
    fi
    return "$init_exit"
}

_tf_latest_plan() {
    local ticket="$1"
    local latest=""

    # shellcheck disable=SC2012
    latest="$(ls -t "$TF_PLANS_DIR/${ticket}-"*.tfplan 2>/dev/null | head -1)"
    if [[ -z "$latest" ]]; then
        printf 'tf: no saved plan for %s in %s (run tf.plan.save first)\n' "$ticket" "$TF_PLANS_DIR" >&2
        return 1
    fi
    printf '%s' "$latest"
}

_tf_confirm_apply() {
    local plan_file="$1"
    local auto_yes="$2"
    local reply=""

    if [[ "$auto_yes" == "true" ]]; then
        return 0
    fi

    printf 'Apply plan? [y/N] %s\n' "$plan_file" >&2
    read -r reply
    case "$reply" in
        y | Y | yes | YES) return 0 ;;
        *) return 1 ;;
    esac
}

_tf_cleanup_plan_on_abort() {
    local plan_file="$1"

    if [[ "${TF_PLAN_KEEP_ON_APPLY_ABORT:-1}" == "0" && -f "$plan_file" ]]; then
        rm -f "$plan_file"
    fi
}

_tf_print_plan_summary() {
    printf '\nSaved plan artifacts:\n' >&2
    printf '  plan: %s\n' "$PLAN_FILE" >&2
    printf '  log:  %s\n' "$TXT_FILE" >&2
    printf '  show: %s\n' "$SHOW_FILE" >&2
    printf 'Attach .txt or -show.txt to GitLab MR; do not commit .tfplan to git.\n' >&2
}

# Usage: tf.plan.save [--init] [--no-sensitive] [--] [terraform plan args...]
tf.plan.save() {
    local ticket="" stamp="" init=false no_sensitive=false
    local -a plan_args=()
    local plan_exit=0 show_exit=0

    while (($# > 0)); do
        case "$1" in
            --init)
                init=true
                shift
                ;;
            --no-sensitive)
                no_sensitive=true
                shift
                ;;
            --)
                shift
                plan_args=("$@")
                break
                ;;
            *)
                plan_args+=("$1")
                shift
                ;;
        esac
    done

    _tf_ticket_resolve || return 1
    ticket="$TICKET"

    _tf_root_resolve || return 1
    _tf_maybe_tfswitch
    _tf_maybe_init "$init" || return 1

    stamp="$(_tf_timestamp)"
    _tf_paths_build "$ticket" "$stamp" || return 1

    if _tf_uses_no_color; then
        terraform plan -no-color -out="$PLAN_FILE" "${plan_args[@]}" 2>&1 | tee "$TXT_FILE"
    else
        terraform plan -out="$PLAN_FILE" "${plan_args[@]}" 2>&1 | tee "$TXT_FILE"
    fi
    plan_exit=${PIPESTATUS[0]}

    if [[ "$no_sensitive" == "true" ]]; then
        if _tf_uses_no_color; then
            if terraform show -no-color -no-sensitive "$PLAN_FILE" >"$SHOW_FILE" 2>/dev/null; then
                show_exit=0
            elif terraform show -no-color "$PLAN_FILE" >"$SHOW_FILE"; then
                show_exit=0
            else
                show_exit=$?
            fi
        elif terraform show -no-sensitive "$PLAN_FILE" >"$SHOW_FILE" 2>/dev/null; then
            show_exit=0
        elif terraform show "$PLAN_FILE" >"$SHOW_FILE"; then
            show_exit=0
        else
            show_exit=$?
        fi
    elif _tf_uses_no_color; then
        terraform show -no-color "$PLAN_FILE" >"$SHOW_FILE" || show_exit=$?
    else
        terraform show "$PLAN_FILE" >"$SHOW_FILE" || show_exit=$?
    fi

    export TF_PLAN_LAST="$PLAN_FILE"
    export TF_PLAN_LAST_TXT="$TXT_FILE"
    export TF_PLAN_LAST_SHOW="$SHOW_FILE"

    _tf_print_plan_summary

    if ((show_exit != 0)); then
        printf 'tf: warning: terraform show failed (exit %s); plan files still saved\n' "$show_exit" >&2
    fi

    return "$plan_exit"
}

# Usage: tf.state.show.save [grep-pattern] [--managed-only]
tf.state.show.save() {
    local ticket="" stamp="" pattern="" managed_only=false
    local state_file="" addr="" list_exit=0
    local -a addresses=()

    while (($# > 0)); do
        case "$1" in
            --managed-only)
                managed_only=true
                shift
                ;;
            --)
                shift
                break
                ;;
            -*)
                printf 'tf.state.show.save: unknown option %s\n' "$1" >&2
                return 1
                ;;
            *)
                if [[ -z "$pattern" ]]; then
                    pattern="$1"
                fi
                shift
                ;;
        esac
    done

    _tf_ticket_resolve || return 1
    ticket="$TICKET"

    _tf_root_resolve || return 1
    _tf_maybe_tfswitch

    stamp="$(_tf_timestamp)"
    mkdir -p "$TF_PLANS_DIR" || return 1
    state_file="$TF_PLANS_DIR/${ticket}-${stamp}-state.txt"

    {
        printf '# terraform state show — %s\n' "$ticket"
        printf '# root: %s\n' "$TF_ROOT"
        printf '# %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        if [[ -n "$pattern" ]]; then
            printf '# filter: %s\n' "$pattern"
        fi
        if [[ "$managed_only" == "true" ]]; then
            printf '# managed resources only (exclude data.*)\n'
        fi
        printf '\n'
    } >"$state_file"

    if [[ -n "$pattern" ]]; then
        while IFS= read -r addr; do
            [[ -n "$addr" ]] && addresses+=("$addr")
        done < <(terraform state list 2>/dev/null | grep -E "$pattern" | sort)
        list_exit=${PIPESTATUS[0]}
    else
        while IFS= read -r addr; do
            [[ -n "$addr" ]] && addresses+=("$addr")
        done < <(terraform state list 2>/dev/null | sort)
        list_exit=${PIPESTATUS[0]}
    fi

    if ((list_exit != 0)); then
        printf 'tf: terraform state list failed\n' >&2
        return "$list_exit"
    fi

    for addr in "${addresses[@]}"; do
        if [[ "$managed_only" == "true" && "$addr" == data.* ]]; then
            continue
        fi
        {
            printf '================================================================================\n'
            printf '# %s\n' "$addr"
            printf '================================================================================\n'
            if _tf_uses_no_color; then
                terraform state show -no-color "$addr"
            else
                terraform state show "$addr"
            fi
            printf '\n'
        } >>"$state_file" 2>&1 || true
    done

    printf '\nSaved state show:\n' >&2
    printf '  %s\n' "$state_file" >&2
    printf 'Attach to GitLab MR if useful post-apply evidence.\n' >&2

    return 0
}

# Usage: tf.apply.save [--init] [--yes] [--] [terraform plan args...]
tf.apply.save() {
    local init=false auto_yes=false
    local -a plan_args=()
    local plan_exit=0 apply_exit=0

    while (($# > 0)); do
        case "$1" in
            --init)
                init=true
                shift
                ;;
            --yes)
                auto_yes=true
                shift
                ;;
            --)
                shift
                plan_args=("$@")
                break
                ;;
            *)
                plan_args+=("$1")
                shift
                ;;
        esac
    done

    local -a save_args=()
    [[ "$init" == "true" ]] && save_args+=(--init)
    save_args+=(-- "${plan_args[@]}")

    tf.plan.save "${save_args[@]}"
    plan_exit=$?

    if ((plan_exit == 1)); then
        return 1
    fi

    if [[ -z "${TF_PLAN_LAST:-}" || ! -f "$TF_PLAN_LAST" ]]; then
        printf 'tf: no plan file to apply\n' >&2
        return 1
    fi

    if ! _tf_confirm_apply "$TF_PLAN_LAST" "$auto_yes"; then
        _tf_cleanup_plan_on_abort "$TF_PLAN_LAST"
        printf 'Apply cancelled.\n' >&2
        return 0
    fi

    _tf_root_resolve || return 1
    if _tf_uses_no_color; then
        terraform apply -no-color "$TF_PLAN_LAST" || apply_exit=$?
    else
        terraform apply "$TF_PLAN_LAST" || apply_exit=$?
    fi

    if ((apply_exit != 0)); then
        _tf_cleanup_plan_on_abort "$TF_PLAN_LAST"
        return "$apply_exit"
    fi

    return 0
}

# Usage: tf.apply.last [--yes]
tf.apply.last() {
    local auto_yes=false plan_file="" txt_file=""
    local apply_exit=0

    while (($# > 0)); do
        case "$1" in
            --yes)
                auto_yes=true
                shift
                ;;
            *)
                printf 'tf.apply.last: unknown argument %s\n' "$1" >&2
                return 1
                ;;
        esac
    done

    _tf_ticket_resolve || return 1
    _tf_root_resolve || return 1
    _tf_maybe_tfswitch

    plan_file="$(_tf_latest_plan "$TICKET")" || return 1
    TF_PLAN_LAST="$plan_file"
    export TF_PLAN_LAST

    txt_file="${plan_file%.tfplan}.txt"
    if [[ -f "$txt_file" ]]; then
        printf 'Plan preview (%s):\n' "$txt_file" >&2
        head -n 30 "$txt_file" >&2
        printf '\n' >&2
    fi

    if ! _tf_confirm_apply "$plan_file" "$auto_yes"; then
        _tf_cleanup_plan_on_abort "$plan_file"
        printf 'Apply cancelled.\n' >&2
        return 0
    fi

    if _tf_uses_no_color; then
        terraform apply -no-color "$plan_file" || apply_exit=$?
    else
        terraform apply "$plan_file" || apply_exit=$?
    fi

    if ((apply_exit != 0)); then
        _tf_cleanup_plan_on_abort "$plan_file"
        return "$apply_exit"
    fi

    return 0
}

alias tf='terraform'
alias tf.plan='terraform plan -out=tfplan'
alias tf.apply='terraform apply tfplan'
alias tf.destroy.plan='terraform plan -destroy -out=tfplan'
alias tf-plan-save='tf.plan.save'
alias tf-state-show-save='tf.state.show.save'
alias tf-apply-save='tf.apply.save'
alias tf-apply-last='tf.apply.last'

if command -v tfswitch >/dev/null 2>&1; then
    alias tfswitch='tfswitch -b ~/.local/bin/terraform'
fi

_terraform_platform="$(uname -s 2>/dev/null):$(uname -m 2>/dev/null)"
if [[ "$_terraform_platform" == "Darwin:arm64" ]] && command -v docker >/dev/null 2>&1; then
    unset _terraform_platform

    _terraform_detect_version() {
        local version=""

        version="$(terraform version -json 2>/dev/null | awk -F'"' '/"terraform_version"/ { print $4; exit }')"
        if [[ -z "$version" ]]; then
            version="$(terraform --version 2>/dev/null | awk 'NR==1 { print substr($2, 2) }')"
        fi

        printf '%s' "$version"
    }

    # Special case: linux/amd64 Terraform in Docker (not used by tf.plan.save).
    tf.amd64() {
        local tag image
        local uid gid passwd_file group_file exit_code container_ssh_auth_sock
        local -a docker_args env_args mount_args

        uid="$(id -u)"
        gid="$(id -g)"
        passwd_file="$(mktemp "${TMPDIR:-/tmp}/tf-amd64-passwd.XXXXXX")" || return 1
        group_file="$(mktemp "${TMPDIR:-/tmp}/tf-amd64-group.XXXXXX")" || {
            command rm -f "$passwd_file"
            return 1
        }

        tag="${TF_AMD64_TAG:-$(_terraform_detect_version)}"
        [[ -n "$tag" ]] || tag="latest"

        image="${TF_AMD64_IMAGE:-hashicorp/terraform:$tag}"
        container_ssh_auth_sock="${TF_AMD64_SSH_AUTH_SOCK:-/run/host-services/ssh-auth.sock}"

        command printf 'terraform:x:%s:%s:Terraform:/home/terraform:/bin/sh\n' "$uid" "$gid" >"$passwd_file"
        command printf 'terraform:x:%s:\n' "$gid" >"$group_file"

        env_args=(
            -e HOME=/home/terraform
            -e USER=terraform
            -e LOGNAME=terraform
            -e SSH_AUTH_SOCK="$container_ssh_auth_sock"
            -e AWS_PROFILE
            -e AWS_REGION
            -e AWS_DEFAULT_REGION
            -e AWS_ACCESS_KEY_ID
            -e AWS_SECRET_ACCESS_KEY
            -e AWS_SESSION_TOKEN
            -e AWS_SECURITY_TOKEN
            -e TF_INPUT
            -e TF_IN_AUTOMATION
            -e TF_LOG
            -e TF_LOG_PATH
            -e TF_WORKSPACE
        )

        mount_args=(
            -v "$PWD:/workspace"
            -v "$passwd_file:/etc/passwd:ro"
            -v "$group_file:/etc/group:ro"
        )

        if [[ -d "$HOME/.aws" ]]; then
            mount_args+=(-v "$HOME/.aws:/home/terraform/.aws:ro")
        fi
        if [[ -d "$HOME/.ssh" ]]; then
            mount_args+=(-v "$HOME/.ssh:/home/terraform/.ssh:ro")
        fi
        if [[ -S "/run/host-services/ssh-auth.sock" ]]; then
            mount_args+=(-v "/run/host-services/ssh-auth.sock:$container_ssh_auth_sock")
        elif [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK}" ]]; then
            mount_args+=(-v "${SSH_AUTH_SOCK}:$container_ssh_auth_sock")
        fi
        if [[ -f "$HOME/.terraformrc" ]]; then
            mount_args+=(-v "$HOME/.terraformrc:/home/terraform/.terraformrc:ro")
        fi
        if [[ -d "$HOME/.terraform.d" ]]; then
            mount_args+=(-v "$HOME/.terraform.d:/home/terraform/.terraform.d")
        fi

        docker_args=(
            run
            --rm
            -it
            --platform linux/amd64
            --user "$uid:$gid"
            "${env_args[@]}"
            "${mount_args[@]}"
            -w /workspace
            "$image"
        )

        docker "${docker_args[@]}" "$@"
        exit_code=$?

        command rm -f "$passwd_file" "$group_file"
        return "$exit_code"
    }
else
    unset _terraform_platform
fi
