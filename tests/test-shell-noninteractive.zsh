#!/usr/bin/env zsh
emulate -LR zsh
setopt err_exit pipe_fail
local root="${TOOLBOX_TEST_ROOT:-${0:A:h:h}}"
local probe=$(mktemp -d "${TMPDIR:-/tmp}/toolbox-shell-test.XXXXXX")
trap 'rm -rf -- "$probe"' EXIT
mkdir -p "$probe/home" "$probe/bin" "$probe/toolbox"
ln -s "$root/shell" "$probe/toolbox/shell"
for dependency in aws knife kubectl sesh tmux terraform; do
    print -r -- '#!/bin/sh' 'exit 0' > "$probe/bin/$dependency"
    chmod +x "$probe/bin/$dependency"
done
for mode in plain completion; do
    env -u TOOLBOX_LOADED HOME="$probe/home" XDG_CACHE_HOME="$probe/cache" \
        XDG_CONFIG_HOME="$probe/config" TMUX=test PATH="$probe/bin:/usr/bin:/bin" \
        zsh -dfc '
            if [[ $2 == completion ]]; then
                autoload -Uz compinit
                compinit -i -D
            fi
            source "$1/shell/init.sh"
            for helper in aws.env chef.env git.ignore.add k.env terraform.plan.save tp; do
                (( ${+functions[$helper]} )) || exit 1
            done
            export AWS_PROFILE=example AWS_REGION=example
            aws.env clear
            [[ -z ${AWS_PROFILE:-} && -z ${AWS_REGION:-} ]] || exit 1
            (( ! ${+widgets[_tmux_popup_toggle]} )) || exit 1
            if [[ $2 == completion ]]; then
                [[ $_comps[aws.env] == _aws_env &&
                   $_comps[chef.env] == _chef_env &&
                   $_comps[git.ignore.add] == _toolbox_git_ignore_add &&
                   $_comps[k.env] == _k_env &&
                   $_comps[tp] == _toolbox_tp ]] || exit 1
            else
                (( ! ${+functions[compdef]} )) || exit 1
                [[ ! -d $XDG_CACHE_HOME/silentcastle/toolbox/completions ]] || exit 1
            fi
        ' test "$probe/toolbox" "$mode" > "$probe/stdout" 2> "$probe/stderr" || { cat "$probe/stderr" >&2; exit 1; }
    if [[ -s "$probe/stderr" ]]; then
        cat "$probe/stderr" >&2
        exit 1
    fi
done
print 'PASS: noninteractive Toolbox commands, optional completions, and widget guard'
