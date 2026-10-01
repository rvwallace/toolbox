# Git shell helpers for Nushell

# Navigate to git repository root
export def --env "git.cdroot" [] {
    let root = git rev-parse --show-toplevel err> /dev/null | str trim
    if ($root | is-empty) {
        print -e "git.cdroot: not inside a git repository"
        return 1
    }
    cd $root
}

# Append pattern to .gitignore
export def "git.ignore.add" [pattern: string] {
    if ($pattern | is-empty) {
        print -e "Usage: git.ignore.add <pattern>"
        return 1
    }
    $"($pattern)(char nl)" | save --append .gitignore
}

# Soft reset HEAD back by count commits (default 1)
export def "git.undo" [count: int = 1] {
    let is_repo = git rev-parse --is-inside-work-tree err> /dev/null | str trim
    if $is_repo != "true" {
        print -e "git: not inside a git repository"
        return 1
    }

    let target = $"HEAD~($count)"
    let verify = git rev-parse --verify $target err> /dev/null | str trim
    if ($verify | is-empty) {
        print -e $"git.undo: cannot move back ($count) commit(s)"
        return 1
    }

    print $"git.undo: soft reset HEAD by ($count) commit(s)"
    git reset --soft $target
}

# Delete merged branches (dry-run by default, pass --apply to delete)
export def "git.delete-merged-branches" [--apply] {
    let is_repo = git rev-parse --is-inside-work-tree err> /dev/null | str trim
    if $is_repo != "true" {
        print -e "git: not inside a git repository"
        return 1
    }

    let current = git branch --show-current err> /dev/null | str trim
    let protected = ["main", "master", "develop", "dev", "trunk"]

    let branches = (
        git branch --merged
        | lines
        | each {|b| $b | str replace --regex '^\*?\s+' '' }
        | where {|b| ($b | is-not-empty) and ($b != $current) and not ($b in $protected) }
    )

    if ($branches | is-empty) {
        print "git.delete-merged-branches: no merged branches to delete"
        return
    }

    print "Merged branches eligible for deletion:"
    $branches | each {|b| print $"  ($b)" }

    if not $apply {
        print "(char nl)Dry run only. Re-run with --apply to delete these branches."
        return
    }

    $branches | each {|b| git branch -d $b }
}

export def "git.log" [count: int = 5] {
    git log --pretty=%h»¦«%s»¦«%aN»¦«%aE»¦«%aD -n $count
    | lines
    | split column "»¦«" commit subject name email date
    | upsert date {|d| $d.date | into datetime}
}

export def "git.last-commit" [] {
    git.log 1 | first
}

export def "git.current-branch" [] {
    let branch = git branch --show-current | str trim
    if ($branch | is-empty) {
        "HEAD"
    } else {
        $branch
    }
}

export def "git.status" [] {
    let changes = (
        git status --short
        | lines
        | parse --regex '^(?<index>.)(?<worktree>.)\s(?<path>.*)$'
    )

    {
        branch: (git.current-branch)
        changes: $changes
    }
}

export def "git.changed-files" [--staged] {
    let diff = if $staged {
        git diff --cached --name-status --find-renames
    } else {
        git diff --name-status --find-renames
    }

    $diff
    | lines
    | parse --regex '^(?<status>\S+)\t(?<path>.*)$'
}

export def "git.commit-amend" [] {
    git commit --amend --no-edit
}

export def "git.branch-list" [] {
    git branch --all --format='%(HEAD)»¦«%(refname:short)»¦«%(upstream:short)'
    | lines
    | split column "»¦«" current branch upstream
    | upsert current {|b| $b.current == "*"}
}

export def "git.diff-staged" [] {
    git diff --staged
}

export def "git.log-all" [count: int = 0] {
    let log = if $count > 0 {
        git log --pretty=%h»¦«%s»¦«%aN»¦«%aE»¦«%aD --all -n $count
    } else {
        git log --pretty=%h»¦«%s»¦«%aN»¦«%aE»¦«%aD --all
    }

    $log
    | lines
    | split column "»¦«" commit subject name email date
    | upsert date {|d| $d.date | into datetime}
}

export def "git.stash-list" [] {
    git stash list --format='%gd»¦«%H»¦«%s»¦«%aD'
    | lines
    | split column "»¦«" stash commit subject date
    | upsert date {|d| $d.date | into datetime}
}

export def "git.recent-branches" [] {
    let branches = (git for-each-ref --sort=-committerdate --format='%(refname:short)»¦«%(objectname:short)»¦«%(committerdate:iso-strict)»¦«%(subject)' refs/heads)

    $branches
    | lines
    | split column "»¦«" branch commit date subject
    | upsert date {|b| $b.date | into datetime}
}

export def "git.log-graph" [] {
    git log --graph --oneline --decorate --all
}
