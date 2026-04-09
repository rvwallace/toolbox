# shellcheck shell=zsh
# zsh completions for cmux and cmux shell helpers

toolbox_require_commands cmux cmux || return 0

# Helper: complete surface refs from cmux tree
_toolbox_cmux_surfaces() {
    local -a surfaces
    surfaces=(${(f)"$(cmux tree --json 2>/dev/null | \
        command python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for w in d.get('windows', []):
        for ws in w.get('workspaces', []):
            for p in ws.get('panes', []):
                for s in p.get('surfaces', []):
                    print(s['ref'] + ':' + s.get('title','').replace(':',''))
except: pass
" 2>/dev/null)"})
    _describe 'surface' surfaces
}

# Helper: complete workspace refs
_toolbox_cmux_workspaces() {
    local -a workspaces
    workspaces=(${(f)"$(cmux list-workspaces 2>/dev/null | awk '{print $1}' | grep 'workspace:')"})
    _describe 'workspace' workspaces
}

# Helper: complete pane refs
_toolbox_cmux_panes() {
    local -a panes
    panes=(${(f)"$(cmux list-panes 2>/dev/null | awk '{print $1}' | grep 'pane:')"})
    _describe 'pane' panes
}

_toolbox_cmux() {
    local state

    local -a global_opts
    global_opts=(
        '--socket[Unix socket path]:socket path:_files'
        '--window[Target window]:window ref'
        '--password[Socket auth password]:password'
        '--json[Output as JSON]'
        '--id-format[ID format]:format:(refs uuids both)'
    )

    _arguments -C \
        $global_opts \
        '1: :_toolbox_cmux_commands' \
        '*:: :->subcmd'

    case $state in
        subcmd)
            case $words[1] in
                select-workspace|close-workspace|rename-workspace|current-workspace|\
                list-panes|new-split|focus-pane|new-pane|new-surface)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--direction[Direction]:direction:(left right up down)' \
                        '--type[Type]:type:(terminal browser)' \
                        '--url[URL]:url:_urls'
                    ;;
                focus-window|close-window)
                    _arguments '--window[Window]:window ref'
                    ;;
                close-surface|refresh-surfaces|surface-health|clear-history)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces'
                    ;;
                move-surface)
                    _arguments \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--pane[Target pane]:pane ref:_toolbox_cmux_panes' \
                        '--workspace[Target workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--before[Before surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--after[After surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--index[Index]:number' \
                        '--focus[Focus after move]:bool:(true false)'
                    ;;
                send)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--[End of options]' \
                        '*:text'
                    ;;
                send-key|send-panel|send-key-panel)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--panel[Panel]:panel ref' \
                        '*:key'
                    ;;
                capture-pane|read-screen)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--scrollback[Include scrollback]' \
                        '--lines[Last N lines]:number'
                    ;;
                notify)
                    _arguments \
                        '--title[Title]:title' \
                        '--subtitle[Subtitle]:subtitle' \
                        '--body[Body]:body' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces'
                    ;;
                trigger-flash)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces'
                    ;;
                set-status)
                    _arguments \
                        '--icon[Icon name]:icon' \
                        '--color[Hex color]:color' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '1:key' \
                        '2:value'
                    ;;
                clear-status|list-status)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '1:key'
                    ;;
                set-progress)
                    _arguments \
                        '--label[Label]:label' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '1:value (0.0-1.0)'
                    ;;
                clear-progress)
                    _arguments '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces'
                    ;;
                log)
                    _arguments \
                        '--level[Log level]:level:(debug info warn error)' \
                        '--source[Source name]:source' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--[End of options]' \
                        '*:message'
                    ;;
                list-log)
                    _arguments \
                        '--limit[Max entries]:number' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces'
                    ;;
                clear-log)
                    _arguments '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces'
                    ;;
                tree)
                    _arguments \
                        '--all[All windows]' \
                        '--workspace[Filter to workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--json[JSON output]'
                    ;;
                identify)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces' \
                        '--no-caller[Omit caller context]'
                    ;;
                pipe-pane)
                    _arguments \
                        '--command[Shell command]:command:_command_names' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '--surface[Surface]:surface ref:_toolbox_cmux_surfaces'
                    ;;
                resize-pane)
                    _arguments \
                        '--pane[Pane]:pane ref:_toolbox_cmux_panes' \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '-L[Resize left]' '-R[Resize right]' \
                        '-U[Resize up]' '-D[Resize down]' \
                        '--amount[Amount]:number'
                    ;;
                new-workspace)
                    _arguments \
                        '--cwd[Working directory]:directory:_directories' \
                        '--command[Command to run]:command:_command_names'
                    ;;
                rename-workspace|rename-window|rename-tab)
                    _arguments \
                        '--workspace[Workspace]:workspace ref:_toolbox_cmux_workspaces' \
                        '*:title'
                    ;;
                claude-hook)
                    _arguments '1:event:(session-start stop notification)'
                    ;;
                themes)
                    _arguments '1:action:(list set clear)'
                    ;;
                markdown)
                    _arguments \
                        '1:action:(open)' \
                        '2:path:_files -g "*.md"'
                    ;;
                browser)
                    local -a browser_cmds
                    browser_cmds=(
                        'open:Open URL in browser pane'
                        'open-split:Open URL in browser split'
                        'goto:Navigate to URL'
                        'navigate:Navigate to URL'
                        'back:Go back'
                        'forward:Go forward'
                        'reload:Reload page'
                        'url:Get current URL'
                        'get-url:Get current URL'
                        'snapshot:Snapshot DOM'
                        'eval:Evaluate JavaScript'
                        'wait:Wait for condition'
                        'click:Click element'
                        'dblclick:Double-click element'
                        'hover:Hover element'
                        'type:Type into element'
                        'fill:Fill input'
                        'press:Press key'
                        'select:Select option'
                        'scroll:Scroll'
                        'screenshot:Take screenshot'
                        'get:Get page property'
                        'find:Find element'
                        'dialog:Handle dialog'
                        'download:Handle download'
                        'cookies:Manage cookies'
                        'storage:Manage storage'
                        'tab:Manage tabs'
                        'console:Browser console'
                        'errors:Browser errors'
                        'highlight:Highlight element'
                        'identify:Identify browser surface'
                    )
                    _arguments \
                        '--surface[Browser surface]:surface ref:_toolbox_cmux_surfaces' \
                        '1:subcommand:((${browser_cmds[@]}))' \
                        '*:args'
                    ;;
            esac
            ;;
    esac
}

_toolbox_cmux_commands() {
    local -a cmds
    cmds=(
        'version:Show version'
        'ping:Ping cmux socket'
        'identify:Show current context'
        'capabilities:Show server capabilities'
        'welcome:Show welcome message'
        'shortcuts:Show keyboard shortcuts'
        'feedback:Send feedback'
        'list-windows:List windows'
        'current-window:Show current window'
        'new-window:Create new window'
        'focus-window:Focus a window'
        'close-window:Close a window'
        'rename-window:Rename window'
        'list-workspaces:List workspaces'
        'current-workspace:Show current workspace'
        'new-workspace:Create new workspace'
        'select-workspace:Switch to workspace'
        'close-workspace:Close workspace'
        'rename-workspace:Rename workspace'
        'reorder-workspace:Reorder workspace'
        'move-workspace-to-window:Move workspace to another window'
        'list-panes:List panes'
        'new-pane:Create new pane'
        'new-split:Create split pane'
        'focus-pane:Focus pane'
        'focus-panel:Focus panel'
        'list-panels:List panels'
        'resize-pane:Resize pane'
        'swap-pane:Swap panes'
        'break-pane:Break pane to new workspace'
        'join-pane:Join pane'
        'last-pane:Switch to last pane'
        'list-pane-surfaces:List surfaces in pane'
        'new-surface:Create new surface'
        'close-surface:Close surface'
        'move-surface:Move surface'
        'reorder-surface:Reorder surface'
        'rename-tab:Rename tab'
        'refresh-surfaces:Refresh all surfaces'
        'surface-health:Check surface health'
        'trigger-flash:Flash pane border'
        'drag-surface-to-split:Drag surface to split'
        'tree:Show workspace tree'
        'send:Send text to surface'
        'send-key:Send key to surface'
        'send-panel:Send text to panel'
        'send-key-panel:Send key to panel'
        'read-screen:Read terminal text'
        'capture-pane:Capture pane output (tmux compat)'
        'clear-history:Clear terminal history'
        'notify:Send notification'
        'list-notifications:List notifications'
        'clear-notifications:Clear notifications'
        'set-status:Set sidebar status item'
        'clear-status:Clear sidebar status item'
        'list-status:List sidebar status items'
        'set-progress:Set sidebar progress'
        'clear-progress:Clear sidebar progress'
        'sidebar-state:Show sidebar state'
        'log:Add log entry'
        'list-log:List log entries'
        'clear-log:Clear log'
        'claude-hook:Trigger Claude Code hook event'
        'claude-teams:Launch Claude teams'
        'themes:Manage themes'
        'markdown:Open markdown file'
        'find-window:Find window by content'
        'pipe-pane:Pipe pane output to command'
        'wait-for:Wait for signal'
        'respawn-pane:Respawn pane'
        'display-message:Display message'
        'paste-buffer:Paste buffer to surface'
        'list-buffers:List paste buffers'
        'set-buffer:Set paste buffer'
        'next-window:Switch to next window'
        'previous-window:Switch to previous window'
        'last-window:Switch to last window'
        'copy-mode:Enter copy mode'
        'set-hook:Set tmux hook'
        'popup:Show popup'
        'browser:Browser automation subcommands'
    )
    _describe 'command' cmds
}

_toolbox_cmux_ssh_wrapper() {
    _arguments \
        '(-i --identity)'{-i,--identity}'[Pass through identity mode to cmux ssh]' \
        '*:args:_normal'
}

_toolbox_cmux_jc_wrapper() {
    _arguments \
        '1:host:_hosts' \
        '*:remote args:_normal'
}

compdef _toolbox_cmux cmux
compdef _toolbox_cmux_ssh_wrapper cssh
compdef _toolbox_cmux_jc_wrapper csshjc
