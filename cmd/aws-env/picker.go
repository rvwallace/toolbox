package main

import (
	"fmt"
	"strings"
	"unicode"

	"charm.land/bubbles/v2/spinner"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

var (
	titleStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
	selStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("212")).Bold(true)
	dimStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))
	helpStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))
	errStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("196"))
)

type pickerState int

const (
	pickerLoading pickerState = iota
	pickerReady
	pickerDone
	pickerAborted
	pickerError
)

type itemsLoadedMsg struct {
	items []string
	err   error
}

type pickerModel struct {
	title  string
	loader func() ([]string, error)

	state   pickerState
	spinner spinner.Model

	items    []string
	filtered []string
	cursor   int
	query    string

	Selected string
	Aborted  bool

	width  int
	height int
	err    error
}

func newPickerModel(title string, loader func() ([]string, error), initialQuery string) pickerModel {
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	m := pickerModel{
		title:   title,
		loader:  loader,
		state:   pickerLoading,
		spinner: sp,
		query:   initialQuery,
	}
	return m
}

func (m pickerModel) Init() tea.Cmd {
	return tea.Batch(m.spinner.Tick, m.loadItemsCmd())
}

func (m pickerModel) loadItemsCmd() tea.Cmd {
	loader := m.loader
	return func() tea.Msg {
		items, err := loader()
		return itemsLoadedMsg{items: items, err: err}
	}
}

func (m pickerModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		return m, nil

	case itemsLoadedMsg:
		if msg.err != nil {
			m.state = pickerError
			m.err = msg.err
			return m, nil
		}
		m.items = msg.items
		m.state = pickerReady
		m.applyFilter()
		return m, nil

	case tea.KeyPressMsg:
		key := msg.String()

		if key == "ctrl+c" || key == "esc" {
			m.Aborted = true
			return m, tea.Quit
		}

		if m.state != pickerReady {
			return m, nil
		}

		switch key {
		case "enter":
			if len(m.filtered) > 0 {
				m.Selected = m.filtered[m.cursor]
				m.state = pickerDone
				return m, tea.Quit
			}
		case "up":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
			}
		case "backspace":
			if len(m.query) > 0 {
				runes := []rune(m.query)
				m.query = string(runes[:len(runes)-1])
				m.applyFilter()
			}
		case "ctrl+u":
			m.query = ""
			m.applyFilter()
		default:
			if isPrintable(key) {
				m.query += key
				m.applyFilter()
			}
		}
		return m, nil
	}

	// Pass through to spinner while loading
	if m.state == pickerLoading {
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	return m, nil
}

func (m pickerModel) View() tea.View {
	view := tea.NewView(m.render())
	view.AltScreen = true
	return view
}

func (m pickerModel) render() string {
	if m.width == 0 {
		return "Loading..."
	}

	var b strings.Builder
	b.WriteString("  " + titleStyle.Render(m.title) + "\n\n")

	switch m.state {
	case pickerLoading:
		fmt.Fprintf(&b, "  %s Loading...\n", m.spinner.View())

	case pickerError:
		b.WriteString("  " + errStyle.Render("Error: "+m.err.Error()) + "\n\n")
		b.WriteString("  " + helpStyle.Render("Press esc to quit.") + "\n")

	case pickerReady, pickerDone, pickerAborted:
		// Filter line
		cursor := dimStyle.Render("█")
		if m.query == "" {
			b.WriteString("  " + dimStyle.Render("Filter: ") + cursor + "\n\n")
		} else {
			b.WriteString("  " + dimStyle.Render("Filter: ") + m.query + cursor + "\n\n")
		}

		// List
		listHeight := max(5, m.height-9)
		start := 0
		if m.cursor >= listHeight {
			start = m.cursor - listHeight + 1
		}
		end := min(len(m.filtered), start+listHeight)

		if len(m.filtered) == 0 {
			b.WriteString("  " + dimStyle.Render("No matches.") + "\n")
		} else {
			for i := start; i < end; i++ {
				item := truncate(m.filtered[i], m.width-6)
				if i == m.cursor {
					b.WriteString(selStyle.Render("  > "+item) + "\n")
				} else {
					b.WriteString("    " + item + "\n")
				}
			}
		}

		b.WriteString("\n")
		fmt.Fprintf(&b, "  %s\n", helpStyle.Render(fmt.Sprintf("↑/↓ navigate • enter select • esc quit • %d/%d", len(m.filtered), len(m.items))))
	}

	return b.String()
}

func (m *pickerModel) applyFilter() {
	q := strings.ToLower(strings.TrimSpace(m.query))
	if q == "" {
		m.filtered = m.items
	} else {
		filtered := make([]string, 0, len(m.items))
		for _, item := range m.items {
			if strings.Contains(strings.ToLower(item), q) {
				filtered = append(filtered, item)
			}
		}
		m.filtered = filtered
	}
	m.cursor = 0
}

func isPrintable(s string) bool {
	runes := []rune(s)
	if len(runes) != 1 {
		return false
	}
	return unicode.IsPrint(runes[0])
}

func truncate(s string, width int) string {
	if width <= 0 {
		return ""
	}
	if lipgloss.Width(s) <= width {
		return s
	}
	return lipgloss.NewStyle().MaxWidth(width).Render(s)
}

