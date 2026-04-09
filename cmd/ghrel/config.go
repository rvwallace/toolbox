package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Config holds all user-configurable settings.
// It is serialized to ~/.config/silentcastle/ghrel.json (XDG-aware).
type Config struct {
	// InstallPath is where extracted binaries are placed (e.g. ~/.local/bin).
	InstallPath string `json:"install_path"`

	// DownloadPath is where the raw asset file is saved.
	// Defaults to the current working directory if empty.
	DownloadPath string `json:"download_path"`

	// ReleasesPerPage controls how many releases are fetched from GitHub.
	// Valid values: 5, 10, 20, 30. Defaults to 10.
	ReleasesPerPage int `json:"releases_per_page"`

	// MarkExecutable automatically chmod +x downloaded binaries.
	MarkExecutable bool `json:"mark_executable"`
}

// defaultConfig returns sensible out-of-the-box settings.
func defaultConfig() Config {
	home, _ := os.UserHomeDir()
	return Config{
		InstallPath:     filepath.Join(home, ".local", "bin"),
		DownloadPath:    "",
		ReleasesPerPage: 10,
		MarkExecutable:  true,
	}
}

func xdgConfigBase() (string, error) {
	base := os.Getenv("XDG_CONFIG_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("finding home directory: %w", err)
		}
		base = filepath.Join(home, ".config")
	}
	return base, nil
}

// configPath returns the canonical path for new installs and saves.
func configPath() (string, error) {
	base, err := xdgConfigBase()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "silentcastle", "ghrel.json"), nil
}

// legacyConfigPath was used by the standalone ghrel repo.
func legacyConfigPath() (string, error) {
	base, err := xdgConfigBase()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "ghrel", "config.json"), nil
}

// loadConfig reads the config file.
// If the file does not exist, returns defaultConfig without error —
// first-run case where the user hasn't saved settings yet.
// Tries ~/.config/silentcastle/ghrel.json first, then ~/.config/ghrel/config.json.
func loadConfig() (Config, error) {
	paths := make([]string, 0, 2)
	if p, err := configPath(); err == nil {
		paths = append(paths, p)
	}
	if p, err := legacyConfigPath(); err == nil {
		paths = append(paths, p)
	}

	var firstErr error
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if os.IsNotExist(err) {
			continue
		}
		if err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		cfg := defaultConfig()
		if err := json.Unmarshal(data, &cfg); err != nil {
			return defaultConfig(), fmt.Errorf("parsing config: %w", err)
		}
		return cfg, nil
	}
	if firstErr != nil {
		return defaultConfig(), fmt.Errorf("reading config: %w", firstErr)
	}
	return defaultConfig(), nil
}

// saveConfig writes cfg to the config file, creating the directory if needed.
func saveConfig(cfg Config) error {
	path, err := configPath()
	if err != nil {
		return err
	}

	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return fmt.Errorf("creating config dir: %w", err)
	}

	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return fmt.Errorf("encoding config: %w", err)
	}

	// 0600 — config may contain a GitHub token.
	if err := os.WriteFile(path, data, 0o600); err != nil {
		return fmt.Errorf("writing config: %w", err)
	}

	return nil
}

// effectiveDownloadPath returns the download destination, expanding ~ if present.
// Falls back to the current directory when empty.
func effectiveDownloadPath(cfg Config) string {
	if cfg.DownloadPath == "" {
		return "."
	}
	return expandHome(cfg.DownloadPath)
}

// expandHome replaces a leading ~ with the user's home directory.
func expandHome(path string) string {
	if len(path) == 0 || path[0] != '~' {
		return path
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return path
	}
	return filepath.Join(home, path[1:])
}
