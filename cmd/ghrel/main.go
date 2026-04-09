package main

import (
	"fmt"
	"os"

	tea "charm.land/bubbletea/v2"
)

func main() {
	// tea.NewProgram takes your initial model and owns the terminal
	// until p.Run() returns.
	//
	// tea.WithAltScreen() switches to the alternate terminal buffer
	// (the same trick vim/htop use — your shell history is preserved).
	p := tea.NewProgram(newModel())

	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
