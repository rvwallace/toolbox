# shellcheck shell=bash
# Chef Interactive shell module bash completions

toolbox_require_commands chef knife || return 0

_chef_env_complete_bash() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cword=$COMP_CWORD
    local words=("${COMP_WORDS[@]}")

    local commands="set clear show list"

    case "${prev}" in
        set)
            local configs
            configs=$(chef.env list 2>/dev/null | awk '{print $2}')
            COMPREPLY=( $(compgen -W "${configs}" -- "${cur}") )
            return
            ;;
    esac

    if [[ "${cword}" == 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
    fi
}

complete -F _chef_env_complete_bash chef.env
