# Git shell helpers for Nushell

# Navigate to git repository root
export def --env "git.cdroot" [] {
    let root = (git rev-parse --show-toplevel err> /dev/null | str trim)
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
    let is_repo = (git rev-parse --is-inside-work-tree err> /dev/null | str trim)
    if ($is_repo != "true") {
        print -e "git: not inside a git repository"
        return 1
    }

    let target = $"HEAD~($count)"
    let verify = (git rev-parse --verify $target err> /dev/null | str trim)
    if ($verify | is-empty) {
        print -e $"git.undo: cannot move back ($count) commit(s)"
        return 1
    }

    print $"git.undo: soft reset HEAD by ($count) commit(s)"
    git reset --soft $target
}

# Delete merged branches (dry-run by default, pass --apply to delete)
export def "git.delete-merged-branches" [--apply] {
    let is_repo = (git rev-parse --is-inside-work-tree err> /dev/null | str trim)
    if ($is_repo != "true") {
        print -e "git: not inside a git repository"
        return 1
    }

    let current = (git branch --show-current err> /dev/null | str trim)
    let protected = ["main", "master", "develop", "dev", "trunk"]

    let branches = (
        git branch --merged
        | lines
        | each { |b| $b | str replace --regex '^\*?\s+' '' }
        | where { |b| ($b | is-not-empty) and ($b != $current) and not ($b in $protected) }
    )

    if ($branches | is-empty) {
        print "git.delete-merged-branches: no merged branches to delete"
        return
    }

    print "Merged branches eligible for deletion:"
    $branches | each { |b| print $"  ($b)" }

    if not $apply {
        print "(char nl)Dry run only. Re-run with --apply to delete these branches."
        return
    }

    $branches | each { |b| git branch -d $b }
}

export alias "git.commit-amend" = git commit --amend --no-edit
export alias "git.branch-list" = git branch -a
export alias "git.diff-staged" = git diff --staged
export alias "git.log-all" = git log --graph --oneline --decorate --all
