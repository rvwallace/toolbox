package main

import (
	"fmt"
	"strconv"
	"strings"

	"charm.land/bubbles/v2/textinput"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

// ── Settings field ordering ───────────────────────────────────────────────────
// Using an iota keeps the field list and the cursor in sync.
// Add a new const here and a matching case in settingsModel.View() to add a field.

type settingsField int

const (
	fieldInstallPath settingsField = iota
	fieldDownloadPath
	fieldReleasesPerPage
	fieldMarkExecutable
	fieldCount
)

// ── Styles ────────────────────────────────────────────────────────────────────

var (
	settingLabelStyle   = lipgloss.NewStyle().Width(20).Foreground(lipgloss.Color("244"))
	settingActiveLabel  = lipgloss.NewStyle().Width(20).Foreground(lipgloss.Color("212")).Bold(true)
	settingToggleOn     = lipgloss.NewStyle().Foreground(lipgloss.Color("82")).Bold(true)
	settingToggleOff    = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))
	settingSavedStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("82"))
	settingUnsaved      = lipgloss.NewStyle().Foreground(lipgloss.Color("214"))
)

// ── settingsSavedMsg ──────────────────────────────────────────────────────────
// Sent by the save Cmd so the parent model knows settings were committed.

type settingsSavedMsg struct {
	cfg Config
}

// ── settingsModel ─────────────────────────────────────────────────────────────
// settingsModel is a self-contained sub-model for the settings screen.
// The parent model holds one of these and delegates Update/View calls to it
// while stateSettings is active.

type settingsModel struct {
	cfg     Config        // working copy — only committed on save
	cursor  settingsField // which field is focused
	inputs  []textinput.Model
	saved   bool   // show "saved" confirmation briefly
	saveErr string // non-empty if save failed
}

// newSettingsModel builds the settings sub-model from the current config.
func newSettingsModel(cfg Config) settingsModel {
	inputs := make([]textinput.Model, fieldCount)

	// Build a textinput for each editable field.
	// Toggle fields (bool) don't use textinput — they're flipped with Space.

	inputs[fieldInstallPath] = makeInput(cfg.InstallPath, "~/.local/bin", false)
	inputs[fieldDownloadPath] = makeInput(cfg.DownloadPath, ". (current directory)", false)
	inputs[fieldReleasesPerPage] = makeInput(strconv.Itoa(cfg.ReleasesPerPage), "10", false)

	// Focus the first field on open.
	inputs[fieldInstallPath].Focus()

	return settingsModel{
		cfg:    cfg,
		cursor: fieldInstallPath,
		inputs: inputs,
	}
}

// makeInput constructs a configured textinput.
func makeInput(value, placeholder string, password bool) textinput.Model {
	ti := textinput.New()
	ti.SetValue(value)
	ti.Placeholder = placeholder
	if password {
		// EchoModePassword shows *** — safe for terminal shoulder-surfing.
		ti.EchoMode = textinput.EchoPassword
	}
	return ti
}

// ── Init ──────────────────────────────────────────────────────────────────────

// ── Update ────────────────────────────────────────────────────────────────────

func (s settingsModel) Update(msg tea.Msg) (settingsModel, tea.Cmd) {
	switch msg := msg.(type) {

	case tea.KeyPressMsg:
		s.saved = false   // clear "saved" indicator on any keypress
		s.saveErr = ""

		switch msg.String() {

		// Tab / Shift+Tab move between fields.
		case "tab", "down":
			s.moveCursor(1)
			return s, nil

		case "shift+tab", "up":
			s.moveCursor(-1)
			return s, nil

		// Space toggles boolean fields.
		case " ":
			if s.cursor == fieldMarkExecutable {
				s.cfg.MarkExecutable = !s.cfg.MarkExecutable
			}
			return s, nil

		// Enter on the last field (or s key) saves.
		case "enter":
			return s, s.saveCmd()

		// Escape returns without saving.
		case "esc":
			// Return a nil Cmd — the parent model watches for
			// settingsSavedMsg and won't see one, so it handles
			// esc by switching state itself.
			return s, nil
		}

	// settingsSavedMsg comes back from our save goroutine.
	case settingsSavedMsg:
		s.cfg = msg.cfg
		s.saved = true
		return s, nil
	}

	// Forward the message to the currently focused textinput.
	if s.isTextField(s.cursor) {
		var cmd tea.Cmd
		s.inputs[s.cursor], cmd = s.inputs[s.cursor].Update(msg)
		return s, cmd
	}

	return s, nil
}

// moveCursor shifts focus by delta, wrapping around fieldCount.
func (s *settingsModel) moveCursor(delta int) {
	s.inputs[s.cursor].Blur()
	s.cursor = settingsField((int(s.cursor) + delta + int(fieldCount)) % int(fieldCount))
	if s.isTextField(s.cursor) {
		s.inputs[s.cursor].Focus()
	}
}

// isTextField returns true for fields that use a textinput.
func (s settingsModel) isTextField(f settingsField) bool {
	return f != fieldMarkExecutable
}

// saveCmd builds the Config from current input values and writes it to disk.
// Returns a tea.Cmd so the write happens off the main goroutine.
func (s settingsModel) saveCmd() tea.Cmd {
	// Snapshot values from the inputs right now — Cmds run asynchronously
	// so we must not close over the mutable inputs slice.
	installPath  := s.inputs[fieldInstallPath].Value()
	downloadPath := s.inputs[fieldDownloadPath].Value()
	perPageStr   := s.inputs[fieldReleasesPerPage].Value()
	markExec     := s.cfg.MarkExecutable

	return func() tea.Msg {
		perPage, err := strconv.Atoi(perPageStr)
		if err != nil || perPage < 1 || perPage > 100 {
			perPage = 10
		}

		cfg := Config{
			InstallPath:     installPath,
			DownloadPath:    downloadPath,
			ReleasesPerPage: perPage,
			MarkExecutable:  markExec,
		}

		if err := saveConfig(cfg); err != nil {
			// Return an errMsg so the parent model surfaces it.
			return errMsg{fmt.Errorf("saving config: %w", err)}
		}

		return settingsSavedMsg{cfg: cfg}
	}
}

// ── View ──────────────────────────────────────────────────────────────────────

func (s settingsModel) View() string {
	var b strings.Builder

	b.WriteString(titleStyle.Render("  Settings") + "\n\n")

	s.renderTextField(&b, fieldInstallPath, "Install path")
	s.renderTextField(&b, fieldDownloadPath, "Download path")
	s.renderTextField(&b, fieldReleasesPerPage, "Releases to fetch")
	s.renderToggle(&b, fieldMarkExecutable, "Mark executable", s.cfg.MarkExecutable)

	b.WriteString("\n")

	// Status line.
	switch {
	case s.saved:
		b.WriteString(settingSavedStyle.Render("  ✓ Settings saved") + "\n")
	case s.saveErr != "":
		b.WriteString(errorStyle.Render("  ✗ "+s.saveErr) + "\n")
	default:
		b.WriteString(settingUnsaved.Render("  Unsaved") + "\n")
	}

	b.WriteString("\n")
	b.WriteString(helpStyle.Render("  tab/↑↓ navigate • space toggle • enter save • esc back"))

	return b.String()
}

// renderTextField draws one text-editable row.
func (s *settingsModel) renderTextField(b *strings.Builder, field settingsField, label string) {
	active := s.cursor == field
	lStyle := settingLabelStyle
	if active {
		lStyle = settingActiveLabel
	}
	prefix := "    "
	if active {
		prefix = "  ❯ "
	}
	fmt.Fprintf(b, "%s%s  %s\n", prefix, lStyle.Render(label), s.inputs[field].View())
}

// renderToggle draws one boolean-toggle row.
func (s *settingsModel) renderToggle(b *strings.Builder, field settingsField, label string, value bool) {
	active := s.cursor == field
	lStyle := settingLabelStyle
	if active {
		lStyle = settingActiveLabel
	}
	prefix := "    "
	if active {
		prefix = "  ❯ "
	}

	var toggle string
	if value {
		toggle = settingToggleOn.Render("● on ")
	} else {
		toggle = settingToggleOff.Render("○ off")
	}

	fmt.Fprintf(b, "%s%s  %s\n", prefix, lStyle.Render(label), toggle)
}
