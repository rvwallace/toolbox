# Yazi shell wrapper for Nushell

# Open Yazi and navigate to selected directory on exit
export def --env y [...args: string] {
    if (which yazi | is-empty) {
        print -e "y: yazi not found"
        return 1
    }

    let tmp = (mktemp -t "yazi-cwd.XXXXXX")
    ^yazi ...$args --cwd-file $tmp

    if ($tmp | path exists) {
        let cwd = (open $tmp | str trim)
        if ($cwd | is-not-empty) and ($cwd != $env.PWD) and ($cwd | path exists) {
            cd $cwd
        }
        rm -fp $tmp
    }
}
