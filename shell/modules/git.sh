#!/usr/bin/env bash
# shellcheck shell=bash
# git shell helpers

git.ignore.add() {
    if [[ -z "${1-}" ]]; then
        printf 'Usage: git.ignore.add <pattern>\n' >&2
        return 1
    fi

    printf '%s\n' "$1" >> .gitignore
}

_git_require_repo() {
    git rev-parse --show-toplevel >/dev/null 2>&1 || {
        printf 'git: not inside a git repository\n' >&2
        return 1
    }
}

git.commit-amend() {
    _git_require_repo || return 1
    git commit --amend --no-edit "$@"
}

git.branch-list() {
    _git_require_repo || return 1
    git branch -a "$@"
}

git.diff-staged() {
    _git_require_repo || return 1
    git diff --staged "$@"
}

git.log-all() {
    _git_require_repo || return 1
    git log --graph --oneline --decorate --all "$@"
}

git.cdroot() {
    local root

    root=$(git rev-parse --show-toplevel 2>/dev/null) || {
        printf 'git.cdroot: not inside a git repository\n' >&2
        return 1
    }

    cd "$root" || return 1
}

git.undo() {
    local count="${1:-1}"

    _git_require_repo || return 1
    [[ "$count" =~ ^[1-9][0-9]*$ ]] || {
        printf 'Usage: git.undo [count]\n' >&2
        return 1
    }

    git rev-parse --verify "HEAD~${count}" >/dev/null 2>&1 || {
        printf 'git.undo: cannot move back %s commit(s)\n' "$count" >&2
        return 1
    }

    printf 'git.undo: soft reset HEAD by %s commit(s)\n' "$count" >&2
    git reset --soft "HEAD~${count}"
}

git.delete-merged-branches() {
    local apply=0
    local branch current
    local protected='main|master|develop|dev|trunk'
    local branches=()

    _git_require_repo || return 1

    if [[ "${1-}" == "--apply" ]]; then
        apply=1
        shift
    fi
    if (($# > 0)); then
        printf 'Usage: git.delete-merged-branches [--apply]\n' >&2
        return 1
    fi

    current=$(git branch --show-current 2>/dev/null)
    while IFS= read -r branch; do
        branch=${branch#\* }
        branch=${branch#  }
        [[ -z "$branch" ]] && continue
        [[ "$branch" == "$current" ]] && continue
        [[ "$branch" =~ ^(${protected})$ ]] && continue
        branches+=("$branch")
    done < <(git branch --merged)

    if ((${#branches[@]} == 0)); then
        printf 'git.delete-merged-branches: no merged branches to delete\n'
        return 0
    fi

    printf 'Merged branches eligible for deletion:\n'
    printf '  %s\n' "${branches[@]}"

    if ((apply == 0)); then
        printf 'Dry run only. Re-run with --apply to delete these branches.\n'
        return 0
    fi

    for branch in "${branches[@]}"; do
        git branch -d "$branch" || return 1
    done
}

git.stats() {
    _git_require_repo || return 1
    git log --pretty=tformat: --numstat "$@" | awk '
        {
            add += $1
            subs += $2
            loc += $1 - $2
        }
        END {
            printf "Added lines: %s\nRemoved lines: %s\nTotal lines: %s\n", add, subs, loc
        }
    '
}
