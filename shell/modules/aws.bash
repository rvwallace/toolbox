# shellcheck shell=bash
# AWS Interactive shell module bash completions

toolbox_require_commands aws aws || return 0

_aws_env_complete_bash() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cword=$COMP_CWORD
    local words=("${COMP_WORDS[@]}")

    local commands="set profile region show clear token-status"

    case "${prev}" in
        profile)
            local profiles
            profiles=$(_aws_get_profiles_cache 2>/dev/null)
            COMPREPLY=( $(compgen -W "${profiles}" -- "${cur}") )
            return
            ;;
        region)
            local regions=""
            for r in "${AWS_REGIONS[@]}"; do
                regions+="${r%%:*} "
            done
            COMPREPLY=( $(compgen -W "${regions}" -- "${cur}") )
            return
            ;;
        set)
            local profiles
            profiles=$(_aws_get_profiles_cache 2>/dev/null)
            COMPREPLY=( $(compgen -W "${profiles}" -- "${cur}") )
            return
            ;;
    esac

    if [[ $cword -ge 2 && "${words[cword-2]:-}" == "set" ]]; then
        local regions=""
        for r in "${AWS_REGIONS[@]}"; do
            regions+="${r%%:*} "
        done
        COMPREPLY=( $(compgen -W "${regions}" -- "${cur}") )
        return
    fi

    if [[ "${cword}" == 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
    fi
}

complete -F _aws_env_complete_bash aws.env
