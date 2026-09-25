# Tmux shell helpers for Nushell

# Run a command inside a tmux display-popup window
export def tp [
    --keep-on-error (-E) # Stay open if command fails (useful for debugging)
    ...cmd: string
] {
    if (which tmux | is-empty) {
        print -e "tp: tmux not found"
        return 1
    }

    if ("TMUX" not-in $env) {
        print -e "tp: not inside a tmux session"
        return 1
    }

    if ($cmd | is-empty) {
        print -e "Usage: tp [-E] <command...>"
        return 1
    }

    let flag = if $keep_on_error { "-EE" } else { "-E" }
    tmux display-popup $flag -- /bin/sh -c ($cmd | str join " ")
}
