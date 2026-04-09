package main

import (
	"fmt"
	"strings"
	"time"

	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/textinput"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

// ── Styles ────────────────────────────────────────────────────────────────────

var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
	selectedStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("212")).Bold(true)
	dimStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))
	errorStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("196"))
	successStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("82"))
	helpStyle     = dimStyle

	// Panel styles.
	// activePanelHeader highlights the focused panel's header label and draws
	// a colored bottom border to make the active side obvious at a glance.
	activePanelHeader = lipgloss.NewStyle().
				Foreground(lipgloss.Color("212")).
				Bold(true).
				BorderBottom(true).
				BorderStyle(lipgloss.NormalBorder()).
				BorderForeground(lipgloss.Color("212"))

	inactivePanelHeader = lipgloss.NewStyle().
				Foreground(lipgloss.Color("238")).
				BorderBottom(true).
				BorderStyle(lipgloss.NormalBorder()).
				BorderForeground(lipgloss.Color("236"))

	// The left panel gets a right-hand border to create the divider.
	leftPanelStyle = lipgloss.NewStyle().
			BorderRight(true).
			BorderStyle(lipgloss.NormalBorder()).
			BorderForeground(lipgloss.Color("236")).
			PaddingRight(1)

	rightPanelStyle = lipgloss.NewStyle().PaddingLeft(1)

	// Inactive selected row — shows the cursor position in the unfocused panel
	// without competing with the active panel's highlight.
	inactiveSelStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("244"))
)

// ── Panel focus ───────────────────────────────────────────────────────────────

type panel int

const (
	panelReleases panel = iota
	panelAssets
)

// ── State machine ─────────────────────────────────────────────────────────────

type appState int

const (
	stateInput     appState = iota
	stateLoading            // waiting for GitHub API
	stateBrowse             // two-panel release+asset picker
	stateDownloading
	stateDone
	stateError
	stateSettings
)

// ── Model ─────────────────────────────────────────────────────────────────────

type model struct {
	state appState

	input    textinput.Model
	spinner  spinner.Model
	settings settingsModel

	cfg Config

	// GitHub data.
	repo     string
	releases []Release

	// Two-panel browse state.
	focused   panel // which panel has keyboard focus
	relCursor int
	astCursor int

	// Terminal dimensions — received from WindowSizeMsg.
	width int

	downloadedPath string
	err            error
}

func newModel() model {
	cfg, _ := loadConfig()

	ti := textinput.New()
	ti.Placeholder = "owner/repo  (e.g. devmatteini/dra)"
	ti.Focus()

	sp := spinner.New()
	sp.Spinner = spinner.Dot

	return model{
		state:    stateInput,
		input:    ti,
		spinner:  sp,
		cfg:      cfg,
		settings: newSettingsModel(cfg),
		width:    80, // safe default before first WindowSizeMsg
	}
}

// ── Init ──────────────────────────────────────────────────────────────────────

func (m model) Init() tea.Cmd {
	return textinput.Blink
}

// ── Update ────────────────────────────────────────────────────────────────────

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.input.SetWidth(msg.Width - 4)
		return m, nil
	case errMsg:
		m.state = stateError
		m.err = msg.err
		return m, nil
	case tea.KeyPressMsg:
		if msg.String() == "ctrl+c" {
			return m, tea.Quit
		}
	}

	if m.state == stateSettings {
		return m.updateSettings(msg)
	}

	switch m.state {
	case stateInput:
		return m.updateInput(msg)
	case stateLoading:
		return m.updateLoading(msg)
	case stateBrowse:
		return m.updateBrowse(msg)
	case stateDownloading:
		return m.updateDownloading(msg)
	case stateDone, stateError:
		if _, ok := msg.(tea.KeyPressMsg); ok {
			return m, tea.Quit
		}
	}

	return m, nil
}

func (m model) updateSettings(msg tea.Msg) (tea.Model, tea.Cmd) {
	if key, ok := msg.(tea.KeyPressMsg); ok && key.String() == "esc" {
		m.state = stateInput
		return m, nil
	}
	if saved, ok := msg.(settingsSavedMsg); ok {
		m.cfg = saved.cfg
		m.settings = newSettingsModel(saved.cfg)
	}
	updated, cmd := m.settings.Update(msg)
	m.settings = updated
	return m, cmd
}

func (m model) updateInput(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case tea.KeyPressMsg:
		switch msg.String() {
		case "enter":
			repo := strings.TrimSpace(m.input.Value())
			if repo == "" {
				return m, nil
			}
			m.repo = repo
			m.state = stateLoading
			return m, tea.Batch(
				m.spinner.Tick,
				fetchReleasesCmd(repo, m.cfg.ReleasesPerPage),
			)
		case "s":
			m.state = stateSettings
			m.settings = newSettingsModel(m.cfg)
			return m, textinput.Blink
		}
	}
	m.input, cmd = m.input.Update(msg)
	return m, cmd
}

func (m model) updateLoading(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case releasesLoadedMsg:
		m.releases = msg.releases
		if len(m.releases) == 0 {
			m.state = stateError
			m.err = fmt.Errorf("no releases found for %s", m.repo)
			return m, nil
		}
		m.state = stateBrowse
		m.focused = panelReleases
		m.relCursor = 0
		m.astCursor = 0
		return m, nil
	}
	var cmd tea.Cmd
	m.spinner, cmd = m.spinner.Update(msg)
	return m, cmd
}

func (m model) updateBrowse(msg tea.Msg) (tea.Model, tea.Cmd) {
	key, ok := msg.(tea.KeyPressMsg)
	if !ok {
		return m, nil
	}

	switch key.String() {

	// j/k and arrow keys move within the focused panel.
	case "up", "k":
		if m.focused == panelReleases {
			if m.relCursor > 0 {
				m.relCursor--
				m.astCursor = 0 // reset asset cursor when release changes
			}
		} else {
			if m.astCursor > 0 {
				m.astCursor--
			}
		}

	case "down", "j":
		if m.focused == panelReleases {
			if m.relCursor < len(m.releases)-1 {
				m.relCursor++
				m.astCursor = 0
			}
		} else {
			assets := m.releases[m.relCursor].Assets
			if m.astCursor < len(assets)-1 {
				m.astCursor++
			}
		}

	// tab / shift+tab switch panel focus.
	// From releases, tab moves to assets only if the release has assets.
	case "tab", "l":
		if m.focused == panelReleases && len(m.currentAssets()) > 0 {
			m.focused = panelAssets
		}

	case "shift+tab", "h":
		if m.focused == panelAssets {
			m.focused = panelReleases
		}

	// enter on releases moves focus to assets (mirrors pressing tab).
	// enter on assets triggers the download.
	case "enter":
		if m.focused == panelReleases {
			if len(m.currentAssets()) == 0 {
				m.err = fmt.Errorf("release %s has no assets", m.releases[m.relCursor].TagName)
				m.state = stateError
				return m, nil
			}
			m.focused = panelAssets
		} else {
			assets := m.currentAssets()
			m.state = stateDownloading
			return m, tea.Batch(
				m.spinner.Tick,
				downloadAssetCmd(assets[m.astCursor], m.cfg),
			)
		}

	case "s":
		m.state = stateSettings
		m.settings = newSettingsModel(m.cfg)
		return m, textinput.Blink

	case "q", "esc":
		// esc from assets returns focus to releases.
		// esc from releases goes back to the input screen.
		if m.focused == panelAssets {
			m.focused = panelReleases
		} else {
			m.state = stateInput
			m.input.SetValue("")
		}
	}

	return m, nil
}

// currentAssets returns the asset list for the currently selected release.
func (m model) currentAssets() []Asset {
	if len(m.releases) == 0 {
		return nil
	}
	return m.releases[m.relCursor].Assets
}

func (m model) updateDownloading(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case downloadDoneMsg:
		m.downloadedPath = msg.path
		m.state = stateDone
		return m, nil
	}
	var cmd tea.Cmd
	m.spinner, cmd = m.spinner.Update(msg)
	return m, cmd
}

// ── View ──────────────────────────────────────────────────────────────────────

func (m model) View() tea.View {
	v := tea.NewView(m.render())
	v.AltScreen = true
	return v
}

func (m model) render() string {
	var b strings.Builder

	if m.state == stateSettings {
		b.WriteString(m.settings.View())
		return b.String()
	}

	b.WriteString(titleStyle.Render("  ghrel — GitHub Release Downloader") + "\n\n")

	switch m.state {

	case stateInput:
		b.WriteString("  Repository\n")
		b.WriteString("  " + m.input.View() + "\n\n")
		b.WriteString(helpStyle.Render("  enter search • s settings • ctrl+c quit"))

	case stateLoading:
		b.WriteString(fmt.Sprintf("  %s Fetching releases for %s…\n",
			m.spinner.View(), titleStyle.Render(m.repo)))

	case stateBrowse:
		b.WriteString(m.renderBrowse())

	case stateDownloading:
		asset := m.currentAssets()[m.astCursor]
		b.WriteString(fmt.Sprintf("  %s Downloading %s…\n",
			m.spinner.View(), titleStyle.Render(asset.Name)))

	case stateDone:
		b.WriteString(successStyle.Render("  ✓ Downloaded: "+m.downloadedPath) + "\n\n")
		b.WriteString(helpStyle.Render("  any key to quit"))

	case stateError:
		b.WriteString(errorStyle.Render("  ✗ Error: "+m.err.Error()) + "\n\n")
		b.WriteString(helpStyle.Render("  any key to quit"))
	}

	b.WriteString("\n")
	return b.String()
}

// renderBrowse builds the two-panel layout.
//
// Each panel is rendered independently as a string, then lipgloss joins
// them horizontally. This is the standard approach in Bubble Tea — render
// each component to a string, then compose them.
func (m model) renderBrowse() string {
	// Divide available width evenly, leaving room for the divider.
	halfW := (m.width - 6) / 2 // -6 for margins and border

	left := m.renderReleasesPanel(halfW)
	right := m.renderAssetsPanel(halfW)

	left = leftPanelStyle.Render(left)
	right = rightPanelStyle.Render(right)

	panels := lipgloss.JoinHorizontal(lipgloss.Top, left, right)

	var b strings.Builder
	b.WriteString("  Repo: " + titleStyle.Render(m.repo) + "\n\n")
	b.WriteString(panels + "\n")

	// Help line changes based on which panel is focused.
	if m.focused == panelReleases {
		b.WriteString(helpStyle.Render("\n  j/k move • tab/l focus assets • s settings • esc back"))
	} else {
		b.WriteString(helpStyle.Render("\n  j/k move • tab/h focus releases • enter download • esc back"))
	}

	return b.String()
}

// renderReleasesPanel renders the left panel content at the given width.
func (m model) renderReleasesPanel(width int) string {
	var b strings.Builder

	// Header — active or inactive styling.
	label := "Releases"
	hint := ""
	if m.focused == panelReleases {
		hint = "tab →"
		b.WriteString(activePanelHeader.Width(width).Render(fmt.Sprintf("%-*s%s", width-len(hint), label, hint)) + "\n")
	} else {
		hint = "← tab"
		b.WriteString(inactivePanelHeader.Width(width).Render(fmt.Sprintf("%-*s%s", width-len(hint), label, hint)) + "\n")
	}

	dateW := 12
	nameW := width - dateW - 1 // -1 for the cursor prefix space

	for i, r := range m.releases {
		name := r.Name
		if name == "" {
			name = r.TagName
		}
		if len(name) > nameW {
			name = name[:nameW-1] + "…"
		}

		date := formatDate(r.PublishedAt)

		row := fmt.Sprintf("%-*s%s", nameW, name, dimStyle.Render(date))

		switch {
		case i == m.relCursor && m.focused == panelReleases:
			b.WriteString(selectedStyle.Render("❯ "+row) + "\n")
		case i == m.relCursor:
			// Cursor position in unfocused panel — visible but not bright.
			b.WriteString(inactiveSelStyle.Render("  "+row) + "\n")
		default:
			b.WriteString(dimStyle.Render("  "+row) + "\n")
		}
	}

	return b.String()
}

// renderAssetsPanel renders the right panel content at the given width.
func (m model) renderAssetsPanel(width int) string {
	var b strings.Builder

	assets := m.currentAssets()
	rel := m.releases[m.relCursor]
	tag := rel.TagName

	count := fmt.Sprintf("%d files", len(assets))
	label := "Assets — " + tag
	if len(label)+len(count) > width {
		label = tag
	}

	if m.focused == panelAssets {
		b.WriteString(activePanelHeader.Width(width).Render(
			fmt.Sprintf("%-*s%s", width-len(count), label, count)) + "\n")
	} else {
		b.WriteString(inactivePanelHeader.Width(width).Render(
			fmt.Sprintf("%-*s%s", width-len(count), label, count)) + "\n")
	}

	if len(assets) == 0 {
		b.WriteString(dimStyle.Render("  no assets") + "\n")
		return b.String()
	}

	sizeW := 8
	nameW := width - sizeW - 1

	for i, a := range assets {
		name := a.Name
		if len(name) > nameW {
			name = name[:nameW-1] + "…"
		}
		size := formatBytes(a.Size)
		row := fmt.Sprintf("%-*s%*s", nameW, name, sizeW, size)

		switch {
		case i == m.astCursor && m.focused == panelAssets:
			b.WriteString(selectedStyle.Render("❯ "+row) + "\n")
		case i == m.astCursor:
			b.WriteString(inactiveSelStyle.Render("  "+row) + "\n")
		default:
			b.WriteString(dimStyle.Render("  "+row) + "\n")
		}
	}

	return b.String()
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func formatBytes(n int64) string {
	switch {
	case n >= 1 << 30:
		return fmt.Sprintf("%.1fG", float64(n)/(1<<30))
	case n >= 1 << 20:
		return fmt.Sprintf("%.1fM", float64(n)/(1<<20))
	case n >= 1 << 10:
		return fmt.Sprintf("%.1fK", float64(n)/(1<<10))
	default:
		return fmt.Sprintf("%dB", n)
	}
}

func formatDate(s string) string {
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return ""
	}
	return t.Format("Jan 02 2006")
}
