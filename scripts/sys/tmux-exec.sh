#!/bin/bash
#
# tmux-exec.sh - Execute a command in a new tmux pane
#
# Usage: tmux-exec.sh [-v|-h|-w] [-i|-p] <command> [args...]
#   -v: Create a vertical split (default)
#   -h: Create a horizontal split
#   -w: Create a new window
#   -i: Interactive mode (keep pane open after command exits)
#   -p: Pause mode (wait for keypress after command exits)
#

# Default settings
SPLIT_TYPE="-v"
INTERACTIVE=false
PAUSE=false

# Parse options
while [[ "$1" == -* ]]; do
    case "$1" in
        -v|-h|-w)
            SPLIT_TYPE="$1"
            ;;
        -i)
            INTERACTIVE=true
            PAUSE=false  # Interactive mode overrides pause mode
            ;;
        -p)
            PAUSE=true
            # Only set PAUSE if not in interactive mode
            if [ "$INTERACTIVE" = true ]; then
                PAUSE=false
            fi
            ;;
        *)
            echo "Error: Invalid option: $1"
            echo "Usage: tmux-exec.sh [-v|-h|-w] [-i|-p] <command> [args...]"
            exit 1
            ;;
    esac
    shift
done

# Check if a command was provided
if [ $# -eq 0 ]; then
    echo "Error: No command specified"
    echo "Usage: tmux-exec.sh [-v|-h|-w] [-i|-p] <command> [args...]"
    exit 1
fi

# Combine all remaining arguments into a single command
COMMAND="$*"

# Check if we're in a tmux session
if [ -z "$TMUX" ]; then
    echo "Error: Not in a tmux session"
    exit 1
fi

# Prepare the command
if [ "$INTERACTIVE" = true ]; then
    # In interactive mode, run the command and then start a shell
    EXEC_CMD="$COMMAND; exec $SHELL"
elif [ "$PAUSE" = true ]; then
    # In pause mode, run the command and then wait for a keypress
    EXEC_CMD="$COMMAND; echo; echo 'Press <enter> key to exit...'; read -n 1"
else
    # In normal mode, just run the command
    EXEC_CMD="$COMMAND"
fi

# Execute the command in a new pane based on the split type
case "$SPLIT_TYPE" in
    "-v")
        # Vertical split (default)
        tmux split-window -v "$EXEC_CMD"
        ;;
    "-h")
        # Horizontal split
        tmux split-window -h "$EXEC_CMD"
        ;;
    "-w")
        # New window
        tmux new-window -n "$(echo "$1" | cut -d ' ' -f 1)" "$EXEC_CMD"
        ;;
    *)
        echo "Error: Invalid split type: $SPLIT_TYPE"
        echo "Usage: tmux-exec.sh [-v|-h|-w] [-i|-p] <command> [args...]"
        exit 1
        ;;
esac

exit 0
