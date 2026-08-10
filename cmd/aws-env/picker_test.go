package main

import (
	"strings"
	"testing"
)

func TestPickerFilterResetsCursor(t *testing.T) {
	m := pickerModel{
		items:  []string{"default", "development", "production"},
		query:  "dev",
		cursor: 2,
	}

	m.applyFilter()

	if len(m.filtered) != 1 || m.filtered[0] != "development" {
		t.Fatalf("filtered = %q", m.filtered)
	}
	if m.cursor != 0 {
		t.Fatalf("cursor = %d, want 0", m.cursor)
	}
}

func TestPickerMoveCursorClampsToResults(t *testing.T) {
	m := pickerModel{filtered: []string{"one", "two", "three"}}

	m.moveCursor(20)
	if m.cursor != 2 {
		t.Fatalf("cursor after moving down = %d, want 2", m.cursor)
	}
	m.moveCursor(-20)
	if m.cursor != 0 {
		t.Fatalf("cursor after moving up = %d, want 0", m.cursor)
	}
}

func TestPickerSmallTerminalMessage(t *testing.T) {
	m := pickerModel{title: "Select profile", width: 39, height: 24}

	view := m.render()

	if !strings.Contains(view, "Terminal too small") {
		t.Fatalf("rendered view did not contain resize guidance: %q", view)
	}
}

func TestPickerHelpListsNavigation(t *testing.T) {
	m := pickerModel{title: "Select profile", width: 80, height: 24, showHelp: true}

	view := m.render()

	for _, want := range []string{"Keyboard help", "PgUp/PgDn", "Ctrl-u", "Enter"} {
		if !strings.Contains(view, want) {
			t.Errorf("rendered help does not contain %q", want)
		}
	}
}
