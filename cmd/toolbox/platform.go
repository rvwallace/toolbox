package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"gopkg.in/yaml.v3"
)

const scriptPlatformHeader = "toolbox-platforms:"

type commandMetadata struct {
	Platforms []string `yaml:"platforms"`
}

func currentPlatform() string {
	return runtime.GOOS
}

func isPlatformSupported(platforms []string) (bool, error) {
	if len(platforms) == 0 {
		return true, nil
	}

	current := currentPlatform()
	for _, p := range platforms {
		norm, err := normalizePlatform(p)
		if err != nil {
			return false, err
		}
		if norm == "all" || norm == current {
			return true, nil
		}
	}
	return false, nil
}

func normalizePlatform(p string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(p)) {
	case "", "all", "universal":
		return "all", nil
	case "darwin", "macos", "mac":
		return "darwin", nil
	case "linux":
		return "linux", nil
	default:
		return "", fmt.Errorf("unsupported platform %q (use all, linux, darwin/macos)", p)
	}
}

func parsePlatformList(raw string) ([]string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	seen := make(map[string]struct{})
	for _, part := range parts {
		norm, err := normalizePlatform(part)
		if err != nil {
			return nil, err
		}
		if _, ok := seen[norm]; ok {
			continue
		}
		seen[norm] = struct{}{}
		out = append(out, norm)
	}
	return out, nil
}

func platformSummary(platforms []string) string {
	if len(platforms) == 0 {
		return "all"
	}
	return strings.Join(platforms, ",")
}

func readScriptPlatforms(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	sc := bufio.NewScanner(f)
	for i := 0; sc.Scan() && i < 25; i++ {
		line := strings.TrimSpace(sc.Text())
		switch {
		case strings.HasPrefix(line, "# "+scriptPlatformHeader):
			return parsePlatformList(strings.TrimSpace(strings.TrimPrefix(line, "# "+scriptPlatformHeader)))
		case strings.HasPrefix(line, "#"+scriptPlatformHeader):
			return parsePlatformList(strings.TrimSpace(strings.TrimPrefix(line, "#"+scriptPlatformHeader)))
		case strings.HasPrefix(line, "// "+scriptPlatformHeader):
			return parsePlatformList(strings.TrimSpace(strings.TrimPrefix(line, "// "+scriptPlatformHeader)))
		case strings.HasPrefix(line, "//"+scriptPlatformHeader):
			return parsePlatformList(strings.TrimSpace(strings.TrimPrefix(line, "//"+scriptPlatformHeader)))
		}
	}
	return nil, sc.Err()
}

func readCommandPlatforms(cmdDir string) ([]string, error) {
	metaPath := filepath.Join(cmdDir, "toolbox.yaml")
	data, err := os.ReadFile(metaPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var meta commandMetadata
	if err := yaml.Unmarshal(data, &meta); err != nil {
		return nil, fmt.Errorf("%s: %w", metaPath, err)
	}
	return parsePlatformList(strings.Join(meta.Platforms, ","))
}

func removeBinTarget(path string) error {
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
