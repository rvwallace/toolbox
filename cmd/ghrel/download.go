package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	tea "charm.land/bubbletea/v2"
)

// downloadDoneMsg is sent to the Bubble Tea runtime when the download finishes.
// In Bubble Tea, goroutines communicate back to the UI by returning a Msg.
type downloadDoneMsg struct {
	path string
}

// errMsg wraps any error so we can handle it in Update.
type errMsg struct {
	err error
}

// releasesLoadedMsg carries the releases back from the API goroutine.
type releasesLoadedMsg struct {
	releases []Release
}

// fetchReleasesCmd returns a tea.Cmd — a function that runs in a goroutine
// and returns a single Msg when done.
//
// This is the core Bubble Tea pattern for I/O:
//   cmd := func() tea.Msg { ... do work ... return someMsg{} }
func fetchReleasesCmd(repo string, perPage int) tea.Cmd {
	return func() tea.Msg {
		client := newGithubClient()
		releases, err := client.fetchReleases(repo, perPage)
		if err != nil {
			return errMsg{err}
		}
		return releasesLoadedMsg{releases}
	}
}

// downloadAssetCmd downloads the asset to the path from config.
// If cfg.MarkExecutable is set, it chmods the file 0755 after writing.
func downloadAssetCmd(asset Asset, cfg Config) tea.Cmd {
	return func() tea.Msg {
		dir := effectiveDownloadPath(cfg)
		if err := os.MkdirAll(dir, 0o750); err != nil {
			return errMsg{fmt.Errorf("creating download dir: %w", err)}
		}

		dest := filepath.Join(dir, asset.Name)

		resp, err := http.Get(asset.BrowserDownloadURL) //nolint:noctx
		if err != nil {
			return errMsg{fmt.Errorf("starting download: %w", err)}
		}
		defer resp.Body.Close()

		f, err := os.Create(dest)
		if err != nil {
			return errMsg{fmt.Errorf("creating file: %w", err)}
		}
		defer f.Close()

		if _, err := io.Copy(f, resp.Body); err != nil {
			return errMsg{fmt.Errorf("writing file: %w", err)}
		}

		// chmod +x if the user wants it and it looks like a bare binary
		// (no archive extension). Archives need extraction first.
		if cfg.MarkExecutable && isBareExecutable(asset.Name) {
			if err := os.Chmod(dest, 0o755); err != nil {
				return errMsg{fmt.Errorf("chmod: %w", err)}
			}
		}

		return downloadDoneMsg{path: dest}
	}
}

// isBareExecutable returns true when the asset name has no archive extension.
// We only auto-chmod bare binaries — tarballs and zips need extraction first.
func isBareExecutable(name string) bool {
	for _, ext := range []string{".tar.gz", ".tgz", ".zip", ".gz", ".bz2", ".xz", ".deb", ".rpm", ".7z"} {
		if strings.HasSuffix(name, ext) {
			return false
		}
	}
	return true
}
